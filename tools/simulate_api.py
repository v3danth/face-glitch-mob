"""
Simulated clients for the studio API, including the rude ones.

Bots upload photos, render with valid and invalid settings, race each other,
reuse evicted photo ids and recover the way the Studio does. Oracles: no 5xx,
every rejection is a designed 4xx, patches stay inside the photo, the same
request renders the same bytes. Prints render latency p50/p95/p99.

    python -m server.app &
    python tools/simulate_api.py --clients 6 --actions 25 --image input/input.jpg
"""

import argparse
import io
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from PIL import Image

MATERIALS = ["random", "frosted", "clear", "glossy", "prism", "ripple", "magnify", "crystal", "ice", "hazy", "chromatic", "liquid"]
TINTS = ["none", "color", "palette", "auto", "rainbow", "noise"]


class Recorder:
    """Thread-safe log of failures and render timings."""

    def __init__(self):
        self.lock = threading.Lock()
        self.failures = []
        self.latencies = []
        self.statuses = {}

    def fail(self, client, message):
        with self.lock:
            self.failures.append(f"client {client}: {message}")

    def status(self, code):
        with self.lock:
            self.statuses[code] = self.statuses.get(code, 0) + 1

    def latency(self, seconds):
        with self.lock:
            self.latencies.append(seconds * 1000.0)


def photo_bytes(path, rng):
    image = Image.open(path).convert("RGB")
    variant = rng.choice(["full", "half", "rgba", "gray"])
    if variant == "half":
        image = image.resize((image.width // 2, image.height // 2))
    buffer = io.BytesIO()
    if variant == "rgba":
        image.convert("RGBA").save(buffer, "PNG")
    elif variant == "gray":
        image.convert("L").save(buffer, "JPEG", quality=85)
    else:
        image.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


def random_style(rng):
    return {
        "material": rng.choice(MATERIALS),
        "tint": {"mode": rng.choice(TINTS), "color": "#%06x" % rng.randrange(1 << 24), "strength": rng.random()},
        "angle": rng.choice([None, rng.uniform(0, 180)]),
    }


def random_request(rng, photo, faces):
    grid = rng.randint(1, 12)
    cells = [
        {"face": rng.randrange(len(faces)), "row": rng.randrange(grid), "col": rng.randrange(grid), "style": random_style(rng)}
        for _ in range(rng.randint(0, 6))
    ] if faces else []
    return {
        "photo": photo,
        "faces": faces,
        "settings": {
            "grid": grid,
            "seed": rng.randrange(1 << 32),
            "seamless": rng.random() < 0.5,
            "likeness": rng.random(),
            "intensity": rng.uniform(0.1, 1.5),
            "distortionMin": rng.uniform(0, 30),
            "distortionMax": rng.uniform(0, 30),
            "noise": rng.uniform(0, 10),
        },
        "layout": {"grid": grid, "cells": cells},
        "base": random_style(rng),
    }


def rude_request(rng, body):
    """A request a buggy or hostile client might send; must be a clean 422."""
    body = {**body, "settings": dict(body["settings"]), "layout": dict(body["layout"])}
    kind = rng.choice(["seed", "grid", "layout", "material", "cell", "color"])
    if kind == "seed":
        body["settings"]["seed"] = rng.choice([-1, "", None, 2**40])
    elif kind == "grid":
        body["settings"]["grid"] = rng.choice([0, 13, 2.5])
    elif kind == "layout":
        body["layout"]["grid"] = body["settings"]["grid"] % 12 + 1
    elif kind == "material":
        body["base"] = {"material": "lava"}
    elif kind == "cell":
        body["layout"]["cells"] = [{"face": 0, "row": 99, "col": 0, "style": {}}]
    else:
        body["base"] = {"tint": {"mode": "color", "color": "red"}}
    return body


def check_patches(client_id, recorder, body, width, height):
    for patch in body["patches"]:
        if patch["x"] < 0 or patch["y"] < 0 or patch["x"] + patch["w"] > width or patch["y"] + patch["h"] > height:
            recorder.fail(client_id, f"patch outside photo: {patch['x'], patch['y'], patch['w'], patch['h']} in {width}x{height}")


def run_client(client_id, base_url, image, actions, seed, recorder):
    rng = random.Random(seed * 1000 + client_id)
    with httpx.Client(base_url=base_url, timeout=120) as http:
        data = photo_bytes(image, rng)

        def upload():
            response = http.post("/api/photos", files={"file": ("p.jpg", data, "image/jpeg")})
            recorder.status(response.status_code)
            if response.status_code != 200:
                recorder.fail(client_id, f"upload returned {response.status_code}: {response.text[:120]}")
                return None
            return response.json()

        photo = upload()
        if photo is None:
            return
        faces = photo["faces"] or [{"x": 10, "y": 10, "w": 80, "h": 80}]
        for _ in range(actions):
            body = random_request(rng, photo["id"], faces)
            roll = rng.random()
            if roll < 0.15:
                response = http.post("/api/render", json=rude_request(rng, body))
                recorder.status(response.status_code)
                if response.status_code != 422:
                    recorder.fail(client_id, f"rude request got {response.status_code}, wanted 422: {response.text[:120]}")
                continue
            if roll < 0.22:
                # Another tab floods the store; this client's photo may be evicted.
                for _ in range(rng.randint(1, 4)):
                    upload()
            started = time.perf_counter()
            response = http.post("/api/render", json=body)
            recorder.status(response.status_code)
            if response.status_code == 404:
                photo = upload()  # what the Studio does on expire
                if photo is None:
                    return
                continue
            if response.status_code != 200:
                recorder.fail(client_id, f"render returned {response.status_code}: {response.text[:160]}")
                continue
            recorder.latency(time.perf_counter() - started)
            result = response.json()
            check_patches(client_id, recorder, result, photo["width"], photo["height"])
            if rng.random() < 0.1:
                again = http.post("/api/render", json=body)
                if again.status_code == 200 and again.json()["patches"] != result["patches"]:
                    recorder.fail(client_id, "same request rendered different glass")


def percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--image", default="input/input.jpg")
    parser.add_argument("--clients", type=int, default=6)
    parser.add_argument("--actions", type=int, default=25)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    recorder = Recorder()
    started = time.perf_counter()
    with ThreadPoolExecutor(args.clients) as pool:
        for client_id in range(args.clients):
            pool.submit(run_client, client_id, args.url, args.image, args.actions, args.seed, recorder)
    elapsed = time.perf_counter() - started

    print(f"{args.clients} clients x {args.actions} actions in {elapsed:.1f}s; statuses {dict(sorted(recorder.statuses.items()))}")
    if recorder.latencies:
        lat = recorder.latencies
        print(
            f"render latency ms: p50 {percentile(lat, 0.5):.0f}  p95 {percentile(lat, 0.95):.0f}  "
            f"p99 {percentile(lat, 0.99):.0f}  mean {statistics.mean(lat):.0f}  (n={len(lat)})"
        )
    for failure in recorder.failures:
        print("BUG ", failure)
    print(f"{len(recorder.failures)} failure(s)")
    return 1 if recorder.failures else 0


if __name__ == "__main__":
    sys.exit(main())
