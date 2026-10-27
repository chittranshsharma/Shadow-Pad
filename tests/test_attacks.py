import random
import unittest

from attacks import HandAttacks, HandObservation


def hand(scale=1, side="Left", gesture="Closed_Fist", **changes):
    values = dict(side=side, gesture=gesture, score=.95, x=.3 if side == "Left" else .7,
                  y=.5, width=.05 * scale, length=.08 * scale)
    values.update(changes)
    return HandObservation(**values)


class AttackTests(unittest.TestCase):
    def setUp(self):
        self.engine = HandAttacks()
        self.now = 0
        self.body = (.5, .4, .4)

    def feed(self, observation=None, dt=.05, body=None):
        self.now += dt
        return self.engine.update([] if observation is None else [observation], self.now,
                                  self.body if body is None else body)

    def guard(self, side="Left", gesture="Closed_Fist"):
        for _ in range(14):
            self.assertEqual(self.feed(hand(side=side, gesture=gesture)), set())
        self.assertEqual(self.engine.hands[side].phase, "ready")

    def stroke(self, side="Left", gesture="Closed_Fist"):
        events = []
        for scale in (1.08, 1.16, 1.28, 1.45, 1.6, 1.6):
            events.extend(self.feed(hand(scale, side, gesture)))
        return events

    def test_four_forward_attacks_fire_once_and_require_return(self):
        for side, gesture, action in (("Left", "Closed_Fist", "Square"),
                                      ("Right", "Closed_Fist", "Triangle"),
                                      ("Left", "Open_Palm", "Cross"),
                                      ("Right", "Open_Palm", "Circle")):
            with self.subTest(action=action):
                self.engine.reset()
                self.guard(side, gesture)
                self.assertEqual(self.stroke(side, gesture), [action])
                for _ in range(20):
                    self.assertEqual(self.feed(hand(1.6, side, gesture)), set())
                for _ in range(12):
                    self.assertEqual(self.feed(hand(1, side, gesture)), set())
                self.assertEqual(self.stroke(side, gesture), [action])

    def test_idle_jitter_does_not_fire_over_thirty_seconds(self):
        self.guard()
        rng = random.Random(7)
        for _ in range(600):
            self.assertEqual(self.feed(hand(1 + rng.uniform(-.06, .06),
                                            x=.3 + rng.uniform(-.008, .008))), set())

    def test_consistent_sixty_percent_fist_can_learn_guard(self):
        for index in range(20):
            self.assertEqual(self.feed(hand(1 + (.04 if index % 2 else -.04), score=.62)), set())
        self.assertEqual(self.engine.hands["Left"].phase, "ready")

    def test_uncertain_shape_explains_why_guard_is_blocked(self):
        for _ in range(20):
            self.assertEqual(self.feed(hand(score=.55)), set())
        self.assertIsNone(self.engine.hands["Left"].anchor)
        self.assertIn("shape uncertain", self.engine.hands["Left"].reason)

    def test_one_low_confidence_frame_does_not_erase_guard_learning(self):
        for _ in range(5):
            self.feed(hand())
        self.feed(hand(score=.4))
        for _ in range(6):
            self.feed(hand())
        self.assertEqual(self.engine.hands["Left"].phase, "ready")

    def test_guard_has_no_chest_height_box(self):
        for _ in range(14):
            self.assertEqual(self.feed(hand(y=.9)), set())
        self.assertEqual(self.engine.hands["Left"].phase, "ready")

    def test_one_frame_scale_spike_does_not_fire(self):
        self.guard()
        self.assertEqual(self.feed(hand(1.9)), set())
        for _ in range(6):
            self.assertEqual(self.feed(hand()), set())

    def test_rotating_hand_one_dimension_only_does_not_fire(self):
        self.guard()
        for scale in (1.1, 1.3, 1.5, 1.7, 1.9):
            self.assertEqual(self.feed(hand(width=.05 * scale)), set())

    def test_distorted_palm_aspect_does_not_count_as_forward_push(self):
        self.guard()
        for scale in (1.1, 1.3, 1.5, 1.7, 1.9, 1.9):
            self.assertEqual(self.feed(hand(width=.05 * scale, length=.08 * (1 + (scale-1)*.25))), set())

    def test_opening_fist_does_not_count_as_kick(self):
        self.guard()
        for _ in range(20):
            self.assertEqual(self.feed(hand(1.7, gesture="Open_Palm")), set())
        self.assertEqual(self.engine.hands["Left"].phase, "ready")

    def test_lowering_hand_does_not_count_as_kick(self):
        self.guard()
        for y in (.53, .57, .63, .7, .8):
            self.assertEqual(self.feed(hand(y=y)), set())

    def test_slow_scale_drift_does_not_count_as_strike(self):
        self.guard()
        for step in range(100):
            self.assertEqual(self.feed(hand(1 + step * .006)), set())

    def test_reacquired_extended_hand_does_not_fire(self):
        self.guard()
        self.feed()
        for _ in range(20):
            self.assertEqual(self.feed(hand(1.6)), set())
        for _ in range(12):
            self.feed(hand())
        self.assertEqual(self.stroke(), ["Square"])

    def test_leaning_towards_camera_does_not_count_as_hand_push(self):
        self.guard()
        for scale in (1.08, 1.16, 1.28, 1.45, 1.6):
            self.assertEqual(self.feed(hand(scale), body=(.5, .4, .4 * scale)), set())

    def test_duplicate_identity_and_invalid_confidence_do_not_fire(self):
        self.guard()
        self.now += .05
        self.assertEqual(self.engine.update([hand(1.6), hand(1.6)], self.now, self.body), set())
        self.assertEqual(self.feed(hand(1.8, score=.2)), set())

    def test_same_timestamp_does_not_advance_motion(self):
        self.guard()
        for _ in range(10):
            self.assertEqual(self.engine.update([hand(1.6)], self.now, self.body), set())

    def test_tracking_teleport_does_not_fire(self):
        self.guard()
        for scale in (1.2, 1.4, 1.6, 1.8):
            self.assertEqual(self.feed(hand(scale, x=.8)), set())


if __name__ == "__main__":
    unittest.main()
