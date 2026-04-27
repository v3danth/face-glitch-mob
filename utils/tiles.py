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


def choose_mode(rng=random):
    # return rng.choices(
    #     ["frosted", "clear", "glossy"],
    #     weights=[0.6, 0.2, 0.2],
    #     k=1
    # )[0]

    modes = [
        "frosted",
        "clear",
        "glossy",
        # "prism",
        # "ripple",
        # "magnify",
        # "crystal",
        "ice",
        # "hazy",
    ]

    weights = [
        0.35,  # frosted (most common)
        0.15,  # clear
        0.15,  # glossy
        # 0.08,  # prism
        # 0.08,  # ripple
        # 0.06,  # magnify
        # 0.05,  # crystal
        0.04,  # ice
        # 0.04,  # hazy
    ]

    return rng.choices(modes, k=1)[0]
