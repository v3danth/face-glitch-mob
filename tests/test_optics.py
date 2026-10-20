import unittest

import numpy as np

from utils import optics
from utils.face import crossfade, stylized_face_glass
from utils.materials import MATERIAL_NAMES


class OpticsTest(unittest.TestCase):
    def test_cauchy_reproduces_catalogue_index(self):
        b, g, r = optics.channel_iors(1.5168, 64.17)  # Schott N-BK7
        self.assertGreater(b, g)
        self.assertGreater(g, r)
        self.assertAlmostEqual(g, 1.5168, delta=0.002)

    def test_no_dispersion_without_abbe(self):
        self.assertEqual(optics.channel_iors(1.5, None), (1.5, 1.5, 1.5))

    def test_flat_glass_does_not_shift_the_image(self):
        nx, ny, nz = optics.surface_normals(np.zeros(4), np.zeros(4))
        dx, dy = optics.refraction_offsets(nx, ny, nz, np.full(4, 10.0), 1.5)
        np.testing.assert_allclose(dx, 0.0, atol=1e-6)
        np.testing.assert_allclose(dy, 0.0, atol=1e-6)

    def test_convex_lens_bends_rays_toward_its_centre(self):
        # On the right flank of a dome the height falls as x grows.
        nx, ny, nz = optics.surface_normals(np.array([-0.5]), np.array([0.0]))
        dx, _ = optics.refraction_offsets(nx, ny, nz, np.array([10.0]), 1.5)
        self.assertLess(dx[0], 0.0)

    def test_snell_matches_scalar_law(self):
        theta = np.deg2rad(30.0)
        nx, ny, nz = np.sin(theta), 0.0, np.cos(theta)
        dx, _ = optics.refraction_offsets(nx, ny, nz, 1.0, 1.5)
        refracted = np.arcsin(np.sin(theta) / 1.5)
        self.assertAlmostEqual(-dx, np.tan(theta - refracted), places=5)

    def test_fresnel_is_four_percent_at_normal_incidence(self):
        self.assertAlmostEqual(optics.fresnel(1.0, 1.5), 0.04, places=6)
        self.assertAlmostEqual(optics.fresnel(0.0, 1.5), 1.0, places=6)


class RenderTest(unittest.TestCase):
    def test_every_material_renders_finite_pixels(self):
        rng = np.random.default_rng(0)
        image = rng.integers(0, 256, (90, 90, 3), dtype=np.uint8)
        for name in MATERIAL_NAMES:
            with self.subTest(material=name):
                out = stylized_face_glass(
                    image.copy(), (10, 10, 70, 70), 4, name, True, rng
                )
                self.assertEqual(out.dtype, np.uint8)
                self.assertFalse(np.array_equal(out, image))

    def test_seeded_render_is_reproducible(self):
        image = np.full((60, 60, 3), 128, dtype=np.uint8)
        image[::7] = 255
        first = stylized_face_glass(
            image.copy(), (0, 0, 60, 60), 3, None, True, np.random.default_rng(5)
        )
        second = stylized_face_glass(
            image.copy(), (0, 0, 60, 60), 3, None, True, np.random.default_rng(5)
        )
        np.testing.assert_array_equal(first, second)


class SeamTest(unittest.TestCase):
    def test_neighbouring_crossfades_sum_to_one(self):
        # Three tiles of a 30 px face with a 4 px overlap: any gap in the sum
        # would let the unaltered photo show through between tiles.
        total = sum(crossfade(30, start, start + 10, 4) for start in (0, 10, 20))
        np.testing.assert_allclose(total[4:26], 1.0, atol=1e-6)

    def test_hard_tiles_do_not_overlap(self):
        np.testing.assert_array_equal(crossfade(6, 2, 4, 0), [0, 0, 1, 1, 0, 0])


if __name__ == "__main__":
    unittest.main()
