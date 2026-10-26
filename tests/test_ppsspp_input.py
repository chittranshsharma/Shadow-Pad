from pathlib import Path
import tempfile
import unittest

from ppsspp_input import BoundedTest, WindowsKeyboard, read_bindings


class FakeKeyboard:
    def __init__(self):
        self.focus = (123, 1)
        self.paused = False
        self.events = []

    def foreground_ppsspp(self):
        return self.focus

    def pause_requested(self):
        return self.paused

    def press(self, vk, target):
        self.events.append(("down", vk, target))

    def release(self):
        self.events.append(("up",))


class InputTestTests(unittest.TestCase):
    def setUp(self):
        self.keyboard = FakeKeyboard()
        self.test = BoundedTest(self.keyboard)

    def test_starts_paused_and_countdown_sends_nothing(self):
        self.assertEqual(self.test.state, "PAUSED")
        self.test.arm(65, 3, .1, 0)
        self.test.tick(2.9)
        self.assertEqual(self.keyboard.events, [])

    def test_missing_ppsspp_focus_blocks_key_down(self):
        self.keyboard.focus = None
        self.test.arm(65, 3, .1, 0)
        with self.assertRaisesRegex(RuntimeError, "active window"):
            self.test.tick(3)
        self.assertFalse(any(event[0] == "down" for event in self.keyboard.events))

    def test_hold_releases_and_finishes_once(self):
        self.test.arm(65, 3, .1, 0)
        self.test.tick(3)
        self.assertEqual(self.test.state, "HOLDING")
        self.test.tick(3.11)
        self.test.tick(4)
        self.assertEqual(self.keyboard.events, [("down", 65, (123, 1)), ("up",)])
        self.assertEqual(self.test.state, "DONE")

    def test_focus_change_releases_early(self):
        self.test.arm(65, 3, 1, 0)
        self.test.tick(3)
        self.keyboard.focus = (456, 2)
        self.test.tick(3.01)
        self.assertEqual(self.keyboard.events[-1], ("up",))
        self.assertEqual(self.test.state, "CANCELLED")

    def test_pause_cancels_pending_action(self):
        self.test.arm(65, 3, .1, 0)
        self.keyboard.paused = True
        self.test.tick(2)
        self.assertEqual(self.test.state, "CANCELLED")
        self.assertFalse(any(event[0] == "down" for event in self.keyboard.events))

    def test_pause_releases_held_action(self):
        self.test.arm(65, 3, 1, 0)
        self.test.tick(3)
        self.keyboard.paused = True
        self.test.tick(3.01)
        self.assertEqual(self.test.state, "CANCELLED")
        self.assertEqual(self.keyboard.events[-1], ("up",))

    def test_invalid_and_unbounded_durations_are_rejected(self):
        for delay, hold in ((0, .1), (3, 10), (float("nan"), .1), (3, float("inf"))):
            with self.assertRaises(ValueError):
                self.test.arm(65, delay, hold, 0)

    def test_uncertain_key_down_failure_still_releases(self):
        def failed_press(vk, target):
            self.keyboard.events.append(("down", vk, target))
            raise RuntimeError("API failure")
        self.keyboard.press = failed_press
        self.test.arm(65, 3, .1, 0)
        with self.assertRaisesRegex(RuntimeError, "API failure"):
            self.test.tick(3)
        self.assertEqual(self.test.state, "CANCELLED")
        self.assertEqual(self.keyboard.events[-1], ("up",))

    def test_reads_keyboard_binding_instead_of_gamepad(self):
        content = "[ControlMapping]\nLeft=20-21,1-21\nRight=1-22\nSquare=20-99,1-29\nTriangle=1-47\nCross=1-54\nCircle=1-52\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controls.ini"
            path.write_text(content, encoding="utf-8")
            bindings = read_bindings(path)
            self.assertEqual(bindings["Square"], (65, "A"))
            self.assertEqual(bindings["Cross"], (90, "Z"))
            self.assertEqual(bindings["Left"][0], 0x25)
            path.write_text(content.replace("1-29", "1-9999"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Square"):
                read_bindings(path)

    def test_multi_key_release_attempts_other_keys_after_failure(self):
        keyboard = WindowsKeyboard.__new__(WindowsKeyboard)
        keyboard.held = {37: (75, True), 40: (80, True)}
        calls = []
        def send(scan, extended, up=False):
            calls.append(scan)
            if scan == 75:
                raise RuntimeError("release failed")
        keyboard._send = send
        with self.assertRaisesRegex(RuntimeError, "release failed"):
            keyboard.release()
        self.assertEqual(calls, [75, 80])
        self.assertEqual(set(keyboard.held), {37})

    def test_releasing_one_key_keeps_the_other_held(self):
        keyboard = WindowsKeyboard.__new__(WindowsKeyboard)
        keyboard.held = {37: (75, True), 40: (80, True)}
        calls = []
        keyboard._send = lambda *args, **kwargs: calls.append((args, kwargs))
        keyboard.release(37)
        self.assertEqual(set(keyboard.held), {40})
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
