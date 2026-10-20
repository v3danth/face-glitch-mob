"""
Height fields for the top face of a glass tile.

Each builder takes the tile size, a numpy Generator and a relief multiplier
and returns a Surface in pixel units. Slopes are returned alongside the
height because faceted and ridged glass have exact slopes that numerical
differentiation would smear across the edges.
"""

from typing import NamedTuple

import cv2
import numpy as np


class Surface(NamedTuple):
    thickness: np.ndarray
    """Glass thickness above the photo, in pixels (h x w)."""
    gx: np.ndarray
    """Slope dh/dx (h x w)."""
    gy: np.ndarray
    """Slope dh/dy (h x w)."""
    coverage: np.ndarray | None = None
    """Fraction of each pixel covered by glass; None means fully covered."""


def from_height(height, coverage=None):
    """Surface of a smooth height field, offset so the thinnest point is 0."""
    gy, gx = np.gradient(height)
    return Surface(height - height.min(), gx, gy, coverage)


def unit_coords(h, w):
    """Tile coordinates scaled to [-1, 1] on each axis, as broadcastable arrays."""
    u = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    v = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
    return u, v


def smooth_noise(h, w, rng, sigma):
    """Zero-mean, unit-variance Gaussian noise correlated over sigma pixels."""
    noise = rng.standard_normal((h, w), dtype=np.float32)
    noise = cv2.GaussianBlur(noise, (0, 0), sigma, borderType=cv2.BORDER_REFLECT)
    return noise / (noise.std() + 1e-6)


def inset_distance(h, w, corner_radius):
    """
    Distance from each pixel centre to the edge of a rounded rectangle.

    Positive inside, negative outside. Used for the
    capsule-like outline of liquid glass.
    """
    r = min(corner_radius, w / 2.0, h / 2.0)
    px = np.abs(np.arange(w, dtype=np.float32) + 0.5 - w / 2.0)[None, :]
    py = np.abs(np.arange(h, dtype=np.float32) + 0.5 - h / 2.0)[:, None]
    qx = px - (w / 2.0 - r)
    qy = py - (h / 2.0 - r)
    outside = np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
    inside = np.minimum(np.maximum(qx, qy), 0.0)
    return r - outside - inside


def quarter_round(distance, width):
    """Profile of a rounded edge: 0 at the rim, rising to 1 at `width` inward."""
    t = np.clip(distance / width, 0.0, 1.0)
    return np.sqrt(1.0 - (1.0 - t) ** 2)


def cathedral(h, w, rng, relief):
    """Rolled cathedral glass: gentle hammered waves a few per tile."""
    size = min(h, w)
    sigma = max(size / 5.0, 1.0)
    return from_height(0.6 * sigma * relief * smooth_noise(h, w, rng, sigma))


def etched(h, w, rng, relief):
    """
    Acid-etched glass: optically flat at pixel scale.

    The etch pits are microns across, far below a pixel, so they never show
    as bumps; they only scatter light, which the material's roughness models.
    Drawing them at pixel size is what made frosted look hammered.
    """
    zeros = np.zeros((h, w), dtype=np.float32)
    return Surface(zeros, zeros, zeros)


def pillow(h, w, rng, relief):
    """A polished cushion that bulges in the middle and flattens at the rim."""
    u, v = unit_coords(h, w)
    peak = 0.12 * min(h, w) * relief
    return from_height(peak * (1.0 - u**4) * (1.0 - v**4))


def ridges(h, w, rng, relief, angle=None):
    """
    Prism film: parallel sawtooth wedges.

    angle is the direction the ridges run, in degrees counter-clockwise from
    horizontal as seen on screen; None picks one at random.
    """
    if angle is None:
        angle = rng.uniform(0.0, 180.0)
    # Ridges run along (cos a, -sin a) in image space, so the slope points
    # across them along (sin a, cos a).
    across_x, across_y = np.sin(np.deg2rad(angle)), np.cos(np.deg2rad(angle))
    period = max(min(h, w) / 2.0, 3.0)
    slope = 0.75 * relief
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    phase = np.mod(xx * across_x + yy * across_y, period)
    gx = np.full((h, w), slope * across_x, dtype=np.float32)
    gy = np.full((h, w), slope * across_y, dtype=np.float32)
    return Surface(slope * phase, gx, gy)


