from types import SimpleNamespace
import unittest

from movement import ArmStrikes, Movement, MovementController, Neutral


def shoulders(x=.5, y=.4):
    points = [SimpleNamespace(x=.5, y=.5, visibility=0., presence=0.) for _ in range(33)]
    points[11] = SimpleNamespace(x=x-.2, y=y, visibility=.95, presence=.95)
    points[12] = SimpleNamespace(x=x+.2, y=y, visibility=.95, presence=.95)
    return points


def hands(left_x=.24, left_y=.52, right_x=.76, right_y=.52):
    points = shoulders()
    points[15] = SimpleNamespace(x=left_x, y=left_y, visibility=.95, presence=.95)
    points[16] = SimpleNamespace(x=right_x, y=right_y, visibility=.95, presence=.95)
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

    def test_calibration_records_head_when_visible(self):
        movement = Movement()
        movement.calibrate()
        for index in range(11):
            points = shoulders()
            points[0] = SimpleNamespace(x=.5, y=.18, visibility=.95, presence=.95)
            movement.update(points, .01, index*.21)
        self.assertAlmostEqual(movement.neutral.head_y, .18)

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

    def test_small_seated_dip_ducks_with_hysteresis(self):
        movement = self.engine()
        self.assertEqual(movement.update(shoulders(y=.47), .01, 3)[0], {"Down"})
        self.assertEqual(movement.update(shoulders(y=.44), .01, 3.1)[0], {"Down"})
        self.assertEqual(movement.update(shoulders(y=.42), .01, 3.2)[0], set())

    def test_head_lowering_ducks_when_shoulders_barely_move(self):
        movement = self.engine()
        movement.neutral = Neutral(.5, .4, .4, .18)
        points = shoulders(y=.42)
        points[0] = SimpleNamespace(x=.5, y=.30, visibility=.95, presence=.95)
        self.assertEqual(movement.update(points, .01, 3)[0], {"Down"})
        points[0].y = .18
        self.assertEqual(movement.update(points, .01, 3.1)[0], set())

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
                                                            "Up": (38,"Up"), "Down": (40,"Down"),
                                                            "Square": (65,"A"), "Triangle": (83,"S"),
                                                            "Cross": (90,"Z"), "Circle": (88,"X")})
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

    def test_stale_tracking_releases_then_recovers_without_rearming(self):
        self.arm()
        self.controller.on_pose(shoulders(x=.6), .01, 3.05)
        self.controller.tick(3.06)
        self.assertEqual(self.keyboard.keys, {37})
        self.controller.tick(3.8)
        self.assertTrue(self.controller.armed)
        self.assertIsNotNone(self.controller.movement.neutral)
        self.assertEqual(self.keyboard.keys, set())
        self.controller.on_pose(shoulders(x=.6), .01, 3.9)
        self.controller.tick(3.91)
        self.assertEqual(self.keyboard.keys, set())
        self.controller.on_pose(shoulders(x=.6), .01, 4.0)
        self.controller.tick(4.01)
        self.assertEqual(self.keyboard.keys, {37})

    def test_single_invalid_pose_releases_and_recovers(self):
        self.arm()
        self.controller.on_pose(shoulders(x=.6), .01, 3.05)
        self.controller.tick(3.06)
        self.controller.on_pose(None, .01, 3.1)
        self.controller.tick(3.11)
        self.assertTrue(self.controller.armed)
        self.assertEqual(self.keyboard.keys, set())
        self.controller.on_pose(shoulders(x=.6), .01, 3.2)
        self.controller.tick(3.21)
        self.assertEqual(self.keyboard.keys, set())
        self.controller.on_pose(shoulders(x=.6), .01, 3.3)
        self.controller.tick(3.31)
        self.assertEqual(self.keyboard.keys, {37})

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

    def test_attack_tap_while_movement_is_held(self):
        self.arm()
        self.controller.on_pose(hands(), .01, 3.05)
        self.controller.on_pose(hands(), .01, 3.07)
        moving = hands(left_x=.24, right_x=.76)
        moving[11].x += .1
        moving[12].x += .1
        moving[15].x += .1
        moving[16].x += .1
        self.controller.on_pose(moving, .01, 3.10)
        self.controller.tick(3.11)
        self.assertIn(37, self.keyboard.keys)
        self.controller.on_pose(hands(left_x=.40), .01, 3.12)
        self.controller.tick(3.13)
        self.assertNotIn(65, self.keyboard.keys)
        self.controller.on_pose(hands(left_x=.40), .01, 3.15)
        self.controller.tick(3.16)
        self.assertIn(65, self.keyboard.keys)
        self.controller.tick(3.30)
        self.assertNotIn(65, self.keyboard.keys)


