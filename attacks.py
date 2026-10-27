"""Shape-gated attacks from measured palm expansion and projected hand travel."""

from collections import deque
from dataclasses import dataclass, field
import math
from statistics import median


@dataclass(frozen=True)
class HandObservation:
    side: str
    gesture: str
    score: float | None
    x: float
    y: float
    width: float
    length: float
    source: str = "model"
    wrist_x: float | None = None
    wrist_y: float | None = None
    identity_score: float = 1.0
    identity_source: str = "model"

    def valid(self):
        values = (self.x, self.y, self.width, self.length)
        supported = ((self.source == "geometry" and self.score is None)
                     or (self.source == "model" and self.score is not None
                         and math.isfinite(self.score) and .5 <= self.score <= 1))
        identity = (self.identity_source in ("pose", "track", "body")
                    or (self.identity_source == "model" and math.isfinite(self.identity_score)
                        and self.identity_score >= .7))
        return (self.side in ("Left", "Right")
                and self.gesture in ("Closed_Fist", "Open_Palm")
                and all(math.isfinite(value) for value in values)
                and supported
                and identity
                and 0 <= self.x <= 1 and 0 <= self.y <= 1
                and .018 <= self.width <= .6 and .018 <= self.length <= .6)


@dataclass
class HandState:
    phase: str = "show hand"
    gesture: str | None = None
    samples: deque = field(default_factory=lambda: deque(maxlen=64))
    recent: deque = field(default_factory=lambda: deque(maxlen=3))
    anchor: tuple | None = None
    last_time: float | None = None
    last_position: tuple | None = None
    ratio: float = 1.0
    progress: float = 0.0
    previous_progress: float = 0.0
    confirmations: int = 0
    started: float = 0.0
    growth_steps: int = 0
    returned_at: float | None = None
    cooldown_until: float = 0.0
    reason: str = "show fist or palm"

    def interrupt(self, keep_learning=False):
        # Reacquiring an extended hand must never become a fresh strike.
        previous_phase = self.phase
        self.phase = "reacquire" if self.anchor else "show hand"
        if not keep_learning or previous_phase not in ("reacquire", "hold guard", "show hand"):
            self.recent.clear()
            self.samples.clear()
            self.last_time = None
            self.last_position = None
        self.returned_at = None
        self.growth_steps = 0
        self.confirmations = 0
        self.progress = self.previous_progress = 0
        self.reason = "recovering hand" if self.anchor else "show fist or palm"


