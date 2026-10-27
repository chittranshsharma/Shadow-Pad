"""Local hand classification with one in-flight request and one latest result."""

import math
from pathlib import Path
import threading
import time

import cv2
import mediapipe as mp

from attacks import HandObservation
from performance import TimingWindow


HAND_MODEL = Path(__file__).resolve().parent / "models" / "gesture_recognizer.task"


def extract_hands(result, aspect):
    observations, outlines = [], []
    for index, points in enumerate(result.hand_landmarks):
        if len(points) != 21 or index >= len(result.handedness) or index >= len(result.gestures):
            continue
        if not result.handedness[index] or not result.gestures[index]:
            continue
        handedness = max(result.handedness[index], key=lambda category: category.score)
        gesture = max(result.gestures[index], key=lambda category: category.score)
        if handedness.category_name not in ("Left", "Right") or handedness.score < .7:
            continue
        if not all(math.isfinite(p.x) and math.isfinite(p.y) and 0 <= p.x <= 1 and 0 <= p.y <= 1 for p in points):
            continue
        palm = [points[i] for i in (0, 5, 9, 13, 17)]
        def distance(a, b):
            return math.hypot(points[a].x - points[b].x, (points[a].y - points[b].y) * aspect)
        observation = HandObservation(handedness.category_name, gesture.category_name, gesture.score,
                                      sum(p.x for p in palm) / 5, sum(p.y for p in palm) / 5,
                                      distance(5, 17), distance(0, 9))
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
                observations, outlines = extract_hands(result, frame.shape[0] / frame.shape[1])
                elapsed = (time.monotonic() - self.submitted_at) * 1000
                self.timing.add(elapsed)
                self.results += 1
                self.recognized_results += bool(observations)
                self.latest = (timestamp_ms, observations, outlines, frame)
            except Exception as error:
                self.error = str(error)
            finally:
                self.pending_frame = None
                self.busy = False

    def submit(self, frame, timestamp_ms):
        with self.lock:
            if self.error:
                raise RuntimeError(f"Hand tracker failed: {self.error}")
            if self.busy:
                if time.monotonic() - self.submitted_at > 5:
                    raise RuntimeError("Hand tracker stalled. Restart ShadowPad.")
                return False
            # Official hand example uses mirrored input for handedness labels.
            self.pending_frame = cv2.flip(frame, 1)
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
                    "submit_to_result": self.timing.summary()}

    def close(self):
        if not self.closed:
            self.recognizer.close()
            self.closed = True
