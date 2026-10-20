"""
Gradio callbacks for the face grid painter.

State is a dict {"image": BGR array, "faces": [(x, y, w, h)],
"cells": {(face, row, col): TileStyle}}. Every callback returns a new state
and fresh renders, so the board always shows what the output will be.
"""

import logging

import cv2
import gradio as gr
import numpy as np

from utils.detect import detect_faces
from utils.tiles import TileStyle
from utils.tints import Tint, parse_color
from web.painter import cell_at, face_board, render_faces

logger = logging.getLogger("face_glitch_mob_web_painter")


def brush_style(material, tint_mode, color, strength, random_direction, angle):
    """The TileStyle the UI's brush controls describe."""
    return TileStyle(
        material=None if material == "random" else material,
        tint=Tint(mode=tint_mode, color=parse_color(color), strength=float(strength)),
        angle=None if random_direction else float(angle),
    )


def valid_seed(seed):
    """Empty or negative seeds from the number box would crash numpy."""
    try:
        return min(abs(int(seed)), 2**32 - 1)
    except (TypeError, ValueError):
        return 7


def refresh(state, grid_size, seed, feather, likeness, intensity):
    """Board and full output for the current state."""
    if not state:
        return None, None
    rendered = render_faces(
        state["image"],
        state["faces"],
        int(grid_size),
        state["cells"],
        valid_seed(seed),
        feather,
        float(likeness),
        float(intensity),
    )
    board = face_board(rendered, state["faces"], int(grid_size), state["cells"])
    return board, cv2.cvtColor(rendered, cv2.COLOR_BGR2RGB)


def load_image(
    input_image, grid_size, seed, feather, likeness, intensity, scale, det_scale, det_neighbors, det_thresh
):
    """Detects faces in a new upload and starts with every cell unpainted."""
    if input_image is None:
        return None, None, None, "Upload an image first."
    image = cv2.cvtColor(np.array(input_image.convert("RGB")), cv2.COLOR_RGB2BGR)
    faces = detect_faces(image, det_scale, det_neighbors, det_thresh, scale)
    logger.info(f"Painter detected {len(faces)} face(s).")
    if not faces:
        return None, None, None, "No faces found. Lower the threshold or min neighbours."

    state = {"image": image, "faces": faces, "cells": {}}
    board, output = refresh(state, grid_size, seed, feather, likeness, intensity)
    return state, board, output, f"Found {len(faces)} face(s). Click cells to paint them."


def paint_cell(state, grid_size, seed, feather, likeness, intensity, *brush, evt: gr.SelectData):
    """
    Paints the clicked cell with the brush.

    Clicking a cell that already has exactly this style clears it, so the
    same click toggles a mistake off.
    """
    if not state:
        return state, None, None
    hit = cell_at(state["faces"], int(grid_size), *evt.index)
    if hit is None:
        return (state, *refresh(state, grid_size, seed, feather, likeness, intensity))

    style = brush_style(*brush)
    cells = dict(state["cells"])
    if cells.get(hit) == style:
        del cells[hit]
    else:
        cells[hit] = style
    state = {**state, "cells": cells}
    return (state, *refresh(state, grid_size, seed, feather, likeness, intensity))


def paint_all(state, grid_size, seed, feather, likeness, intensity, *brush):
    """Paints every cell of every face with the brush."""
    if not state:
        return state, None, None
    style = brush_style(*brush)
    n = int(grid_size)
    cells = {
        (face, row, col): style
        for face in range(len(state["faces"]))
        for row in range(n)
        for col in range(n)
    }
    state = {**state, "cells": cells}
    return (state, *refresh(state, grid_size, seed, feather, likeness, intensity))


def clear_cells(state, grid_size, seed, feather, likeness, intensity):
    """Back to the random mix everywhere; also used when the grid changes."""
    if not state:
        return state, None, None
    state = {**state, "cells": {}}
    return (state, *refresh(state, grid_size, seed, feather, likeness, intensity))


def rerender(state, grid_size, seed, feather, likeness, intensity):
    return (state, *refresh(state, grid_size, seed, feather, likeness, intensity))
