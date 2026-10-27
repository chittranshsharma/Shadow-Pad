from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from hand_tracking import extract_hands
from movement import MovementController
from ppsspp_input import CONTROL_ACTIONS, PracticeKeyboard
from webcam_tracker import control_overlay, run


def result(gesture="Closed_Fist", score=.95):
    points = [SimpleNamespace(x=.4, y=.5) for _ in range(21)]
    points[0] = SimpleNamespace(x=.4, y=.6)
    points[5] = SimpleNamespace(x=.36, y=.5)
    points[9] = SimpleNamespace(x=.4, y=.48)
    points[17] = SimpleNamespace(x=.44, y=.5)
    return SimpleNamespace(hand_landmarks=[points],
                           handedness=[[SimpleNamespace(category_name="Left", score=.98)]],
                           gestures=[[SimpleNamespace(category_name=gesture, score=score)]])


class HandTrackingTests(unittest.TestCase):
    def test_extracts_palm_geometry_with_pixel_aspect_correction(self):
        observations, outlines = extract_hands(result(), .75)
        self.assertEqual(len(observations), 1)
        self.assertTrue(observations[0].valid())
        self.assertAlmostEqual(observations[0].width, .08)
        self.assertAlmostEqual(observations[0].length, .09)
        self.assertEqual(len(outlines[0][1]), 5)

    def test_uncertain_classification_and_other_shapes_are_not_attacks(self):
        for gesture, score in (("Closed_Fist", .5), ("Pointing_Up", .99), ("None", .99)):
            observations, _ = extract_hands(result(gesture, score), .75)
            self.assertFalse(observations[0].valid())

    def test_cropped_hands_are_rejected(self):
        cropped = result()
        cropped.hand_landmarks[0][8].x = 1.1
        self.assertEqual(extract_hands(cropped, .75), ([], []))

    def test_practice_never_constructs_native_keyboard(self):
        class CameraStop(Exception):
            pass
        args = SimpleNamespace(model=Path(__file__), hand_model=Path(__file__), control=False,
                               practice=True, sensitivity=1, confidence=.6, warmup=2,
                               camera=0, backend="dshow", headless=True)
        with patch("webcam_tracker.WindowsKeyboard", side_effect=AssertionError("native input in practice")) as native:
            with patch("webcam_tracker.Tracker"), patch("webcam_tracker.HandTracker"):
                with patch("webcam_tracker.Camera", side_effect=CameraStop):
                    with self.assertRaises(CameraStop):
                        run(args)
            native.assert_not_called()

    def test_overlay_renders_hand_labels_and_keeps_canvas_size(self):
        controller = MovementController(PracticeKeyboard(), {action: (index + 1, action)
                                        for index, action in enumerate(CONTROL_ACTIONS)})
        _, outlines = extract_hands(result(), .75)
        frame = np.full((480, 640, 3), 100, dtype=np.uint8)
        image = control_overlay(frame, controller, outlines, practice=True)
        self.assertEqual(image.shape, (480, 640, 3))
        np.testing.assert_array_equal(image[400:, 0], np.full((80, 3), 24, dtype=np.uint8))


if __name__ == "__main__":
    unittest.main()
