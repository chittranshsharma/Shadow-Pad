"""Local hand classification with one in-flight request and one latest result."""

import math
from pathlib import Path
import threading
import time
from collections import Counter

import cv2
import mediapipe as mp

from attacks import HandObservation
from performance import TimingWindow
from hand_identity import HandIdentity


HAND_MODEL = Path(__file__).resolve().parent / "models" / "gesture_recognizer.task"


def finger_shape(points):
    """Recognize folded/extended fingers independent of hand rotation."""
    if len(points) != 21:
        return None
    xyz = [(p.x, p.y, p.z) for p in points]
    if not all(math.isfinite(value) for point in xyz for value in point):
        return None
    folded = extended = 0
    for mcp, pip, tip in ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)):
        first = tuple(a - b for a, b in zip(xyz[mcp], xyz[pip]))
        second = tuple(a - b for a, b in zip(xyz[tip], xyz[pip]))
        denominator = math.dist(first, (0, 0, 0)) * math.dist(second, (0, 0, 0))
        palm_distance = math.dist(xyz[mcp], xyz[0])
        if denominator < 1e-10 or palm_distance < 1e-6:
            return None
        cosine = max(-1, min(1, sum(a*b for a, b in zip(first, second)) / denominator))
        angle = math.degrees(math.acos(cosine))
        reach = math.dist(xyz[tip], xyz[0]) / palm_distance
        folded += angle < 115 and reach < 1.05
        extended += angle > 150 and reach > 1.35
    if folded >= 3 and extended == 0:
        return "Closed_Fist"
    if extended >= 3 and folded == 0:
        return "Open_Palm"
    return None


def extract_hands(result, aspect, diagnostics=None):
    diagnostics = diagnostics if diagnostics is not None else Counter()
    diagnostics["raw_hands"] += len(result.hand_landmarks)
    observations, outlines = [], []
    for index, points in enumerate(result.hand_landmarks):
        if len(points) != 21 or index >= len(result.handedness) or index >= len(result.gestures):
            continue
        if not result.handedness[index] or not result.gestures[index]:
            continue
        handedness = max(result.handedness[index], key=lambda category: category.score)
        gesture = max(result.gestures[index], key=lambda category: category.score)
        shape, score, source = gesture.category_name, gesture.score, "model"
        world = getattr(result, "hand_world_landmarks", [])
        fingers_in_frame = all(math.isfinite(p.x) and math.isfinite(p.y) and 0 <= p.x <= 1 and 0 <= p.y <= 1 for p in points)
        geometry = finger_shape(world[index]) if index < len(world) and fingers_in_frame else None
        if geometry and (shape == "None" or (shape == geometry and score < .6)):
            shape, score, source = geometry, None, "geometry"
        if handedness.category_name not in ("Left", "Right"):
            diagnostics["identity_unresolved"] += 1
            continue
        palm = [points[i] for i in (0, 5, 9, 13, 17)]
        if not all(math.isfinite(p.x) and math.isfinite(p.y) and 0 <= p.x <= 1 and 0 <= p.y <= 1 for p in palm):
            diagnostics["palm_outside_frame"] += 1
            continue
        if handedness.score < .7:
            diagnostics["uncertain_model_handedness"] += 1
        def distance(a, b):
            return math.hypot(points[a].x - points[b].x, (points[a].y - points[b].y) * aspect)
        observation = HandObservation(handedness.category_name, shape, score,
                                      sum(p.x for p in palm) / 5, sum(p.y for p in palm) / 5,
                                      distance(5, 17), distance(0, 9), source,
                                      points[0].x, points[0].y, handedness.score)
        observations.append(observation)
        outlines.append((observation, tuple((p.x, p.y) for p in palm)))
    return observations, outlines


class HandTracker:
    def __init__(self, model=HAND_MODEL):
        self.lock = threading.Lock()
        self.busy = False
        self.closed = False
        self.latest = None
        self.pending_frame = None
        self.pending_references = {}
        self.identity = HandIdentity()
        self.diagnostics = Counter()
        self.submitted_at = 0
        self.results = 0
        self.recognized_results = 0
        self.error = None
        self.timing = TimingWindow()
        options = mp.tasks.vision.GestureRecognizerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
            running_mode=mp.tasks.vision.RunningMode.LIVE_STREAM,
            num_hands=2,
            min_hand_detection_confidence=.6,
            min_hand_presence_confidence=.6,
            min_tracking_confidence=.6,
            result_callback=self._result,
        )
        self.recognizer = mp.tasks.vision.GestureRecognizer.create_from_options(options)

    def _result(self, result, output_image, timestamp_ms):
        with self.lock:
            try:
                frame = self.pending_frame
                diagnostics = Counter()
                observations, outlines = extract_hands(result, frame.shape[0] / frame.shape[1], diagnostics)
                observations = self.identity.assign(observations, self.pending_references, timestamp_ms / 1000)
                outlines = [(hand, outline[1]) for hand, outline in zip(observations, outlines)]
                diagnostics["assigned_hands"] = sum(hand.side != "Unknown" for hand in observations)
                self.diagnostics.update(diagnostics)
                elapsed = (time.monotonic() - self.submitted_at) * 1000
                self.timing.add(elapsed)
                self.results += 1
                self.recognized_results += bool(observations)
                self.latest = (timestamp_ms, observations, outlines, frame, dict(diagnostics))
            except Exception as error:
                self.error = str(error)
            finally:
                self.pending_frame = None
                self.busy = False

    def submit(self, frame, timestamp_ms, references=None):
        with self.lock:
            if self.error:
                raise RuntimeError(f"Hand tracker failed: {self.error}")
            if self.busy:
                if time.monotonic() - self.submitted_at > 5:
                    raise RuntimeError("Hand tracker stalled. Restart ShadowPad.")
                return False
            # Official hand example uses mirrored input for handedness labels.
            self.pending_frame = cv2.flip(frame, 1)
            self.pending_references = references or {}
            self.busy = True
            self.submitted_at = time.monotonic()
            image = mp.Image(image_format=mp.ImageFormat.SRGB,
                             data=cv2.cvtColor(self.pending_frame, cv2.COLOR_BGR2RGB))
        try:
            self.recognizer.recognize_async(image, timestamp_ms)
        except BaseException:
            with self.lock:
                self.busy = False
                self.pending_frame = None
            raise
        return True

    def snapshot(self):
        with self.lock:
            if self.error:
                raise RuntimeError(f"Hand tracker failed: {self.error}")
            return self.latest

    def summary(self):
        with self.lock:
            return {"completed_results": self.results, "results_with_hands": self.recognized_results,
                    "submit_to_result": self.timing.summary(), "detection_counts": dict(self.diagnostics)}

    def close(self):
        if not self.closed:
            self.recognizer.close()
            self.closed = True
