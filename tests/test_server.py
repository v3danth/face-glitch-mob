import io
import unittest

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from server.app import MAX_PHOTOS, app

client = TestClient(app)


def png_bytes(width=200, height=160, mode="RGB"):
    rng = np.random.default_rng(0)
    pixels = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels).convert(mode).save(buffer, "PNG")
    return buffer.getvalue()


def upload(data=None):
    response = client.post("/api/photos", files={"file": ("p.png", data or png_bytes(), "image/png")})
    return response


def render_body(photo, grid=3, cells=(), seed=7, faces=None):
    return {
        "photo": photo,
        "faces": faces if faces is not None else [{"x": 40, "y": 30, "w": 90, "h": 90}],
        "settings": {"grid": grid, "seed": seed, "seamless": True},
        "layout": {"grid": grid, "cells": list(cells)},
    }


class ServerTest(unittest.TestCase):
    def test_materials_match_the_shared_front_end_catalogue(self):
        with open("frontend/shared/model.js", encoding="utf-8") as f:
            model = f.read()
        catalogue = client.get("/api/materials").json()
        for name in catalogue["materials"] + catalogue["tint_modes"]:
            self.assertIn(f"'{name}'", model, f"{name} missing from frontend/shared/model.js")

    def test_upload_keeps_full_resolution_and_odd_modes(self):
        for mode in ("RGB", "RGBA", "L"):
            with self.subTest(mode=mode):
                body = upload(png_bytes(321, 207, mode)).json()
                self.assertEqual((body["width"], body["height"]), (321, 207))
                self.assertEqual(len(body["id"]), 32)

    def test_non_image_is_rejected_cleanly(self):
        self.assertEqual(upload(b"definitely not a photo").status_code, 415)

    def test_render_returns_patches_inside_the_photo(self):
        photo = upload().json()["id"]
        response = client.post("/api/render", json=render_body(photo))
        self.assertEqual(response.status_code, 200, response.text)
        (patch,) = response.json()["patches"]
        self.assertTrue(patch["data"].startswith("data:image/png;base64,"))
        self.assertLessEqual(patch["x"] + patch["w"], 200)
        self.assertLessEqual(patch["y"] + patch["h"], 160)

    def test_same_request_renders_the_same_glass(self):
        photo = upload().json()["id"]
        first = client.post("/api/render", json=render_body(photo)).json()["patches"]
        second = client.post("/api/render", json=render_body(photo)).json()["patches"]
        self.assertEqual(first, second)

    def test_layout_painted_on_another_grid_is_refused(self):
        photo = upload().json()["id"]
        body = render_body(photo, grid=3)
        body["layout"]["grid"] = 4
        self.assertEqual(client.post("/api/render", json=body).status_code, 422)

    def test_bad_settings_are_rejected_not_crashed(self):
        photo = upload().json()["id"]
        for settings in ({"seed": -1}, {"grid": 0}, {"intensity": 9}, {"seed": "x"}):
            body = render_body(photo)
            body["settings"].update(settings)
            with self.subTest(settings=settings):
                self.assertEqual(client.post("/api/render", json=body).status_code, 422)

    def test_inverted_distortion_range_renders(self):
        photo = upload().json()["id"]
        body = render_body(photo)
        body["settings"].update(distortionMin=25, distortionMax=2)
        self.assertEqual(client.post("/api/render", json=body).status_code, 200)

    def test_evicted_photo_is_a_404_the_client_can_recover_from(self):
        first = upload().json()["id"]
        for _ in range(MAX_PHOTOS):
            upload()
        self.assertEqual(client.post("/api/render", json=render_body(first)).status_code, 404)

    def test_out_of_bounds_face_is_clamped(self):
        photo = upload().json()["id"]
        body = render_body(photo, faces=[{"x": 190, "y": 150, "w": 500, "h": 500}])
        (patch,) = client.post("/api/render", json=body).json()["patches"]
        self.assertLessEqual(patch["x"] + patch["w"], 200)


class OverlapTest(unittest.TestCase):
    def test_overlap_is_intersection_over_union(self):
        from utils.detect import overlap

        self.assertEqual(overlap((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)
        self.assertEqual(overlap((0, 0, 10, 10), (20, 20, 5, 5)), 0.0)
        self.assertAlmostEqual(overlap((0, 0, 10, 10), (5, 0, 10, 10)), 50 / 150)


if __name__ == "__main__":
    unittest.main()