class HandAttacks:
    ACTIONS = {("Left", "Closed_Fist"): "Square", ("Right", "Closed_Fist"): "Triangle",
               ("Left", "Open_Palm"): "Cross", ("Right", "Open_Palm"): "Circle"}

    def __init__(self, sensitivity=1.0):
        if not math.isfinite(sensitivity) or not .5 <= sensitivity <= 2:
            raise ValueError("Attack sensitivity must be between 0.5 and 2.")
        self.sensitivity = sensitivity
        self.reset()

    def set_sensitivity(self, sensitivity):
        if not math.isfinite(sensitivity) or not .5 <= sensitivity <= 2:
            raise ValueError("Attack sensitivity must be between 0.5 and 2.")
        self.sensitivity = sensitivity
        self.reset()

    def reset(self):
        self.hands = {side: HandState() for side in ("Left", "Right")}
        self.last_timestamp = None

    @property
    def ready(self):
        return sum(state.phase in ("ready", "extending") for state in self.hands.values())

    def interrupt(self, keep_learning=False, reason=None):
        for state in self.hands.values():
            state.interrupt(keep_learning)
            if reason:
                state.reason = reason

    def update(self, observations, timestamp, body):
        """Consume each capture timestamp once. Body is mirrored x, y, width."""
        if not math.isfinite(timestamp) or (self.last_timestamp is not None and timestamp <= self.last_timestamp):
            return set()
        self.last_timestamp = timestamp
        if body is None or not all(math.isfinite(v) for v in body) or body[2] < .05:
            self.interrupt()
            return set()
        grouped = {side: [] for side in self.hands}
        for observation in observations:
            if observation.valid():
                grouped[observation.side].append(observation)
        events = set()
        for side, state in self.hands.items():
            if len(grouped[side]) != 1:
                state.interrupt(keep_learning=True)
                visible = [hand for hand in observations if hand.side == side]
                if len(visible) > 1:
                    state.reason = "hand identity uncertain"
                elif visible:
                    hand = visible[0]
                    if hand.gesture not in ("Closed_Fist", "Open_Palm"):
                        state.reason = "make fist or open palm"
                    elif hand.score is not None and hand.score < .5:
                        state.reason = f"shape confidence {hand.score:.0%}"
                    else:
                        state.reason = "move hand closer / fully in view"
                else:
                    state.reason = "hand not detected"
                continue
            hand = grouped[side][0]
            if state.gesture != hand.gesture:
                # Opening a fist increases its image size; learn a new guard first.
                state = self.hands[side] = HandState(gesture=hand.gesture)
            if self._advance(state, hand, timestamp, body, self.sensitivity):
                events.add(self.ACTIONS[(side, hand.gesture)])
        return events

    @staticmethod
    def _learn_guard(state, hand, now, width, length, position, bw, duration=.3):
        state.phase = "hold guard" if state.anchor is None else "reacquire"
        shape_supported = hand.source == "geometry" or hand.score >= .6
        state.samples.append((now, width, length, *position, bw, shape_supported))
        while state.samples and now - state.samples[0][0] > .8:
            state.samples.popleft()
        state.reason = f"hold still: {min(len(state.samples), 5)}/5"
        if len(state.samples) < 5 or now - state.samples[0][0] < duration:
            return
        if sum(sample[6] for sample in state.samples) / len(state.samples) < .6:
            state.reason = "shape uncertain: turn fist/palm toward lens"
            return
        for index in (1, 2):
            values = [sample[index] for sample in state.samples]
            centre = median(values)
            if median(abs(value - centre) for value in values) / centre > .08:
                state.reason = "hold hand still"
                return
            half = len(values) // 2
            if abs(median(values[:half]) - median(values[-half:])) / centre > .1:
                state.reason = "hold hand still"
                return
        if any(median(abs(s[i] - median(v[i] for v in state.samples)) for s in state.samples) > .08 for i in (3, 4)):
            state.reason = "hold hand still"
            return
        state.anchor = tuple(median(s[i] for s in state.samples) for i in range(1, 6))
        state.samples.clear()
        state.phase = state.reason = "ready"
        state.ratio = 1
        state.progress = state.previous_progress = 0
        state.confirmations = state.growth_steps = 0
        state.returned_at = None

    @staticmethod
    def _advance(state, hand, now, body, sensitivity):
        bx, by, bw = body
        position = ((hand.x - bx) / bw, (hand.y - by) / bw)
        if state.last_time is not None:
            dt = now - state.last_time
            if dt > .3 or math.dist(position, state.last_position) > max(.45, 5 * dt):
                state.interrupt()
        state.last_time, state.last_position = now, position
        state.recent.append((hand.width, hand.length, *position))
        if len(state.recent) < 3:
            state.reason = "checking hand"
            return False
        width = median(value[0] for value in state.recent)
        length = median(value[1] for value in state.recent)
        position = (median(value[2] for value in state.recent), median(value[3] for value in state.recent))
        if state.anchor is None:
            HandAttacks._learn_guard(state, hand, now, width, length, position, bw)
            return False

        aw, al, ax, ay, abw = state.anchor
        # Torso scale change means leaning/turning, not an isolated hand push.
        if state.phase != "reacquire" and not .85 <= bw / abw <= 1.15:
            state.interrupt()
            state.reason = "body moved: return or press H"
            return False
        rw, rl = width / aw, length / al
        ratio = math.sqrt(rw * rl)
        state.ratio = ratio
        dx, dy = position[0] - ax, position[1] - ay
        expansion = ((ratio - 1) / .35 if min(rw, rl) >= 1.08 and .75 <= rw / rl <= 1.33 and dy <= .18 else 0)
        travel = max(-dy / .22, abs(dx) / .30 if dy <= .12 else 0)
        progress = max(0, expansion, travel) * sensitivity
        previous = state.previous_progress
        state.progress = state.previous_progress = progress
        near_guard = rw < 1.13 and rl < 1.13 and math.dist(position, (ax, ay)) < .12
        if state.phase in ("return", "reacquire"):
            state.reason = "retract hand"
            if near_guard and now >= state.cooldown_until:
                if state.returned_at is None:
                    state.returned_at = now
                elif now - state.returned_at >= .18:
                    state.phase = "ready"
                    state.reason = "ready"
                    state.anchor = (width, length, *position, bw)
                    state.returned_at = None
                    state.growth_steps = 0
                    state.confirmations = 0
                    state.samples.clear()
            else:
                state.returned_at = None
                if progress < .7 and rw < 1.15 and rl < 1.15 and now >= state.cooldown_until:
                    HandAttacks._learn_guard(state, hand, now, width, length, position, bw, duration=.5)
            return False
        if state.phase == "ready" and progress > .3:
            state.phase = "extending"
            state.reason = "push forward"
            state.started = now
            state.growth_steps = 1 if progress - previous > .12 else 0
            state.confirmations = int(progress >= 1)
            return False
        if state.phase == "extending":
            if progress - previous > .12:
                state.growth_steps += 1
            state.confirmations = state.confirmations + 1 if progress >= 1 else 0
            if progress < .18:
                state.phase = "ready"
                state.reason = "ready"
                state.growth_steps = 0
            elif now - state.started > .8 or ratio > 2.4:
                state.phase = "return"
                state.reason = "retract hand"
            elif progress >= 1 and (state.growth_steps >= 2 or state.confirmations >= 2):
                state.phase = "return"
                state.reason = "attack detected: retract"
                state.cooldown_until = now + .3
                state.returned_at = None
                return True
        return False
