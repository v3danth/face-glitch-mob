"""
Face grid painter: per-cell glass styles chosen by clicking a face board.

Faces are often under 100 px wide in a full photo, far too small to click
individual cells, so the painter shows a board of enlarged face crops and
maps clicks on it back to (face, row, col).
"""

import cv2
import numpy as np

from utils.face import stylized_face_glass
from utils.materials import MATERIAL_NAMES

BOARD_SLOT = 320
BOARD_COLUMNS = 3
BOARD_GAP = 12

# One distinct marker colour per material (RGB), for the board and legend.
MATERIAL_COLORS = {
    "frosted": (236, 240, 245),
    "clear": (125, 211, 252),
    "glossy": (250, 204, 21),
    "prism": (244, 114, 182),
    "ripple": (56, 189, 248),
    "magnify": (163, 230, 53),
    "crystal": (192, 132, 252),
    "ice": (103, 232, 249),
    "hazy": (148, 163, 184),
    "chromatic": (251, 146, 60),
    "liquid": (52, 211, 153),
    None: (255, 255, 255),
}

_LABELS = {name: name[:2].upper() for name in MATERIAL_NAMES}
_LABELS[None] = "RND"


def slot_origin(index):
    """Top-left corner of a face's slot on the board."""
    row, col = divmod(index, BOARD_COLUMNS)
    step = BOARD_SLOT + BOARD_GAP
    return col * step, row * step


def grid_edges(length, grid_size):
    """Cell boundaries along one side, matching utils.face.tile_rects."""
    return np.linspace(0, length, grid_size + 1).round().astype(int)


def cell_at(faces, grid_size, x, y):
    """The (face, row, col) under board pixel (x, y), or None for a gap."""
    step = BOARD_SLOT + BOARD_GAP
    col_slot, lx = divmod(int(x), step)
    row_slot, ly = divmod(int(y), step)
    index = row_slot * BOARD_COLUMNS + col_slot
    if col_slot >= BOARD_COLUMNS or index >= len(faces):
        return None
    if lx >= BOARD_SLOT or ly >= BOARD_SLOT:
        return None
    _, _, w, h = faces[index]
    row = np.searchsorted(grid_edges(h, grid_size), ly * h / BOARD_SLOT, "right") - 1
    col = np.searchsorted(grid_edges(w, grid_size), lx * w / BOARD_SLOT, "right") - 1
    return index, int(min(row, grid_size - 1)), int(min(col, grid_size - 1))


def render_faces(image_bgr, faces, grid_size, cells, seed, feather, likeness, intensity):
    """
    Renders every face with its painted cells; unpainted cells use the mix.

    Each face gets its own seeded generator, so painting one cell re-renders
    the rest identically instead of reshuffling the whole picture.
    """
    output = image_bgr.copy()
    for index, box in enumerate(faces):
        face_cells = {
            (row, col): style
            for (face, row, col), style in cells.items()
            if face == index
        }
        output = stylized_face_glass(
            output,
            box,
            grid_size=grid_size,
            feather_edges=feather,
            rng=np.random.default_rng([seed, index]),
            cells=face_cells,
            likeness=likeness,
            intensity=intensity,
        )
    return output


def face_board(rendered_bgr, faces, grid_size, cells):
    """
    Enlarged face crops with the grid and painted cells marked, as RGB.

    Painted cells get a border in their material colour and a short label,
    so the board doubles as a map of the layout.
    """
    rows = (len(faces) + BOARD_COLUMNS - 1) // BOARD_COLUMNS
    cols = min(len(faces), BOARD_COLUMNS)
    step = BOARD_SLOT + BOARD_GAP
    board = np.full(
        (rows * step - BOARD_GAP, cols * step - BOARD_GAP, 3), 18, dtype=np.uint8
    )

    for index, (x, y, w, h) in enumerate(faces):
        crop = cv2.cvtColor(rendered_bgr[y : y + h, x : x + w], cv2.COLOR_BGR2RGB)
        slot = cv2.resize(crop, (BOARD_SLOT, BOARD_SLOT), interpolation=cv2.INTER_CUBIC)
        draw_grid(slot, w, h, grid_size, index, cells)
        ox, oy = slot_origin(index)
        board[oy : oy + BOARD_SLOT, ox : ox + BOARD_SLOT] = slot
    return board


def draw_grid(slot, w, h, grid_size, index, cells):
    """Draws grid lines and painted-cell markers onto one enlarged face slot."""
    xs = (grid_edges(w, grid_size) * BOARD_SLOT / w).round().astype(int)
    ys = (grid_edges(h, grid_size) * BOARD_SLOT / h).round().astype(int)
    for edge in xs:
        cv2.line(slot, (int(edge), 0), (int(edge), BOARD_SLOT), (255, 255, 255), 1)
    for edge in ys:
        cv2.line(slot, (0, int(edge)), (BOARD_SLOT, int(edge)), (255, 255, 255), 1)

    font_scale = float(np.clip((xs[1] - xs[0]) / 70.0, 0.3, 0.6))
    for (face, row, col), style in cells.items():
        if face != index or row >= grid_size or col >= grid_size:
            continue
        x0, x1, y0, y1 = int(xs[col]), int(xs[col + 1]), int(ys[row]), int(ys[row + 1])
        color = MATERIAL_COLORS[style.material]
        cv2.rectangle(slot, (x0 + 1, y0 + 1), (x1 - 2, y1 - 2), color, 2)
        cv2.putText(
            slot,
            _LABELS[style.material],
            (x0 + 4, y0 + int(16 * font_scale / 0.5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            1,
            cv2.LINE_AA,
        )


def legend_html():
    """Colour key for the board markers."""
    chips = "".join(
        f'<span class="legend-chip"><i style="background:rgb{MATERIAL_COLORS[name]}"></i>'
        f"{_LABELS[name]} {name or 'random'}</span>"
        for name in [None, *MATERIAL_NAMES]
    )
    return f'<div class="legend">{chips}</div>'
