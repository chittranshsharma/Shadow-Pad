import unittest
from types import SimpleNamespace

from tracking_quality import JOINTS, assess, framing_hints, joint_reason, tracking_label


def pose():
    return [SimpleNamespace(x=0.5, y=0.5, visibility=0.95, presence=0.95)
            for _ in range(33)]


class TrackingQualityTests(unittest.TestCase):
    def test_upper_body_does_not_require_visible_legs_or_hips(self):
        points = pose()
        for point in points[23:]:
            point.y = 2.0
            point.visibility = 0.0
        status, visible = assess(points, 0.05)
        self.assertEqual(status, "UPPER BODY READY")
        self.assertEqual(visible, set(JOINTS))

    def test_hidden_wrist_is_partial(self):
        points = pose()
        points[15].visibility = 0.2
        status, visible = assess(points, 0.05)
        self.assertEqual(status, "PARTIAL UPPER BODY")
        self.assertNotIn(15, visible)

    def test_confident_but_out_of_frame_joint_is_missing(self):
        points = pose()
        points[16].x = 1.1
        self.assertNotIn(16, assess(points, 0.05)[1])

    def test_low_presence_is_missing(self):
        points = pose()
        points[11].presence = 0.1
        self.assertNotIn(11, assess(points, 0.05)[1])

    def test_stale_pose_cannot_be_ready(self):
        self.assertEqual(assess(pose(), 0.6), ("TRACKING STALE", set()))

    def test_no_person(self):
        self.assertEqual(assess(None, 0.05), ("NO PERSON DETECTED", set()))

    def test_nonfinite_and_missing_confidence_are_rejected(self):
        for value in (float("nan"), float("inf"), None):
            points = pose()
            points[13].visibility = value
            self.assertNotIn(13, assess(points, 0.05)[1])

    def test_invalid_result_age_is_stale(self):
        for age in (float("nan"), float("inf"), -0.1):
            self.assertEqual(assess(pose(), age)[1], set())

    def test_wrists_below_frame_prompt_raising_hands(self):
        points = pose()
        points[15].y = points[16].y = 1.2
        self.assertEqual(joint_reason(points[15]), "BELOW FRAME")
        self.assertIn("Raise your hands", " ".join(framing_hints(points, 0.03)))

    def test_side_crop_prompts_moving_back(self):
        points = pose()
        points[11].x = -0.1
        self.assertIn("chair back", " ".join(framing_hints(points, 0.03)))

    def test_stale_hints_do_not_suggest_pose_adjustments(self):
        self.assertEqual(len(framing_hints(pose(), 1)), 1)
        self.assertIn("fresh tracking", framing_hints(pose(), 1)[0])

    def test_low_confidence_is_not_claimed_to_be_outside_frame(self):
        points = pose()
        points[13].visibility = .1
        self.assertEqual(joint_reason(points[13]), "LOW CONFIDENCE")

    def test_tracking_label_does_not_call_hidden_elbows_reliable(self):
        label = tracking_label({11, 12, 15, 16}, "PARTIAL UPPER BODY")
        self.assertIn("elbows uncertain", label)
        self.assertNotIn("ready", label)


if __name__ == "__main__":
    unittest.main()
