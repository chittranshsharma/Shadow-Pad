import unittest

import numpy as np

from webcam_tracker import preview


class PreviewTests(unittest.TestCase):
    def test_default_preview_preserves_entire_camera_canvas(self):
        frame = np.full((480, 640, 3), 130, dtype=np.uint8)
        image = preview(frame, None, set(), "NO PERSON DETECTED", .02, 20, 30, 30)
        self.assertEqual(image.shape, frame.shape)
        np.testing.assert_array_equal(image[34:453], frame[34:453])
        np.testing.assert_array_equal(frame, np.full_like(frame, 130))

    def test_details_does_not_crop_or_expand_camera(self):
        frame = np.full((480, 640, 3), 130, dtype=np.uint8)
        image = preview(frame, None, set(), "NO PERSON DETECTED", .02, 20, 30, 30, details=True)
        self.assertEqual(image.shape, frame.shape)
        np.testing.assert_array_equal(image[35:450, 425:], frame[35:450, 425:])


if __name__ == "__main__":
    unittest.main()