def waves(h, w, rng, relief):
    """Water drops: damped concentric waves from a centre near the tile."""
    size = min(h, w)
    cx, cy = rng.uniform(-0.5, 1.5) * w, rng.uniform(-0.5, 1.5) * h
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot(xx - cx, yy - cy)
    k = 2.0 * np.pi / max(size * 0.4, 2.0)
    amplitude = 0.7 * relief / k
    phase = rng.uniform(0.0, 2.0 * np.pi)
    return from_height(amplitude * np.sin(k * r + phase) * np.exp(-r / (2.0 * size)))


def lens(h, w, rng, relief):
    """
    Plano-convex lens ground to a rounded square that fills the tile.

    A round lens leaves the tile corners flat and reads as a grid of
    bubbles; a squircle contour (|u|^4 + |v|^4) keeps the lensing but
    tiles the face edge to edge.
    """
    u, v = unit_coords(h, w)
    sag = 0.2 * min(h, w) * relief
    return from_height(sag * np.maximum(1.0 - np.sqrt(u**4 + v**4), 0.0))


def facets(h, w, rng, relief):
    """Cut crystal: Voronoi cells, each a flat face tilted a different way."""
    count = int(rng.integers(5, 10))
    seeds = rng.uniform((0.0, 0.0), (w, h), size=(count, 2)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dist = (xx[None] - seeds[:, 0, None, None]) ** 2 + (
        yy[None] - seeds[:, 1, None, None]
    ) ** 2
    cell = dist.argmin(axis=0)

    tilt = rng.uniform(0.25, 0.65, count) * relief
    angle = rng.uniform(0.0, 2.0 * np.pi, count)
    sx = (tilt * np.cos(angle)).astype(np.float32)
    sy = (tilt * np.sin(angle)).astype(np.float32)
    gx, gy = sx[cell], sy[cell]
    height = gx * (xx - seeds[cell, 0]) + gy * (yy - seeds[cell, 1])
    return Surface(height - height.min(), gx, gy)


def streaks(h, w, rng, relief, angle=None):
    """
    Ice: frozen-in flow streaks running in one direction.

    angle is the streak direction in degrees counter-clockwise from
    horizontal as seen on screen; None picks one at random.
    """
    if angle is None:
        angle = rng.uniform(0.0, 180.0)
    size = min(h, w)
    span = int(np.ceil(np.hypot(h, w))) + 2
    noise = rng.standard_normal((span, span), dtype=np.float32)
    noise = cv2.GaussianBlur(noise, (0, 0), sigmaX=max(size / 2.5, 1.0), sigmaY=0.9)
    turn = cv2.getRotationMatrix2D((span / 2.0, span / 2.0), angle, 1.0)
    noise = cv2.warpAffine(noise, turn, (span, span), borderMode=cv2.BORDER_REFLECT)
    top, left = (span - h) // 2, (span - w) // 2
    field = noise[top : top + h, left : left + w]
    field = field / (field.std() + 1e-6)
    return from_height(0.9 * relief * field)


def capsule(h, w, rng, relief):
    """
    Liquid glass: a flat slab whose rim curls over like a meniscus.

    All the curvature lives in a narrow bezel, so the centre stays calm while
    the rim acts as a strong lens and catches the light, which is the look
    of Apple's Liquid Glass.
    """
    size = min(h, w)
    distance = inset_distance(h, w, corner_radius=0.22 * size)
    bezel = max(0.24 * size, 1.5)
    height = 0.2 * size * relief * quarter_round(distance, bezel)
    coverage = np.clip(distance + 0.5, 0.0, 1.0)
    return from_height(height, coverage)


def with_bumps(surface, rng, amplitude):
    """Adds sub-tile manufacturing ripple, so no two tiles refract identically."""
    h, w = surface.thickness.shape
    gy, gx = np.gradient(amplitude * smooth_noise(h, w, rng, 1.5))
    return surface._replace(gx=surface.gx + gx, gy=surface.gy + gy)

