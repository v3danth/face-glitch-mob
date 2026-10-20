import cv2
import numpy as np

from config import Config

from .tiles import apply_glass_tile, as_tile_style

# Light adds linearly, so blur and Fresnel mixing happen in linear light;
# blurring sRGB values directly darkens highlights and muddies edges.
_TO_LINEAR = ((np.arange(256, dtype=np.float32) / 255.0) ** 2.2).astype(np.float32)


# Neighbouring tiles overlap by this fraction of a tile and cross-fade, so
# no line marks where one glass type ends and the next begins.
_OVERLAP = 0.35


def to_linear(srgb):
    return _TO_LINEAR[srgb]


def to_srgb(linear):
    return (np.clip(linear, 0.0, 1.0) ** (1.0 / 2.2) * 255.0 + 0.5).astype(np.uint8)


def keep_likeness(source, output, sigma, likeness):
    """
    Puts the original's coarse picture back under the glass detail.

    A hybrid image: viewers recognise a small picture from its low spatial
    frequencies and read detail only when zoomed in. Swapping the glass
    render's low band (Gaussian sigma ~ 0.3 tile) for the original's keeps
    the face recognisable as a thumbnail, while every feature finer than a
    tile, such as eyes, mouth and skin texture, stays pure glass.
    Physically it is the energy budget of ideal glass, which only redirects
    light, so each tile passes on the light that falls on it.
    """
    if likeness <= 0:
        return output
    coarse_source = cv2.GaussianBlur(source, (0, 0), sigma, borderType=cv2.BORDER_REFLECT)
    coarse_output = cv2.GaussianBlur(output, (0, 0), sigma, borderType=cv2.BORDER_REFLECT)
    return output + likeness * (coarse_source - coarse_output)


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def crossfade(length, start, end, margin):
    """
    Weight along one axis for a tile covering [start, end) plus `margin`.

    Ramps are smoothsteps 2*margin wide centred on the tile edges; a falling
    ramp and its neighbour's rising ramp always sum to 1, so overlapping
    tiles never let the photo show through between them.
    """
    centres = np.arange(length, dtype=np.float32) + 0.5
    if margin <= 0:
        return ((centres >= start) & (centres < end)).astype(np.float32)
    rise = smoothstep((centres - (start - margin)) / (2.0 * margin))
    fall = smoothstep(((end + margin) - centres) / (2.0 * margin))
    return rise * fall


def edge_fade(length, start, end, margin):
    """1 across [start, end), easing to 0 over `margin` outside it."""
    centres = np.arange(length, dtype=np.float32) + 0.5
    if margin <= 0:
        return ((centres >= start) & (centres < end)).astype(np.float32)
    rise = smoothstep((centres - (start - margin)) / margin)
    fall = smoothstep(((end + margin) - centres) / margin)
    return rise * fall


def tile_rects(w, h, grid_size):
    """
    Splits a w x h box into grid_size^2 tiles, spreading the remainder.

    Yields ((row, col), (x, y, w, h)) so callers can address painted cells.
    """
    xs = np.linspace(0, w, grid_size + 1).round().astype(int)
    ys = np.linspace(0, h, grid_size + 1).round().astype(int)
    for row, (y0, y1) in enumerate(zip(ys[:-1], ys[1:])):
        for col, (x0, x1) in enumerate(zip(xs[:-1], xs[1:])):
            if x1 > x0 and y1 > y0:
                yield (row, col), (int(x0), int(y0), int(x1 - x0), int(y1 - y0))


def stylized_face_glass(
    image,
    face_box,
    grid_size=None,
    style=None,
    feather_edges=True,
    rng=None,
    cells=None,
    likeness=None,
    intensity=None,
    distortion=None,
    noise=None,
):
    """
    Covers a face with a grid of physically shaded glass tiles.

    grid_size: number of tiles per face side (int, optional)
    style: material name, TileStyle, or None for a random mix (optional)
    feather_edges: blend tiles into one seamless sheet that fades into the
        photo outside the face box; False gives hard-edged tiles (bool)
    rng: numpy Generator, for reproducible renders (optional)
    cells: {(row, col): TileStyle} overriding `style` per tile (optional)
    likeness: 0-1, how recognisable a thumbnail stays (default Config.LIKENESS)
    intensity: scales glass blur and distortion; lower shows more of the
        face (default Config.INTENSITY)
    distortion: (min, max) surface relief strength, ~8 is nominal
        (default Config)
    noise: manufacturing ripple strength (default Config.NOISE_FACTOR)
    """
    if grid_size is None:
        grid_size = Config.GRID_SIZE
    if rng is None:
        rng = np.random.default_rng()
    if intensity is None:
        intensity = Config.INTENSITY
    if likeness is None:
        likeness = Config.LIKENESS

    x, y, w, h = face_box
    tile = min(w, h) / grid_size
    margin = int(round(_OVERLAP * tile)) if feather_edges else 0

    # Work on the face box plus a margin, so edge tiles have room to fade.
    ih, iw = image.shape[:2]
    x0, y0 = max(x - margin, 0), max(y - margin, 0)
    x1, y1 = min(x + w + margin, iw), min(y + h + margin, ih)
    source = to_linear(image[y0:y1, x0:x1])
    ch, cw = source.shape[:2]
    fx, fy = x - x0, y - y0

    light = np.zeros_like(source)
    weight = np.zeros((ch, cw), dtype=np.float32)
    default = as_tile_style(style)
    cells = cells or {}

    for cell, (tx, ty, tw, th) in tile_rects(w, h, grid_size):
        cx, cy = fx + tx, fy + ty
        ex0, ey0 = max(cx - margin, 0), max(cy - margin, 0)
        ex1, ey1 = min(cx + tw + margin, cw), min(cy + th + margin, ch)
        rendered = apply_glass_tile(
            source,
            (ex0, ey0, ex1 - ex0, ey1 - ey0),
            cells.get(cell, default),
            rng,
            intensity,
            distortion,
            noise,
        )
        tile_weight = np.outer(
            crossfade(ch, cy, cy + th, margin)[ey0:ey1],
            crossfade(cw, cx, cx + tw, margin)[ex0:ex1],
        )
        light[ey0:ey1, ex0:ex1] += rendered * tile_weight[..., None]
        weight[ey0:ey1, ex0:ex1] += tile_weight

    covered = weight > 1e-6
    output = source.copy()
    output[covered] = light[covered] / weight[covered][:, None]
    output = keep_likeness(source, output, 0.3 * tile, likeness)

    # Fully glass inside the face box, easing into the photo only outside it.
    inside = np.outer(edge_fade(ch, fy, fy + h, margin), edge_fade(cw, fx, fx + w, margin))
    output = inside[..., None] * output + (1.0 - inside[..., None]) * source
    image[y0:y1, x0:x1] = to_srgb(output)
    return image
