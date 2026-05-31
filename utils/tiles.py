import random

from .distortion import add_noise, radial_distortion, random_distortion_strength
from .materials import apply_material
from .mesh import compute_radius, create_meshgrid, normalize_coords
from .remap import create_remap, remap_image


def apply_glass_tile(block, mode):

    h, w = block.shape[:2]

    xx, yy = create_meshgrid(h, w)

    nx, ny = normalize_coords(xx, yy, w, h)

    r = compute_radius(nx, ny)

    strength = random_distortion_strength()

    dx, dy = radial_distortion(nx, ny, r, strength)

    dx, dy = add_noise(dx, dy, h, w)

    map_x, map_y = create_remap(xx, yy, dx, dy)

    distorted = remap_image(block, map_x, map_y)

    return apply_material(distorted, map_x, map_y, mode)


def choose_mode(rng=random, style=None):
    valid_modes = [
        "frosted",
        "clear",
        "glossy",
        "prism",
        "ripple",
        "magnify",
        "crystal",
        "ice",
        "hazy",
        "chromatic",
    ]

    if style in valid_modes:
        return style

    weights = [
        0.35,  # frosted
        0.10,  # clear
        0.10,  # glossy
        0.10,  # prism
        0.10,  # ripple
        0.05,  # magnify
        0.05,  # crystal
        0.05,  # ice
        0.05,  # hazy
        0.05,  # chromatic
    ]

    return rng.choices(valid_modes, weights=weights, k=1)[0]
