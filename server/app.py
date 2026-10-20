"""
Local server for the two front ends.

Serves frontend/ (Studio at /studio/, Glass GL at /gl/) and the API the
Studio renders through. Binds to 127.0.0.1 only: photos are private and the
server holds them in memory, never on disk.

    python -m server.app            # http://127.0.0.1:8000/studio/
"""

import base64
import io
import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from typing import Literal

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, model_validator

from config import Config
from utils.detect import clamp_box, detect_faces_multiscale
from utils.face import stylized_face_glass
from utils.materials import MATERIAL_NAMES, MATERIALS
from utils.tiles import TileStyle
from utils.tints import PALETTE, TINT_MODES, Tint, parse_color

logger = logging.getLogger("face_glitch_mob_server")

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

MAX_PHOTOS = 6
"""Decoded photos kept in memory (LRU). A 12 MP photo is about 36 MB."""

MAX_UPLOAD_BYTES = 40 * 1024 * 1024
MAX_PIXELS = 60_000_000
MAX_FACES = 32

DETECT_THRESHOLD = 2.0
"""Haar confidence a face must reach at one size; voting across sizes does
the false-positive rejection a single high threshold used to."""

# Rendering is CPU bound and copies the photo; two at a time keeps memory
# bounded while one user's slider drags queue behind each other.
_render_slots = threading.BoundedSemaphore(2)


class PhotoStore:
    """Bounded in-memory photo cache with least-recently-used eviction."""

    def __init__(self, capacity):
        self.capacity = capacity
        self._photos = OrderedDict()
        self._lock = threading.Lock()

    def add(self, image):
        photo_id = uuid.uuid4().hex
        with self._lock:
            self._photos[photo_id] = image
            while len(self._photos) > self.capacity:
                self._photos.popitem(last=False)
        return photo_id

    def get(self, photo_id):
        with self._lock:
            image = self._photos.get(photo_id)
            if image is not None:
                self._photos.move_to_end(photo_id)
            return image


store = PhotoStore(MAX_PHOTOS)

MaterialName = Literal[tuple(["random", *MATERIAL_NAMES])]
TintMode = Literal[tuple(TINT_MODES)]


class TintModel(BaseModel):
    mode: TintMode = "none"
    color: str = Field("#5aaaff", pattern=r"^#[0-9a-fA-F]{6}$")
    strength: float = Field(0.5, ge=0.0, le=1.0)


class StyleModel(BaseModel):
    material: MaterialName = "random"
    tint: TintModel = TintModel()
    angle: float | None = Field(None, ge=0.0, le=180.0)

    def to_tile_style(self):
        return TileStyle(
            material=None if self.material == "random" else self.material,
            tint=Tint(self.tint.mode, parse_color(self.tint.color), self.tint.strength),
            angle=self.angle,
        )


class FaceModel(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=4)
    h: int = Field(ge=4)


class CellModel(BaseModel):
    face: int = Field(ge=0, lt=MAX_FACES)
    row: int = Field(ge=0, lt=12)
    col: int = Field(ge=0, lt=12)
    style: StyleModel


class LayoutModel(BaseModel):
    grid: int = Field(ge=1, le=12)
    cells: list[CellModel] = Field(default_factory=list, max_length=12 * 12 * MAX_FACES)


class SettingsModel(BaseModel):
    grid: int = Field(4, ge=1, le=12)
    seed: int = Field(7, ge=0, le=2**32 - 1)
    seamless: bool = True
    likeness: float = Field(0.9, ge=0.0, le=1.0)
    intensity: float = Field(1.0, ge=0.1, le=1.5)
    distortionMin: float = Field(5.0, ge=0.0, le=30.0)
    distortionMax: float = Field(12.0, ge=0.0, le=30.0)
    noise: float = Field(2.0, ge=0.0, le=10.0)


