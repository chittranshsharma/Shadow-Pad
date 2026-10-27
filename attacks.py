"""Forward attacks from measured palm expansion, never inferred pose depth."""

from collections import deque
from dataclasses import dataclass, field
import math
from statistics import median


@dataclass(frozen=True)
class HandObservation:
    side: str
    gesture: str
    score: float
    x: float
    y: float
    width: float
    length: float

    def valid(self):
        values = (self.score, self.x, self.y, self.width, self.length)
        return (self.side in ("Left", "Right")
                and self.gesture in ("Closed_Fist", "Open_Palm")
                and all(math.isfinite(value) for value in values)
                and .7 <= self.score <= 1
                and 0 <= self.x <= 1 and 0 <= self.y <= 1
                and .018 <= self.width <= .6 and .018 <= self.length <= .6)


@dataclass
class HandState:
    phase: str = "show hand"
    gesture: str | None = None
    samples: deque = field(default_factory=lambda: deque(maxlen=16))
    recent: deque = field(default_factory=lambda: deque(maxlen=3))
    anchor: tuple | None = None
    last_time: float | None = None
    last_position: tuple | None = None
    previous_ratio: float = 1.0
    ratio: float = 1.0
    started: float = 0.0
    growth_steps: int = 0
    returned_at: float | None = None
    cooldown_until: float = 0.0

    def interrupt(self):
        # Reacquiring an extended hand must never become a fresh strike.
        self.phase = "return" if self.anchor else "show hand"
        self.recent.clear()
        self.samples.clear()
        self.last_time = None
        self.last_position = None
        self.returned_at = None
        self.growth_steps = 0


class HandAttacks:
    ACTIONS = {("Left", "Closed_Fist"): "Square", ("Right", "Closed_Fist"): "Triangle",
               ("Left", "Open_Palm"): "Cross", ("Right", "Open_Palm"): "Circle"}

    def __init__(self):
        self.reset()

    def reset(self):
        self.hands = {side: HandState() for side in ("Left", "Right")}
        self.last_timestamp = None

    @property
    def ready(self):
        return sum(state.phase in ("ready", "extending") for state in self.hands.values())

    def interrupt(self):
        for state in self.hands.values():
            state.interrupt()

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
                state.interrupt()
                continue
            hand = grouped[side][0]
            if state.gesture != hand.gesture:
                # Opening a fist increases its image size; learn a new guard first.
                state = self.hands[side] = HandState(gesture=hand.gesture)
            if self._advance(state, hand, timestamp, body):
                events.add(self.ACTIONS[(side, hand.gesture)])
        return events

    @staticmethod
    def _advance(state, hand, now, body):
        bx, by, bw = body
        position = ((hand.x - bx) / bw, (hand.y - by) / bw)
        if state.last_time is not None:
            dt = now - state.last_time
            if dt > .3 or math.dist(position, state.last_position) > max(.45, 5 * dt):
                state.interrupt()
        state.last_time, state.last_position = now, position
        state.recent.append((hand.width, hand.length))
        if len(state.recent) < 3:
            return False
        width = median(value[0] for value in state.recent)
        length = median(value[1] for value in state.recent)
        if state.anchor is None:
            state.phase = "hold guard"
            # A relaxed chest-height guard can be anywhere across the frame.
            if not -.6 <= position[1] <= 1.0:
                state.samples.clear()
                return False
            state.samples.append((now, width, length, *position, bw))
            while state.samples and now - state.samples[0][0] > .6:
                state.samples.popleft()
            if len(state.samples) < 4 or now - state.samples[0][0] < .3:
                return False
            for index in (1, 2):
                values = [sample[index] for sample in state.samples]
                if max(values) / min(values) > 1.12:
                    state.samples.clear()
                    return False
            if any(max(s[i] for s in state.samples) - min(s[i] for s in state.samples) > .15 for i in (3, 4)):
                state.samples.clear()
                return False
            state.anchor = tuple(median(s[i] for s in state.samples) for i in range(1, 6))
            state.phase = "ready"
            state.previous_ratio = state.ratio = 1
            return False

        aw, al, ax, ay, abw = state.anchor
        # Torso scale change means leaning/turning, not an isolated hand push.
        if not .85 <= bw / abw <= 1.15:
            state.interrupt()
            return False
        rw, rl = width / aw, length / al
        ratio = math.sqrt(rw * rl)
        previous = state.previous_ratio
        state.previous_ratio = state.ratio = ratio
        near_guard = rw < 1.13 and rl < 1.13 and math.dist(position, (ax, ay)) < .3
        if state.phase == "return":
            if near_guard and now >= state.cooldown_until:
                if state.returned_at is None:
                    state.returned_at = now
                elif now - state.returned_at >= .18:
                    state.phase = "ready"
                    state.anchor = (width, length, *position, bw)
                    state.returned_at = None
                    state.growth_steps = 0
            else:
                state.returned_at = None
            return False
        if state.phase == "ready" and ratio > 1.10:
            state.phase = "extending"
            state.started = now
            state.growth_steps = 1 if ratio - previous > .035 else 0
            return False
        if state.phase == "extending":
            if ratio - previous > .035:
                state.growth_steps += 1
            if ratio < 1.06:
                state.phase = "ready"
                state.growth_steps = 0
            elif now - state.started > .55 or ratio > 2.4:
                state.phase = "return"
            elif (ratio >= 1.35 and min(rw, rl) >= 1.18 and .75 <= rw / rl <= 1.33
                  and state.growth_steps >= 2):
                state.phase = "return"
                state.cooldown_until = now + .3
                state.returned_at = None
                return True
        return False
