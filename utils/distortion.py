import random

import numpy as np

from config import Config


def random_distortion_strength():

    return random.uniform(
        Config.DISTORTION_STRENGTH_MIN, Config.DISTORTION_STRENGTH_MAX
    )


def radial_distortion(nx, ny, r, strength):

    dx = strength * nx / r

    dy = strength * ny / r

    return dx, dy


def add_noise(dx, dy, height, width):

    noise = np.random.randn(height, width).astype(np.float32)

    dx += noise * Config.NOISE_FACTOR
    dy += noise * Config.NOISE_FACTOR

    return dx, dy
