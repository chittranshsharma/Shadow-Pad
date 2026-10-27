"""Associate detected hands with anatomical body references and recent tracks."""

from dataclasses import replace
import math

from tracking_quality import reliable


def body_references(points, age, confidence=.6):
    if not points or len(points) <= 16 or not 0 <= age <= .3:
        return {}
    shoulders, wrists = {}, {}
    for side, shoulder, wrist in (("Left", 11, 15), ("Right", 12, 16)):
        if reliable(points[shoulder], confidence):
            shoulders[side] = (1 - points[shoulder].x, points[shoulder].y)
        if reliable(points[wrist], confidence):
            wrists[side] = (1 - points[wrist].x, points[wrist].y)
    return {"shoulders": shoulders, "wrists": wrists}


class HandIdentity:
    def __init__(self):
        self.tracks = {}

    def assign(self, observations, references, timestamp):
        positions = [(hand.wrist_x if hand.wrist_x is not None else hand.x,
                      hand.wrist_y if hand.wrist_y is not None else hand.y) for hand in observations]
        assignments, used = {}, set()

        def match(targets, maximum, source):
            edges = []
            for index, position in enumerate(positions):
                if index in assignments:
                    continue
                costs = sorted((math.dist(position, point), side) for side, point in targets.items() if side not in used)
                if not costs or costs[0][0] > maximum:
                    continue
                if len(costs) > 1 and costs[1][0] - costs[0][0] < .025:
                    continue
                edges.append((costs[0][0], index, costs[0][1]))
            for _, index, side in sorted(edges):
                if index not in assignments and side not in used:
                    assignments[index] = (side, source)
                    used.add(side)

        recent = {side: point for side, (point, seen) in self.tracks.items() if 0 <= timestamp - seen <= .35}
        match(references.get("wrists", {}), .14, "pose")
        match(recent, .18, "track")
        shoulders = references.get("shoulders", {})
        if len(shoulders) == 2:
            midpoint = sum(point[0] for point in shoulders.values()) / 2
            screen_left = min(shoulders, key=lambda side: shoulders[side][0])
            screen_right = max(shoulders, key=lambda side: shoulders[side][0])
            candidates = []
            for index, position in enumerate(positions):
                if index in assignments or abs(position[0] - midpoint) < .035:
                    continue
                side = screen_left if position[0] < midpoint else screen_right
                candidates.append((math.dist(position, shoulders[side]), index, side))
            for _, index, side in sorted(candidates):
                if side not in used:
                    assignments[index] = (side, "body")
                    used.add(side)

        assigned = []
        for index, hand in enumerate(observations):
            side, source = assignments.get(index, ("Unknown", "unassigned"))
            assigned.append(replace(hand, side=side, identity_source=source))
            if side != "Unknown":
                self.tracks[side] = (positions[index], timestamp)
        self.tracks = {side: value for side, value in self.tracks.items() if timestamp - value[1] <= .5}
        return assigned
