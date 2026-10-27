"""ShadowPad: local webcam tracking and opt-in calibrated PPSSPP movement."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
import textwrap

import cv2
import mediapipe as mp
import numpy as np

from tracking_quality import CONNECTIONS, JOINTS, STALE_SECONDS, assess, framing_hints, joint_reason, tracking_label
from performance import PipelineMetrics, environment, write_report
from movement import MovementController
from attacks import DEFAULT_ATTACK_SENSITIVITY
from hand_tracking import HAND_MODEL, HandTracker
from hand_identity import body_references
from ppsspp_input import CONTROL_ACTIONS, PracticeKeyboard, WindowsKeyboard, default_controls, read_bindings


MODEL = Path(__file__).resolve().parent / "models" / "pose_landmarker_full.task"
WINDOW = "ShadowPad | Camera setup"
GREEN = (130, 225, 100)
AMBER = (80, 195, 255)
WHITE = (235, 235, 235)


class Camera:
    """Capture continuously into one slot; consumers never build a frame queue."""

    def __init__(self, index, backend):
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.latest = None
        self.error = None
        self.frames = 0
        self.started = time.monotonic()
        api = cv2.CAP_DSHOW if backend == "dshow" else cv2.CAP_MSMF
        self.capture = cv2.VideoCapture(index, api)
        if not self.capture.isOpened():
            self.capture.release()
            raise RuntimeError(
                f"Cannot open camera {index} ({backend}). Close other camera apps, "
                "check Windows camera privacy settings, or try --camera 1 / --backend msmf."
            )
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.capture.set(cv2.CAP_PROP_FPS, 30)
        self.started = time.monotonic()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        try:
            while not self.stop.is_set():
                ok, frame = self.capture.read()
                if not ok or frame is None or frame.size == 0:
                    raise RuntimeError("Webcam stopped delivering frames. Reconnect it and restart.")
                captured_ms = time.monotonic_ns() // 1_000_000
                with self.lock:
                    self.frames += 1
                    self.latest = (self.frames, captured_ms, frame)
        except Exception as error:
            self.error = str(error)
        finally:
            self.capture.release()

    def snapshot(self):
        with self.lock:
            return self.latest

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            print("Camera driver did not finish closing promptly; exiting capture worker.", file=sys.stderr)


class Tracker:
    def __init__(self, model, confidence=0.6, warmup_results=15):
        self.lock = threading.Lock()
        self.busy = False
        self.latest = None
        self.submitted_at = 0.0
        self.pending_frame = None
        self.confidence = confidence
        self.metrics = PipelineMetrics(warmup_results)
        self.closed = False
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
            running_mode=mp.tasks.vision.RunningMode.LIVE_STREAM,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_segmentation_masks=False,
            result_callback=self._result,
        )
        self.landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)

    def _result(self, result, output_image, timestamp_ms):
        completed = time.monotonic()
        # Keep landmarks aligned with the exact frame that produced them.
        with self.lock:
            elapsed_ms = (completed - self.submitted_at) * 1000
            points = result.pose_landmarks[0] if result.pose_landmarks else None
            reliable_joints = assess(points, 0, self.confidence)[1]
            self.metrics.completed_frame(elapsed_ms, max(0, completed * 1000 - timestamp_ms),
                                         bool(points), reliable_joints)
            self.latest = (timestamp_ms, result, self.pending_frame, elapsed_ms)
            self.pending_frame = None
            self.busy = False

    def submit(self, frame, timestamp_ms):
        with self.lock:
            if self.busy:
                if time.monotonic() - self.submitted_at > 5:
                    raise RuntimeError("Pose inference stalled. Restart the preview.")
                return False
            self.busy = True
            self.submitted_at = time.monotonic()
            self.pending_frame = frame
        height, width = frame.shape[:2]
        if max(height, width) > 640:
            scale = 640 / max(height, width)
            frame = cv2.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        self.landmarker.detect_async(image, timestamp_ms)
        self.metrics.submitted_frame()
        return True

    def snapshot(self):
        with self.lock:
            return self.latest

    def close(self):
        if not self.closed:
            self.landmarker.close()
            self.closed = True


def put(image, text, position, color=WHITE, scale=0.5):
    cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX,
                scale, color, 1, cv2.LINE_AA)


def preview(frame, landmarks, visible, status, age, processing_ms, capture_fps, result_fps,
            details=False, confidence_threshold=0.6, draw_pose=True, hand_mode=False):
    """The entire camera image is usable; diagnostics never reserve a play area."""
    height, width = frame.shape[:2]
    canvas = frame.copy()

    def pixel(index):
        point = landmarks[index]
        # Infer on the original image; mirror only the display to keep body L/R correct.
        return (int((1 - point.x) * (width - 1)), int(point.y * (height - 1)))

    if landmarks and draw_pose:
        for first, second in CONNECTIONS:
            if first in visible and second in visible:
                cv2.line(canvas, pixel(first), pixel(second), GREEN, 3, cv2.LINE_AA)
        for index in visible:
            x, y = pixel(index)
            cv2.circle(canvas, (x, y), 5, GREEN, -1, cv2.LINE_AA)

    def band(top, bottom):
        region = canvas[top:bottom]
        canvas[top:bottom] = (region.astype(np.float32) * .25).astype(np.uint8)

    band(0, 34)
    ready = len(visible) == len(JOINTS)
    label = tracking_label(visible, status)
    if hand_mode and {11, 12} <= visible:
        label = "Shoulders tracked | dedicated hand AI"
    put(canvas, f"ShadowPad  |  {label}", (12, 23), GREEN if ready else WHITE, .5)
    band(height - 27, height)
    put(canvas, "Tab: details   F: fullscreen   Q: quit", (12, height - 9), scale=.4)

    if details:
        # An overlay, not a reserved sidebar: the camera frame and inference stay unchanged.
        panel_height = min(height - 35, 330)
        panel_width = min(width, 420)
        canvas[35:panel_height, :panel_width] = (canvas[35:panel_height, :panel_width] * .18).astype(np.uint8)
        put(canvas, f"Reliable joints: {len(visible)}/6 (threshold {confidence_threshold:.0%})", (12, 58), scale=.45)
        for row, (index, name) in enumerate(JOINTS.items()):
            point = landmarks[index] if landmarks and age <= STALE_SECONDS else None
            reason = joint_reason(point, confidence_threshold)
            put(canvas, f"{name}: {reason}", (12, 83 + row * 22),
                GREEN if index in visible else AMBER, .42)
        processing = f"{processing_ms:.0f} ms" if processing_ms is not None else "waiting"
        put(canvas, f"Camera {capture_fps:.1f} FPS | Results {result_fps:.1f} FPS", (12, 226), scale=.42)
        put(canvas, f"Submit-to-result {processing} | {width}x{height}", (12, 250), scale=.42)
        hint = framing_hints(landmarks, age, confidence_threshold)[0]
        for row, line in enumerate(textwrap.wrap(hint, 53)):
            put(canvas, line, (12, 277 + row * 20), scale=.4)
    return canvas


def control_overlay(canvas, controller, outlines, practice=False, details=False):
    for observation, outline in outlines:
        polygon = np.array([(int(x * canvas.shape[1]), int(y * canvas.shape[0]))
                            for x, y in outline], dtype=np.int32)
        state = controller.strikes.hands.get(observation.side)
        color = GREEN if state and state.phase == "ready" else AMBER
        cv2.polylines(canvas, [polygon], True, color, 2, cv2.LINE_AA)
        x, y = map(int, polygon[1])
        evidence = ("finger curl" if observation.source == "geometry"
                    else f"score {observation.score:.0%}")
        label = f"{observation.side}: {observation.gesture} | {evidence}"
        put(canvas, label, (max(5, min(x, canvas.shape[1] - 300)), max(50, y - 12)), color, .45)
    expanded = practice or details
    footer_height = 100 if expanded else 30
    canvas[-footer_height:] = (24, 24, 24)
    put(canvas, ("PRACTICE | " if practice else "") + controller.status,
        (12, canvas.shape[0] - (79 if expanded else 11)), scale=.42)
    if expanded:
        for row, (side, state) in enumerate(controller.strikes.hands.items()):
            status = f"{side}: {state.phase} | {state.reason} | reach {state.progress:.1f}/1"
            put(canvas, status, (12, canvas.shape[0] - 56 + row * 22), scale=.4)
        counts = "  ".join(f"{action} {count}" for action, count in controller.attack_counts.items())
        keys = f"atk {controller.strikes.sensitivity:.1f}x [ ]  C: start  A: pause  H: reset" if practice else "C: calibrate  A: arm  H: reset"
        put(canvas, counts + "   " + keys, (12, canvas.shape[0] - 12), scale=.38)
    return canvas


def run(args):
    if not args.model.is_file():
        raise RuntimeError("Pose model missing. Run: .\\.venv\\Scripts\\python.exe download_model.py")
    camera = None
    tracker = None
    hand_tracker = None
    controller = None
    practice = getattr(args, "practice", False)
    use_hands = args.control or practice
    hand_model = getattr(args, "hand_model", HAND_MODEL)
    if use_hands and not hand_model.is_file():
        raise RuntimeError("Hand model missing. Run: .\\.venv\\Scripts\\python.exe download_model.py --variant hands")
    count = ready_count = person_count = 0
    maximum_visible = 0
    last_result_ms = last_frame_ms = -1
    last_sequence = -1
    last_hand_frame = last_hand_result = -1
    last_report = 0.0
    last_practice_report = 0.0
    last_detection_summary = {}
    preview_opened = False
    details = False
    fullscreen = False
    status = "WAITING FOR CAMERA"
    started = time.monotonic()
    print("ShadowPad. Camera frames stay in memory. " +
          ("PRACTICE: no game keys will be sent. C calibrates and starts; A pauses/resumes." if practice else
           "Controller starts paused; press C in the preview to calibrate." if args.control
           else "Camera-only mode; no game inputs."), flush=True)
    try:
        if use_hands:
            bindings = ({action: (index + 1, action) for index, action in enumerate(CONTROL_ACTIONS)}
                        if practice else read_bindings(args.controls, CONTROL_ACTIONS))
            controller = MovementController(PracticeKeyboard() if practice else WindowsKeyboard(),
                                            bindings, args.sensitivity, getattr(args, "attack_sensitivity", DEFAULT_ATTACK_SENSITIVITY))
            hand_tracker = HandTracker(hand_model.resolve())
        tracker = Tracker(args.model.resolve(), args.confidence, args.warmup)
        camera = Camera(args.camera, args.backend)
        started = time.monotonic()
        if not args.headless:
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(WINDOW, 1000, 750)
        while not args.seconds or time.monotonic() - started < args.seconds:
            now = time.monotonic()
            if camera.error:
                raise RuntimeError(camera.error)
            captured = camera.snapshot()
            if captured is None:
                if now - started > 10:
                    raise RuntimeError("Camera opened but no frame arrived within 10 seconds.")
                time.sleep(0.01)
                continue
            sequence, frame_ms, raw = captured
            if now - frame_ms / 1000 > 2:
                raise RuntimeError("Camera feed stalled for more than two seconds. Restart the preview.")
            # Headless benchmarks avoid display-only copies and mirroring.
            mirrored = cv2.flip(raw, 1) if not args.headless else None
            if sequence != last_sequence and frame_ms > last_frame_ms:
                if tracker.submit(raw, frame_ms):
                    last_sequence, last_frame_ms = sequence, frame_ms

            snapshot = tracker.snapshot()
            landmarks = None
            age = float("inf")
            processing_ms = None
            display_frame = mirrored
            if snapshot is not None:
                result_ms, result, result_frame, processing_ms = snapshot
                age = max(0.0, time.monotonic() - result_ms / 1000)
                landmarks = result.pose_landmarks[0] if result.pose_landmarks else None
                if age <= STALE_SECONDS and not args.headless:
                    display_frame = cv2.flip(result_frame, 1)
                if result_ms != last_result_ms:
                    count += 1
                    person_count += bool(landmarks)
                    current_status, current_visible = assess(landmarks, age, args.confidence)
                    ready_count += current_status == "UPPER BODY READY"
                    maximum_visible = max(maximum_visible, len(current_visible))
                    last_result_ms = result_ms
                    if controller:
                        controller.on_pose(landmarks, age, time.monotonic(), args.confidence)
            hand_outlines = []
            if hand_tracker:
                if frame_ms > last_hand_frame:
                    references = body_references(landmarks, age, args.confidence)
                    if hand_tracker.submit(raw, frame_ms, references):
                        last_hand_frame = frame_ms
                hand_snapshot = hand_tracker.snapshot()
                if hand_snapshot is not None:
                    hand_ms, observations, outlines, hand_frame, diagnostics = hand_snapshot
                    last_detection_summary = diagnostics
                    hand_age = time.monotonic() - hand_ms / 1000
                    if hand_age <= .3:
                        display_frame = hand_frame
                        hand_outlines = outlines
                    if hand_ms != last_hand_result:
                        controller.on_hands(observations, hand_ms / 1000, time.monotonic(), diagnostics)
                        last_hand_result = hand_ms
            if controller:
                controller.tick(time.monotonic())
            if practice and now - last_practice_report >= 2:
                print(json.dumps({"practice_seconds": round(now - started, 1),
                                  "counts": controller.attack_counts,
                                  "input_presses": controller.input_press_counts,
                                  "active_actions": sorted(controller.key_actions[key] for key in controller.held),
                                  "detector": last_detection_summary,
                                  "hands": {side: {"phase": state.phase, "reason": state.reason}
                                            for side, state in controller.strikes.hands.items()}}), flush=True)
                last_practice_report = now
            status, visible = assess(landmarks, age, args.confidence)
            if snapshot is None:
                status = "WAITING FOR TRACKER"
            elapsed = max(time.monotonic() - started, 0.001)
            capture_fps = camera.frames / max(time.monotonic() - camera.started, 0.001)
            if controller and elapsed > 3 and capture_fps < 8:
                controller.status = f"CAMERA {capture_fps:.1f} FPS: too slow for strikes; check webcam and lighting"
            if args.headless and now - last_report >= 2:
                print(f"{status} | visible={len(visible)}/6 | camera={capture_fps:.1f} FPS "
                      f"| results={count / elapsed:.1f} FPS", flush=True)
                last_report = now
            if not args.headless:
                canvas = preview(display_frame, landmarks, visible, status, age,
                                 processing_ms, capture_fps, count / elapsed, details, args.confidence,
                                 draw_pose=not use_hands, hand_mode=use_hands)
                if controller:
                    control_overlay(canvas, controller, hand_outlines, practice, details)
                cv2.imshow(WINDOW, canvas)
                if not preview_opened:
                    print("Preview open. Q/Esc quits. C calibrates when movement control is enabled.", flush=True)
                    preview_opened = True
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    break
                if key == 9:
                    details = not details
                if key in (ord("c"), ord("C")) and controller:
                    controller.calibrate()
                if key in (ord("a"), ord("A")) and controller:
                    if practice and controller.armed:
                        controller.pause("Practice paused; A resumes")
                    else:
                        controller.arm_countdown(time.monotonic(), seconds=1 if practice else 5)
                if key in (ord("h"), ord("H")) and controller:
                    controller.strikes.reset()
                    controller.pulses.clear()
                if key in (ord("["), ord("]")) and controller:
                    value = controller.strikes.sensitivity + (.1 if key == ord("]") else -.1)
                    controller.strikes.set_sensitivity(round(min(2, max(.5, value)), 2))
                    controller.pulses.clear()
                if key in (ord("f"), ord("F")):
                    fullscreen = not fullscreen
                    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN,
                                          cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)
                    if not fullscreen:
                        cv2.resizeWindow(WINDOW, 1100, 825)
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break
            else:
                time.sleep(0.005)
        if count == 0:
            raise RuntimeError("No pose inference results received. Try a longer --seconds duration.")
        # Stop capture first, then drain the one pending inference before taking counters.
        if controller:
            controller.pause("Session finished")
        camera.close()
        tracker.close()
        if hand_tracker:
            hand_tracker.close()
        measured_duration = time.monotonic() - started
        summary = {
            "camera_index": args.camera,
            "backend": args.backend,
            "model": args.model.name,
            "camera_frames": camera.frames,
            "elapsed_seconds": round(measured_duration, 2),
            "frame_size": [int(raw.shape[1]), int(raw.shape[0])],
            "observed_pose_results": count,
            "results_with_person": person_count,
            "upper_body_ready_results": ready_count,
            "maximum_visible_required_joints": maximum_visible,
            "last_status": status,
            "last_joint_status": {
                label: joint_reason(landmarks[index], args.confidence) if landmarks and age <= STALE_SECONDS else "UNAVAILABLE"
                for index, label in JOINTS.items()
            },
            "visual_acceptance": "pending user check",
            "environment": environment(args.model),
            "configuration": {"confidence": args.confidence, "headless": args.headless,
                              "warmup_results": args.warmup, "control_enabled": args.control,
                              "movement_sensitivity": args.sensitivity},
            "pipeline": tracker.metrics.summary(camera.frames, measured_duration),
        }
        if hand_tracker:
            summary["hand_pipeline"] = hand_tracker.summary()
            summary["hand_model"] = {"name": hand_model.name,
                                     "sha256": hashlib.sha256(hand_model.read_bytes()).hexdigest()}
            summary["practice"] = practice
            summary["recognized_attacks"] = controller.attack_counts
            summary["input_press_counts"] = controller.input_press_counts
            summary["attack_sensitivity"] = {"initial": getattr(args, "attack_sensitivity", DEFAULT_ATTACK_SENSITIVITY),
                                              "final": controller.strikes.sensitivity}
            hand_tracker = None
        tracker = None
        camera = None
        if args.report:
            write_report(args.report, summary)
            print(f"Report saved: {args.report}", flush=True)
        print(json.dumps(summary, indent=2), flush=True)
    finally:
        try:
            if controller:
                controller.pause("Session closed")
        finally:
            try:
                if camera is not None:
                    camera.close()
            finally:
                try:
                    if tracker is not None:
                        tracker.close()
                finally:
                    try:
                        if hand_tracker is not None:
                            hand_tracker.close()
                    finally:
                        if not args.headless:
                            cv2.destroyAllWindows()


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0, help="Webcam index (default: 0)")
    parser.add_argument("--backend", choices=("dshow", "msmf"), default="dshow")
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--hand-model", type=Path, default=HAND_MODEL)
    parser.add_argument("--confidence", type=float, default=0.6,
                        help="Required joint visibility/presence threshold (default: 0.6)")
    parser.add_argument("--headless", action="store_true", help="Camera/model diagnostic without a preview")
    parser.add_argument("--seconds", type=float, default=0, help="Stop after N seconds (default: until quit)")
    parser.add_argument("--warmup", type=int, default=15, help="Initial completed results excluded from timing statistics")
    parser.add_argument("--report", type=Path, help="Write aggregate JSON metrics to a new file (no frames)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--control", action="store_true", help="Enable game inputs; starts paused")
    mode.add_argument("--practice", action="store_true", help="Test gestures and counters without sending any desktop keys")
    parser.add_argument("--controls", type=Path, default=default_controls(), help="PPSSPP controls.ini path")
    parser.add_argument("--sensitivity", type=float, default=1.0, help="Movement sensitivity, 0.5-2 (higher needs less movement)")
    parser.add_argument("--attack-sensitivity", type=float, default=DEFAULT_ATTACK_SENSITIVITY,
                        help="Attack reach sensitivity, 0.5-2 (default: 1.6); independent of detection confidence")
    args = parser.parse_args()
    if args.camera < 0 or not np.isfinite(args.confidence) or not 0 <= args.confidence <= 1:
        parser.error("--camera must be nonnegative; --confidence must be between 0 and 1.")
    if not np.isfinite(args.seconds) or args.seconds < 0 or (args.headless and args.seconds == 0):
        parser.error("Use a finite positive --seconds value with --headless.")
    if args.warmup < 0:
        parser.error("--warmup must be nonnegative.")
    if args.report and args.report.exists():
        parser.error("Report already exists; choose a new filename.")
    if args.control and args.headless:
        parser.error("--control requires the interactive preview for calibration.")
    if not np.isfinite(args.sensitivity) or not .5 <= args.sensitivity <= 2:
        parser.error("--sensitivity must be between 0.5 and 2.")
    if not np.isfinite(args.attack_sensitivity) or not .5 <= args.attack_sensitivity <= 2:
        parser.error("--attack-sensitivity must be between 0.5 and 2.")
    return args


if __name__ == "__main__":
    try:
        run(arguments())
    except KeyboardInterrupt:
        print("Tracking stopped.")
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
