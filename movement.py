"""Calibrated upper-body movement. Shoulder-only: elbows never gate movement."""

from collections import deque
from dataclasses import dataclass
import math
from statistics import median

from tracking_quality import reliable
from attacks import HandAttacks


POSE_TIMEOUT = .6


@dataclass(frozen=True)
class Neutral:
    x: float
    y: float
    width: float
    head_y: float | None = None


class Movement:
    def __init__(self, sensitivity=1.0):
        if not math.isfinite(sensitivity) or not .5 <= sensitivity <= 2:
            raise ValueError("Sensitivity must be between 0.5 and 2.")
        self.sensitivity = sensitivity
        self.neutral = None
        self.calibrating = False
        self.samples = deque(maxlen=120)
        self.sample_start = None
        self.horizontal = None
        self.ducking = False
        self.jump_ready = True
        self.jump_until = 0

    def reset_actions(self):
        self.horizontal = None
        self.ducking = False
        self.jump_until = 0
        self.jump_ready = True

    def calibrate(self):
        self.neutral = None
        self.calibrating = True
        self.samples.clear()
        self.sample_start = None
        self.reset_actions()

    def update(self, points, age, now, confidence=.6):
        if (not points or len(points) <= 16 or age > POSE_TIMEOUT
                or not all(reliable(points[index], confidence) for index in (11, 12))):
            self.reset_actions()
            if self.calibrating:
                self.samples.clear()
                self.sample_start = None
            return set(), False
        left, right = points[11], points[12]
        x, y = (left.x + right.x) / 2, (left.y + right.y) / 2
        width = math.hypot(left.x - right.x, left.y - right.y)
        if width < .05:
            self.reset_actions()
            return set(), False
        if self.calibrating:
            if self.sample_start is None:
                self.sample_start = now
            head_y = points[0].y if reliable(points[0], confidence) else None
            self.samples.append((x, y, width, head_y))
            if now - self.sample_start >= 2 and len(self.samples) >= 10:
                xs, ys, widths, heads = zip(*self.samples)
                scale = median(widths)
                if max(xs) - min(xs) <= .15 * scale and max(ys) - min(ys) <= .15 * scale:
                    head_values = [value for value in heads if value is not None]
                    self.neutral = Neutral(median(xs), median(ys), scale,
                                           median(head_values) if len(head_values) >= 8 else None)
                    self.calibrating = False
                else:
                    self.samples.clear()
                    self.sample_start = now
            return set(), True
        if self.neutral is None:
            return set(), True

        # Display is mirrored: increasing raw-image x means moving screen-left.
        dx = (self.neutral.x - x) / self.neutral.width * self.sensitivity
        dy = (self.neutral.y - y) / self.neutral.width * self.sensitivity
        head_drop = ((points[0].y - self.neutral.head_y) / self.neutral.width * self.sensitivity
                     if self.neutral.head_y is not None and reliable(points[0], confidence) else 0)
        if dx <= -.20:
            self.horizontal = "Left"
        elif dx >= .20:
            self.horizontal = "Right"
        elif not ((self.horizontal == "Left" and dx < -.12)
                  or (self.horizontal == "Right" and dx > .12)):
            self.horizontal = None
        if dy <= -.17 or head_drop >= .25:
            self.ducking = True
        elif dy >= -.07 and head_drop <= .11:
            self.ducking = False
        if dy < .10:
            self.jump_ready = True
        if dy >= .28 and self.jump_ready and not self.ducking:
            self.jump_until = now + .30
            self.jump_ready = False
        actions = {self.horizontal} if self.horizontal else set()
        if self.ducking:
            self.jump_until = 0
            actions.add("Down")
        elif now < self.jump_until:
            actions.add("Up")
        return actions, True


