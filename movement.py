"""Calibrated upper-body movement. Shoulder-only: elbows never gate movement."""

from collections import deque
from dataclasses import dataclass
import math
from statistics import median

from tracking_quality import reliable


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


class ArmStrikes:
    """One attack per deliberate wrist excursion and return; elbows are optional."""

    HANDS = ((11, 15, "Square", "Cross"), (12, 16, "Triangle", "Circle"))

    def __init__(self, sensitivity=1.0):
        self.sensitivity = sensitivity
        self.anchors = [None, None]
        self.latched = [False, False]
        self.ready = 0

    def reset(self):
        self.anchors = [None, None]
        self.latched = [False, False]
        self.ready = 0

    def update(self, points, age, confidence=.6):
        if not points or len(points) <= 16 or age > POSE_TIMEOUT:
            self.reset()
            return set()
        if not all(reliable(points[index], confidence) for index in (11, 12)):
            self.reset()
            return set()
        midpoint = (points[11].x + points[12].x) / 2
        width = math.hypot(points[11].x - points[12].x, points[11].y - points[12].y)
        if width < .05:
            self.reset()
            return set()
        events = set()
        self.ready = 0
        for side, (shoulder, wrist, punch, kick) in enumerate(self.HANDS):
            if not reliable(points[wrist], confidence):
                self.anchors[side] = None
                self.latched[side] = False
                continue
            distance = abs(points[wrist].x - midpoint) / width
            height = (points[wrist].y - points[shoulder].y) / width
            wrist_z = getattr(points[wrist], "z", None)
            shoulder_z = getattr(points[shoulder], "z", None)
            depth = ((wrist_z - shoulder_z) / width
                     if wrist_z is not None and shoulder_z is not None
                     and math.isfinite(wrist_z) and math.isfinite(shoulder_z) else None)
            anchor = self.anchors[side]
            if anchor is None:
                if distance >= .15 and -.4 <= height <= .85:
                    self.anchors[side] = (distance, height, depth)
                    self.ready += 1
                continue
            self.ready += 1
            inward = (anchor[0] - distance) * self.sensitivity
            downward = (height - anchor[1]) * self.sensitivity
            forward = ((anchor[2] - depth) * self.sensitivity
                       if anchor[2] is not None and depth is not None else 0)
            if self.latched[side]:
                if abs(inward) < .13 and abs(downward) < .15 and abs(forward) < .15:
                    self.latched[side] = False
                    self.anchors[side] = (distance, height, depth)
            elif downward >= .30 and downward > max(inward, forward):
                events.add(kick)
                self.latched[side] = True
            elif inward >= .26 or forward >= .28:
                events.add(punch)
                self.latched[side] = True
        return events


class MovementController:
    def __init__(self, keyboard, bindings, sensitivity=1.0):
        self.keyboard = keyboard
        self.bindings = bindings
        expected = {"Left", "Right", "Up", "Down", "Square", "Triangle", "Cross", "Circle"}
        if set(bindings) != expected:
            raise ValueError("Control requires four directions and four attack bindings.")
        if len({binding[0] for binding in bindings.values()}) != len(expected):
            raise ValueError("Control actions must have distinct keyboard bindings.")
        self.movement = Movement(sensitivity)
        self.strikes = ArmStrikes(sensitivity)
        self.pulses = {}
        self.armed = False
        self.target = None
        self.last_pose = None
        self.desired = set()
        self.held = set()
        self.toggle_was_down = False
        self.arm_at = None
        self.status = "C: calibrate | A: arm in 5 seconds"

    def pause(self, reason="Paused"):
        self.armed = False
        self.arm_at = None
        self.target = None
        self.desired.clear()
        self.movement.reset_actions()
        self.strikes.reset()
        self.pulses.clear()
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
        self.pause(f"ARMING: click PPSSPP within {seconds:g} seconds")
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

    def on_pose(self, points, age, now, confidence=.6):
        desired, valid = self.movement.update(points, age, now, confidence)
        if not valid:
            self.last_pose = None
            self.desired.clear()
            self.strikes.reset()
            self.pulses.clear()
            if self.armed:
                self.pause("Tracking lost: paused; show both shoulders and arm again")
            return
        self.last_pose = now - age
        if self.armed:
            for action in self.strikes.update(points, age, confidence):
                self.pulses[action] = now + .14
        if self.movement.calibrating:
            self.status = "Calibrating: sit comfortably and hold still for 2 seconds"
        elif self.movement.neutral is not None and not self.armed and self.arm_at is None:
            if self.status.startswith("Calibrating:"):
                self.status = "Calibrated | press A here, then click PPSSPP"
        self.desired = desired if self.armed else set()

    def tick(self, now):
        if self.arm_at is not None:
            if now >= self.arm_at:
                self.arm_at = None
                self._arm(now)
            else:
                self.status = f"ARMING: click PPSSPP | {self.arm_at - now:.1f}s"
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
            self.pause("Tracking stale: paused")
            return
        desired = set() if self.keyboard.modifiers_down() else set(self.desired)
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
        self.status = ("ACTIVE: " + (" + ".join(sorted(desired)) if desired else "neutral")
                       + f" | hands {self.strikes.ready}/2")