class RenderRequest(BaseModel):
    photo: str = Field(pattern=r"^[0-9a-f]{32}$")
    faces: list[FaceModel] = Field(max_length=MAX_FACES)
    settings: SettingsModel
    layout: LayoutModel
    base: StyleModel = StyleModel()

    @model_validator(mode="after")
    def layout_matches_grid(self):
        # A layout painted on another grid would be read at the wrong cells.
        if self.layout.grid != self.settings.grid:
            raise ValueError("layout grid differs from settings grid")
        for cell in self.layout.cells:
            if cell.row >= self.layout.grid or cell.col >= self.layout.grid:
                raise ValueError("cell outside the grid")
            if cell.face >= len(self.faces):
                raise ValueError("cell refers to a face that does not exist")
        return self


def decode_photo(data):
    """BGR pixels of an upload, upright as the browser shows it."""
    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_PIXELS:
            raise HTTPException(413, "Photo has too many pixels.")
        image = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(415, "Not a readable image.") from exc
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def patch_margin(face, grid):
    """Pixels the glass can spill past a face box (seamless edge fade)."""
    return int(np.ceil(0.35 * min(face.w, face.h) / grid)) + 1


def encode_png(bgr):
    ok, buffer = cv2.imencode(".png", bgr, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    if not ok:
        raise HTTPException(500, "Could not encode the render.")
    return "data:image/png;base64," + base64.b64encode(buffer).decode("ascii")


app = FastAPI(title="Face Glitch Mob", docs_url=None, redoc_url=None)


@app.get("/api/materials")
def materials():
    """Catalogue the front ends check themselves against."""
    return {
        "materials": MATERIAL_NAMES,
        "directional": [name for name in MATERIAL_NAMES if MATERIALS[name].directional],
        "tint_modes": TINT_MODES,
        "palette": [list(color) for color in PALETTE],
    }


@app.post("/api/photos")
def upload_photo(file: UploadFile = File(...)):
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Photo is larger than 40 MB.")
    image = decode_photo(data)
    height, width = image.shape[:2]
    faces = detect_faces_multiscale(
        image, Config.FACE_DETECT_SCALE, Config.FACE_DETECT_MIN_NEIGHBORS, DETECT_THRESHOLD
    )[:MAX_FACES]
    photo_id = store.add(image)
    logger.info(f"Stored photo {photo_id} with {len(faces)} face(s).")
    return {
        "id": photo_id,
        "width": width,
        "height": height,
        "faces": [{"x": x, "y": y, "w": w, "h": h} for x, y, w, h in faces],
    }


@app.post("/api/render")
def render(request: RenderRequest):
    """
    Renders every face and returns only the changed patches.

    The browser already has the photo, so sending back a few face-sized
    PNGs instead of a full 12 MP image keeps each slider move cheap.
    """
    image = store.get(request.photo)
    if image is None:
        raise HTTPException(404, "Photo expired; upload it again.")
    height, width = image.shape[:2]
    started = time.perf_counter()
    settings = request.settings
    base = request.base.to_tile_style()
    cells_by_face = {}
    for cell in request.layout.cells:
        cells_by_face.setdefault(cell.face, {})[(cell.row, cell.col)] = cell.style.to_tile_style()

    patches = []
    with _render_slots:
        canvas = image.copy()
        for index, face in enumerate(request.faces):
            box = clamp_box((face.x, face.y, face.w, face.h), width, height)
            stylized_face_glass(
                canvas,
                box,
                grid_size=settings.grid,
                style=base,
                feather_edges=settings.seamless,
                rng=np.random.default_rng([settings.seed, index]),
                cells=cells_by_face.get(index, {}),
                likeness=settings.likeness,
                intensity=settings.intensity,
                distortion=(settings.distortionMin, settings.distortionMax),
                noise=settings.noise,
            )
        for face in request.faces:
            x, y, w, h = clamp_box((face.x, face.y, face.w, face.h), width, height)
            m = patch_margin(face, settings.grid)
            x0, y0 = max(x - m, 0), max(y - m, 0)
            x1, y1 = min(x + w + m, width), min(y + h + m, height)
            patches.append(
                {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "data": encode_png(canvas[y0:y1, x0:x1])}
            )
    return {"patches": patches, "ms": round((time.perf_counter() - started) * 1000.0, 1)}


@app.get("/")
def home():
    return RedirectResponse("/studio/")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


def main():
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
