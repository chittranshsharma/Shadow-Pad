from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from hand_tracking import extract_hands, finger_shape
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


def finger_points(extended=()):
    points = [SimpleNamespace(x=0., y=0., z=0.) for _ in range(21)]
    for number, (mcp, pip, tip) in enumerate(((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20))):
        x = -.03 + number * .02
        points[mcp] = SimpleNamespace(x=x, y=.04, z=0.)
        points[pip] = SimpleNamespace(x=x, y=.065, z=0.)
        points[tip] = SimpleNamespace(x=x, y=.11 if number in extended else .025,
                                      z=0. if number in extended else -.01)
    return points


class HandTrackingTests(unittest.TestCase):
    def test_closed_fist_geometry_is_rotation_independent(self):
        points = finger_points()
        self.assertEqual(finger_shape(points), "Closed_Fist")
        rotated = [SimpleNamespace(x=p.z, y=p.x, z=p.y) for p in points]
        self.assertEqual(finger_shape(rotated), "Closed_Fist")

    def test_extended_palm_and_pointing_hand_are_distinguished(self):
        self.assertEqual(finger_shape(finger_points(range(4))), "Open_Palm")
        self.assertIsNone(finger_shape(finger_points((0,))))

    def test_none_label_can_use_definite_finger_curl_without_fake_score(self):
        detected = result("None", .95)
        detected.hand_world_landmarks = [finger_points()]
        hands, _ = extract_hands(detected, .75)
        self.assertEqual(hands[0].gesture, "Closed_Fist")
        self.assertEqual(hands[0].source, "geometry")
        self.assertIsNone(hands[0].score)
        self.assertTrue(hands[0].valid())

    def test_extracts_palm_geometry_with_pixel_aspect_correction(self):
        observations, outlines = extract_hands(result(), .75)
        self.assertEqual(len(observations), 1)
        self.assertTrue(observations[0].valid())
        self.assertAlmostEqual(observations[0].width, .08)
        self.assertAlmostEqual(observations[0].length, .09)
        self.assertEqual(len(outlines[0][1]), 5)

    def test_uncertain_classification_and_other_shapes_are_not_attacks(self):
        for gesture, score in (("Closed_Fist", .4), ("Pointing_Up", .99), ("None", .99)):
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
