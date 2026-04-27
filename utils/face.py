import numpy as np

from config import Config

from .blending import blend
from .tiles import apply_glass_tile, choose_mode


def process_tile(face, output, x0, y0, bw, bh):

    block = face[y0 : y0 + bh, x0 : x0 + bw]

    mode = choose_mode()

    processed = apply_glass_tile(block, mode)

    mask = np.ones((bh, bw, 3), dtype=np.float32)

    region = output[y0 : y0 + bh, x0 : x0 + bw]

    blended = blend(region, processed, mask)

    output[y0 : y0 + bh, x0 : x0 + bw] = blended


def stylized_face_glass(image, face_box, grid_size=None):
    """
    Apply stylized glass effect to a face region.
    grid_size: number of tiles per face side (int, optional)
    """
    if grid_size is None:
        grid_size = Config.GRID_SIZE
    x, y, w, h = face_box
    face = image[y : y + h, x : x + w].copy()
    output = face.copy()

    tile_w = w // grid_size
    tile_h = h // grid_size

    extra_w = w % grid_size
    extra_h = h % grid_size

    y_cursor = 0
    for i in range(grid_size):
        bh = tile_h + (1 if i < extra_h else 0)

        x_cursor = 0
        for j in range(grid_size):
            bw = tile_w + (1 if j < extra_w else 0)

            process_tile(face, output, x_cursor, y_cursor, bw, bh)
            x_cursor += bw

        y_cursor += bh

    image[y : y + h, x : x + w] = output
    return image