class ArmStrikeTests(unittest.TestCase):
    def test_each_hand_has_punch_and_kick_and_requires_return(self):
        strikes = ArmStrikes()
        self.assertEqual(strikes.update(hands(), .01), set())
        self.assertEqual(strikes.update(hands(), .01), set())
        self.assertEqual(strikes.update(hands(), .01), set())
        self.assertEqual(strikes.ready, 2)
        self.assertEqual(strikes.update(hands(left_x=.40), .01), set())
        self.assertEqual(strikes.update(hands(left_x=.40), .01), {"Square"})
        self.assertEqual(strikes.update(hands(left_x=.40), .01), set())
        self.assertEqual(strikes.update(hands(), .01), set())
        self.assertEqual(strikes.update(hands(), .01), set())
        self.assertEqual(strikes.update(hands(left_y=.67), .01), set())
        self.assertEqual(strikes.update(hands(left_y=.67), .01), {"Cross"})
        self.assertEqual(strikes.update(hands(), .01), set())
        self.assertEqual(strikes.update(hands(), .01), set())
        self.assertEqual(strikes.update(hands(right_x=.60), .01), set())
        self.assertEqual(strikes.update(hands(right_x=.60), .01), {"Triangle"})
        self.assertEqual(strikes.update(hands(), .01), set())
        self.assertEqual(strikes.update(hands(), .01), set())
        self.assertEqual(strikes.update(hands(right_y=.67), .01), set())
        self.assertEqual(strikes.update(hands(right_y=.67), .01), {"Circle"})

    def test_missing_wrist_does_not_invent_attack(self):
        strikes = ArmStrikes()
        strikes.update(hands(), .01)
        strikes.update(hands(), .01)
        strikes.update(hands(), .01)
        points = hands(left_x=.40)
        points[15].visibility = .1
        self.assertEqual(strikes.update(points, .01), set())
        self.assertEqual(strikes.ready, 1)

    def test_forward_fist_depth_triggers_punch(self):
        strikes = ArmStrikes()
        guard = hands()
        for index in (11, 12, 15, 16):
            guard[index].z = 0.0
        strikes.update(guard, .01)
        strikes.update(guard, .01)
        strikes.update(guard, .01)
        extended = hands()
        for index in (11, 12, 15, 16):
            extended[index].z = 0.0
        extended[15].x = .28
        extended[15].z = -.20
        self.assertEqual(strikes.update(extended, .01), set())
        self.assertEqual(strikes.update(extended, .01), {"Square"})
        self.assertEqual(strikes.update(extended, .01), set())

    def test_one_frame_wrist_jump_does_not_press(self):
        strikes = ArmStrikes()
        for _ in range(3):
            strikes.update(hands(), .01)
        self.assertEqual(strikes.update(hands(left_x=.40), .01), set())
        self.assertEqual(strikes.update(hands(), .01), set())

    def test_depth_noise_alone_does_not_fire_punch(self):
        strikes = ArmStrikes()
        guard = hands()
        for index in (11, 12, 15, 16):
            guard[index].z = 0.0
        for _ in range(3):
            strikes.update(guard, .01)
        noisy = hands()
        for index in (11, 12, 15, 16):
            noisy[index].z = 0.0
        noisy[15].z = -.4
        self.assertEqual(strikes.update(noisy, .01), set())
        self.assertEqual(strikes.update(noisy, .01), set())

    def test_two_missing_wrist_results_preserve_guard(self):
        strikes = ArmStrikes()
        for _ in range(3):
            strikes.update(hands(), .01)
        missing = hands()
        missing[15].visibility = .1
        strikes.update(missing, .01)
        strikes.update(missing, .01)
        self.assertIsNotNone(strikes.anchors[0])
        strikes.update(missing, .01)
        self.assertIsNone(strikes.anchors[0])

    def test_wrists_below_frame_cannot_arm_attacks(self):
        strikes = ArmStrikes()
        below = hands()
        below[15].y = below[16].y = 1.2
        for _ in range(4):
            self.assertEqual(strikes.update(below, .01), set())
        self.assertEqual(strikes.ready, 0)


if __name__ == "__main__":
    unittest.main()
