from types import SimpleNamespace
import unittest

from movement import Movement, MovementController, Neutral


def shoulders(x=.5, y=.4):
    points = [SimpleNamespace(x=.5, y=.5, visibility=0., presence=0.) for _ in range(33)]
    points[11] = SimpleNamespace(x=x-.2, y=y, visibility=.95, presence=.95)
    points[12] = SimpleNamespace(x=x+.2, y=y, visibility=.95, presence=.95)
    return points


class MovementTests(unittest.TestCase):
    def engine(self):
        movement = Movement()
        movement.neutral = Neutral(.5, .4, .4)
        return movement

    def test_calibration_requires_stable_samples_for_two_seconds(self):
        movement = Movement()
        movement.calibrate()
        for index in range(10):
            movement.update(shoulders(), .01, index*.21)
        self.assertIsNone(movement.neutral)
        movement.update(shoulders(), .01, 2.1)
        self.assertIsNotNone(movement.neutral)
        self.assertFalse(movement.calibrating)

    def test_unstable_calibration_is_not_accepted(self):
        movement = Movement()
        movement.calibrate()
        for index in range(12):
            movement.update(shoulders(x=.5 + .1*(index%2)), .01, index*.21)
        self.assertIsNone(movement.neutral)

    def test_mirrored_left_and_right_without_elbows(self):
        movement = self.engine()
        self.assertEqual(movement.update(shoulders(x=.6), .01, 3)[0], {"Left"})
        self.assertEqual(movement.update(shoulders(x=.4), .01, 3.1)[0], {"Right"})

    def test_horizontal_hysteresis_and_neutral_release(self):
        movement = self.engine()
        movement.update(shoulders(x=.6), .01, 3)
        self.assertEqual(movement.update(shoulders(x=.56), .01, 3.1)[0], {"Left"})
        self.assertEqual(movement.update(shoulders(x=.53), .01, 3.2)[0], set())

    def test_duck_can_combine_with_left_and_releases_at_neutral(self):
        movement = self.engine()
        self.assertEqual(movement.update(shoulders(x=.6, y=.52), .01, 3)[0], {"Left", "Down"})
        self.assertEqual(movement.update(shoulders(), .01, 3.1)[0], set())

    def test_jump_is_one_pulse_and_rearms_after_return(self):
        movement = self.engine()
        self.assertEqual(movement.update(shoulders(y=.28), .01, 3)[0], {"Up"})
        self.assertEqual(movement.update(shoulders(y=.28), .01, 3.2)[0], {"Up"})
        self.assertEqual(movement.update(shoulders(y=.28), .01, 3.4)[0], set())
        movement.update(shoulders(), .01, 3.5)
        self.assertEqual(movement.update(shoulders(y=.28), .01, 3.6)[0], {"Up"})

    def test_stale_or_missing_shoulders_release_everything(self):
        movement = self.engine()
        movement.update(shoulders(x=.6, y=.52), .01, 3)
        self.assertEqual(movement.update(shoulders(), .7, 3.1), (set(), False))
        self.assertEqual(movement.update(None, .01, 3.2), (set(), False))

    def test_higher_sensitivity_needs_less_motion(self):
        movement = Movement(sensitivity=2)
        movement.neutral = Neutral(.5, .4, .4)
        self.assertEqual(movement.update(shoulders(x=.55), .01, 3)[0], {"Left"})


class FakeKeyboard:
    def __init__(self):
        self.focus = (123, 1)
        self.toggle = False
        self.modifiers = False
        self.keys = set()

    def foreground_ppsspp(self):
        return self.focus

    def pause_requested(self):
        return self.toggle

    def modifiers_down(self):
        return self.modifiers

    def press(self, vk, target):
        self.keys.add(vk)

    def release(self, vk=None):
        if vk is None:
            self.keys.clear()
        else:
            self.keys.discard(vk)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.keyboard = FakeKeyboard()
        self.controller = MovementController(self.keyboard, {"Left": (37,"Left"), "Right": (39,"Right"),
                                                            "Up": (38,"Up"), "Down": (40,"Down")})
        self.controller.movement.neutral = Neutral(.5,.4,.4)
        self.controller.on_pose(shoulders(), .01, 3)

    def arm(self):
        self.keyboard.toggle = True
        self.keyboard.modifiers = True
        self.controller.tick(3.01)
        self.keyboard.toggle = False
        self.keyboard.modifiers = False
        self.controller.tick(3.02)

    def test_starts_paused_and_requires_emulator_focus_to_arm(self):
        self.assertFalse(self.controller.armed)
        self.keyboard.focus = None
        self.arm()
        self.assertFalse(self.controller.armed)
        self.assertEqual(self.keyboard.keys, set())

    def test_combined_movement_and_focus_loss_release(self):
        self.arm()
        self.controller.on_pose(shoulders(x=.6,y=.52), .01, 3.05)
        self.controller.tick(3.06)
        self.assertEqual(self.keyboard.keys, {37,40})
        self.keyboard.focus = None
        self.controller.tick(3.07)
        self.assertEqual(self.keyboard.keys, set())
        self.assertFalse(self.controller.armed)

    def test_stale_tracking_disarms(self):
        self.arm()
        self.controller.tick(3.8)
        self.assertFalse(self.controller.armed)
        self.assertEqual(self.keyboard.keys, set())

    def test_invalid_shoulders_prevent_arming_with_a_recent_previous_pose(self):
        self.controller.on_pose(None, .01, 3.01)
        self.arm()
        self.assertFalse(self.controller.armed)

    def test_toggle_pauses_and_does_not_repeat_while_held(self):
        self.arm()
        self.keyboard.toggle = True
        self.controller.tick(3.03)
        self.controller.tick(3.04)
        self.assertFalse(self.controller.armed)

    def test_countdown_arms_after_game_receives_focus(self):
        self.keyboard.focus = None
        self.controller.arm_countdown(3, seconds=5)
        self.controller.tick(7)
        self.assertFalse(self.controller.armed)
        self.keyboard.focus = (123, 1)
        self.controller.on_pose(shoulders(), .01, 7.9)
        self.controller.tick(8)
        self.assertTrue(self.controller.armed)
        self.controller.on_pose(shoulders(x=.6), .01, 8.01)
        self.controller.tick(8.02)
        self.assertEqual(self.keyboard.keys, {37})

    def test_failed_arm_reason_survives_new_pose(self):
        self.keyboard.focus = None
        self.controller.arm_countdown(3, seconds=1)
        self.controller.on_pose(shoulders(), .01, 3.5)
        self.controller.tick(4)
        self.assertIn("PPSSPP was not the active window", self.controller.status)
        self.controller.on_pose(shoulders(), .01, 4.1)
        self.assertIn("PPSSPP was not the active window", self.controller.status)


if __name__ == "__main__":
    unittest.main()
