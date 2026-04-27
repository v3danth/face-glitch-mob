import numpy as np


def create_meshgrid(height, width):

    yy, xx = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")

    return xx, yy


def normalize_coords(xx, yy, width, height):

    nx = (xx - width / 2) / width

    ny = (yy - height / 2) / height

    return nx, ny


def compute_radius(nx, ny):

    return np.sqrt(nx**2 + ny**2) + 1e-6
