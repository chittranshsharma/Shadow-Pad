import unittest
from types import SimpleNamespace

from attacks import HandObservation
from hand_identity import HandIdentity, body_references


def hand(side, x):
    return HandObservation(side, "Closed_Fist", .95, x, .5, .05, .08,
                           wrist_x=x, wrist_y=.5, identity_score=.4)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.identity = HandIdentity()
        self.references = {"wrists": {"Left": (.3, .5), "Right": (.7, .5)},
                           "shoulders": {"Left": (.3, .3), "Right": (.7, .3)}}

    def test_body_references_mirror_positions_without_swapping_anatomical_names(self):
        points = [SimpleNamespace(x=.3, y=.5, visibility=.95, presence=.95) for _ in range(33)]
        points[16].x = .7
        references = body_references(points, .01)
        self.assertAlmostEqual(references["wrists"]["Left"][0], .7)
        self.assertAlmostEqual(references["wrists"]["Right"][0], .3)
        self.assertEqual(body_references(points, .5), {})
        points[15].visibility = .1
        self.assertNotIn("Left", body_references(points, .01)["wrists"])

    def test_two_hands_with_same_classifier_label_get_distinct_body_identities(self):
        assigned = self.identity.assign([hand("Left", .3), hand("Left", .7)], self.references, 1)
        self.assertEqual([h.side for h in assigned], ["Left", "Right"])
        self.assertTrue(all(h.valid() for h in assigned))
        self.assertTrue(all(h.identity_source == "pose" for h in assigned))

    def test_recent_tracks_survive_classifier_label_changes(self):
        self.identity.assign([hand("Left", .3), hand("Right", .7)], self.references, 1)
        assigned = self.identity.assign([hand("Right", .32), hand("Left", .68)], {}, 1.05)
        self.assertEqual([h.side for h in assigned], ["Left", "Right"])
        self.assertTrue(all(h.identity_source == "track" for h in assigned))

    def test_pose_wrists_keep_anatomical_identity_when_hands_cross(self):
        self.identity.assign([hand("Left", .3), hand("Right", .7)], self.references, 1)
        crossed = {"wrists": {"Left": (.55, .5), "Right": (.45, .5)}}
        assigned = self.identity.assign([hand("Right", .55), hand("Left", .45)], crossed, 1.05)
        self.assertEqual([h.side for h in assigned], ["Left", "Right"])

    def test_shoulders_can_seed_guard_when_pose_wrists_are_missing(self):
        assigned = self.identity.assign([hand("Right", .3), hand("Left", .7)],
                                        {"shoulders": self.references["shoulders"]}, 1)
        self.assertEqual([h.side for h in assigned], ["Left", "Right"])
        self.assertTrue(all(h.identity_source == "body" for h in assigned))

    def test_ambiguous_central_hand_and_expired_track_are_not_guessed(self):
        assigned = self.identity.assign([hand("Left", .5)], self.references, 1)
        self.assertEqual(assigned[0].side, "Unknown")
        self.assertFalse(assigned[0].valid())
        self.identity.assign([hand("Left", .3)], self.references, 2)
        assigned = self.identity.assign([hand("Left", .3)], {}, 3)
        self.assertEqual(assigned[0].side, "Unknown")


if __name__ == "__main__":
    unittest.main()
