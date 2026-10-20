import unittest

import numpy as np

from utils.tints import Tint, parse_color, tint_layers
from web.painter import BOARD_GAP, BOARD_SLOT, cell_at


class TintTest(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(0)
        self.path = np.full((8, 8), 4.0, dtype=np.float32)
        self.nz = np.ones((8, 8), dtype=np.float32)

    def test_parse_color_accepts_picker_formats(self):
        self.assertEqual(parse_color("#5aaaff"), (90, 170, 255))
        self.assertEqual(parse_color("#fff"), (255, 255, 255))
        self.assertEqual(parse_color("rgba(255, 80, 120, 1)"), (255, 80, 120))

    def test_dye_transmits_its_own_colour_at_mean_path(self):
        transmission, _ = tint_layers(Tint("color", (255, 0, 0), 1.0), self.path, self.nz, self.rng)
        b, g, r = transmission[0, 0]
        self.assertAlmostEqual(float(r), 1.0, places=5)
        self.assertLess(float(b), 0.01)

    def test_thicker_dyed_glass_absorbs_more(self):
        path = np.array([[2.0, 6.0]], dtype=np.float32)
        transmission, _ = tint_layers(Tint("color", (0, 0, 255), 0.6), path, np.ones_like(path), self.rng)
        self.assertGreater(transmission[0, 0, 2], transmission[0, 1, 2])

    def test_thin_film_conserves_energy(self):
        transmission, reflection = tint_layers(Tint("rainbow", strength=1.0), self.path, self.nz, self.rng)
        np.testing.assert_allclose(transmission + reflection, 1.0, atol=1e-6)
        self.assertGreater(float(np.ptp(reflection)), 0.05)

    def test_clear_glass_is_untouched(self):
        self.assertEqual(tint_layers(Tint(), self.path, self.nz, self.rng), (1.0, 0.0))


class BoardTest(unittest.TestCase):
    faces = [(0, 0, 90, 90), (100, 0, 60, 60)]

    def test_click_maps_to_face_row_and_column(self):
        self.assertEqual(cell_at(self.faces, 3, 5, 5), (0, 0, 0))
        self.assertEqual(cell_at(self.faces, 3, BOARD_SLOT - 1, BOARD_SLOT - 1), (0, 2, 2))
        second = BOARD_SLOT + BOARD_GAP
        self.assertEqual(cell_at(self.faces, 3, second + BOARD_SLOT // 2, 5), (1, 0, 1))

    def test_click_in_gap_or_empty_slot_is_ignored(self):
        self.assertIsNone(cell_at(self.faces, 3, BOARD_SLOT + 2, 5))
        third = 2 * (BOARD_SLOT + BOARD_GAP)
        self.assertIsNone(cell_at(self.faces, 3, third + 5, 5))


if __name__ == "__main__":
    unittest.main()