class MovementController:
    def __init__(self, keyboard, bindings, sensitivity=1.0):
        self.keyboard = keyboard
        self.practice = getattr(keyboard, "is_practice", False)
        self.bindings = bindings
        expected = {"Left", "Right", "Up", "Down", "Square", "Triangle", "Cross", "Circle"}
        if set(bindings) != expected:
            raise ValueError("Control requires four directions and four attack bindings.")
        if len({binding[0] for binding in bindings.values()}) != len(expected):
            raise ValueError("Control actions must have distinct keyboard bindings.")
        self.movement = Movement(sensitivity)
        self.strikes = HandAttacks()
        self.pulses = {}
        self.attack_counts = {action: 0 for action in ("Square", "Triangle", "Cross", "Circle")}
        self.body = None
        self.body_history = deque(maxlen=16)
        self.last_hand_result = None
        self.last_attack = None
        self.last_attack_at = 0
        self.armed = False
        self.target = None
        self.last_pose = None
        self.desired = set()
        self.held = set()
        self.toggle_was_down = False
        self.arm_at = None
        self.recovering = 0
        self.status = "C: calibrate | A: arm in 5 seconds"

    def pause(self, reason="Paused"):
        self.armed = False
        self.arm_at = None
        self.target = None
        self.desired.clear()
        self.movement.reset_actions()
        self.strikes.reset()
        self.pulses.clear()
        self.last_attack = None
        self.last_hand_result = None
        self.recovering = 0
        self.status = reason
        self.keyboard.release()
        self.held.clear()

    def calibrate(self):
        self.pause("Calibrating: sit comfortably and hold still for 2 seconds")
        self.movement.calibrate()

    def arm_countdown(self, now, seconds=5):
        if self.movement.neutral is None:
            self.status = "Calibrate first: press C in this preview"
            return
        self.pause(f"Practice starts in {seconds:g} seconds" if self.practice
                   else f"ARMING: click PPSSPP within {seconds:g} seconds")
        self.arm_at = now + seconds

    def _arm(self, now):
        target = self.keyboard.foreground_ppsspp()
        if not target:
            self.status = "NOT ARMED: PPSSPP was not the active window; press A and retry"
            return
        if self.last_pose is None or now - self.last_pose > POSE_TIMEOUT:
            self.status = "NOT ARMED: shoulders missing or tracking too slow; press A and retry"
            return
        self.armed = True
        self.target = target
        self.status = "ACTIVE: neutral"
        self.movement.reset_actions()
        self.strikes.reset()
        self.pulses.clear()
        self.last_attack = None
        self.last_hand_result = None
        self.recovering = 0

    def on_pose(self, points, age, now, confidence=.6):
        desired, valid = self.movement.update(points, age, now, confidence)
        if not valid:
            self.last_pose = None
            self.body_history.clear()
            self.desired.clear()
            self.strikes.interrupt(keep_learning=True, reason="waiting for shoulders")
            self.pulses.clear()
            self.last_attack = None
            if self.armed:
                self.recovering = 1
                self.status = "TRACKING GAP: keys released; recovering automatically"
            return
        self.last_pose = now - age
        self.body = (1 - (points[11].x + points[12].x) / 2,
                     (points[11].y + points[12].y) / 2,
                     math.hypot(points[11].x - points[12].x, points[11].y - points[12].y))
        self.body_history.append((self.last_pose, self.body))
        if self.armed and self.recovering:
            self.recovering += 1
            if self.recovering < 3:
                self.movement.reset_actions()
                self.desired.clear()
                self.status = "TRACKING: reacquiring shoulders"
                return
            self.recovering = 0
        if self.movement.calibrating:
            self.status = "Calibrating: sit comfortably and hold still for 2 seconds"
        elif self.movement.neutral is not None and not self.armed and self.arm_at is None:
            if self.status.startswith("Calibrating:"):
                self.status = ("Calibrated | A starts practice" if self.practice
                               else "Calibrated | press A here, then click PPSSPP")
        self.desired = desired if self.armed else set()

    def on_hands(self, observations, timestamp, now):
        if not self.armed or self.recovering:
            return
        if (self.keyboard.modifiers_down() or self.last_pose is None or now - self.last_pose > .3
                or not 0 <= now - timestamp <= .3 or not self.body_history):
            self.strikes.interrupt()
            self.pulses.clear()
            return
        body_time, body = min(self.body_history, key=lambda sample: abs(sample[0] - timestamp))
        if abs(body_time - timestamp) > .2:
            self.strikes.interrupt()
            self.pulses.clear()
            return
        self.last_hand_result = timestamp
        for side, actions in (("Left", ("Square", "Cross")), ("Right", ("Triangle", "Circle"))):
            if sum(hand.side == side and hand.valid() for hand in observations) != 1:
                for action in actions:
                    self.pulses.pop(action, None)
        for action in self.strikes.update(observations, timestamp, body):
            self.pulses[action] = now + .12
            self.last_attack = action
            self.last_attack_at = now
            self.attack_counts[action] += 1

    def tick(self, now):
        if self.arm_at is not None:
            if now >= self.arm_at:
                self.arm_at = None
                self._arm(now)
            else:
                self.status = (f"Practice starts in {self.arm_at - now:.1f}s" if self.practice
                               else f"ARMING: click PPSSPP | {self.arm_at - now:.1f}s")
        toggle = self.keyboard.pause_requested()
        if toggle and not self.toggle_was_down:
            if self.armed:
                self.pause()
            elif self.movement.neutral is None:
                self.status = "Calibrate first: focus the camera preview and press C"
            else:
                self.arm_at = None
                self._arm(now)
        self.toggle_was_down = toggle
        if not self.armed:
            return
        if self.keyboard.foreground_ppsspp() != self.target:
            self.pause("PPSSPP lost focus: paused")
            return
        if self.last_pose is None or now - self.last_pose > POSE_TIMEOUT:
            self.recovering = 1
            self.desired.clear()
            self.pulses.clear()
            self.last_attack = None
            self.strikes.interrupt(keep_learning=True, reason="waiting for shoulders")
            self.movement.reset_actions()
            for key in list(self.held):
                self.keyboard.release(key)
                self.held.remove(key)
            self.status = "TRACKING GAP: keys released; recovering automatically"
            return
        desired = set() if self.keyboard.modifiers_down() else set(self.desired)
        if self.keyboard.modifiers_down():
            self.pulses.clear()
            self.strikes.interrupt()
        if self.last_hand_result is None or now - self.last_hand_result > .3:
            self.strikes.interrupt()
            self.pulses.clear()
        if now >= self.movement.jump_until:
            desired.discard("Up")
        for action, deadline in list(self.pulses.items()):
            if now >= deadline:
                del self.pulses[action]
            elif not self.keyboard.modifiers_down():
                desired.add(action)
        desired_keys = {self.bindings[action][0] for action in desired}
        try:
            for key in self.held - desired_keys:
                self.keyboard.release(key)
                self.held.remove(key)
            for key in desired_keys - self.held:
                self.keyboard.press(key, self.target)
                self.held.add(key)
        except BaseException:
            self.pause("Input error: paused")
            raise
        activity = " + ".join(sorted(desired)) if desired else "neutral"
        if self.last_attack and now - self.last_attack_at < 1 and not self.pulses:
            activity += f" | last {self.last_attack}"
        hands = f"hands {self.strikes.ready}/2"
        if self.strikes.ready == 0:
            hands += " | Tab: hand status"
        self.status = f"ACTIVE: {activity} | {hands}"
