from dataclasses import dataclass, field

import numpy as np

from config import Config

from .materials import MATERIAL_NAMES, MATERIALS, render_tile
from .tints import Tint

_MIX_WEIGHTS = np.array([MATERIALS[name].weight for name in MATERIAL_NAMES])
_MIX_WEIGHTS /= _MIX_WEIGHTS.sum()


@dataclass(frozen=True)
class TileStyle:
    """What one tile is made of. Painted cells and whole faces use the same type."""

    material: str | None = None
    """A name from MATERIAL_NAMES, or None for the random mix."""
    tint: Tint = field(default_factory=Tint)
    angle: float | None = None
    """Grain direction of prism and ice in degrees; None is random per tile."""


def as_tile_style(style):
    """Accepts a TileStyle, a material name, or None, as older callers pass."""
    if isinstance(style, TileStyle):
        return style
    return TileStyle(material=style)


def relief(rng, distortion):
    """
    Surface relief multiplier for one tile.

    The distortion sliders were tuned around 8 px of displacement, so a
    strength of 8 gives each material its nominal shape. The range is
    ordered here because UIs can send min above max.
    """
    low, high = sorted(distortion)
    return rng.uniform(low, high) / 8.0


def apply_glass_tile(source, rect, style, rng, intensity=1.0, distortion=None, noise=None):
    """
    Renders the tile at rect = (x, y, w, h) of the linear-light source.

    distortion (min, max) and noise default to Config; callers serving
    several users pass their own so one request never changes another's.
    """
    if distortion is None:
        distortion = (Config.DISTORTION_STRENGTH_MIN, Config.DISTORTION_STRENGTH_MAX)
    if noise is None:
        noise = Config.NOISE_FACTOR
    return render_tile(
        source,
        rect,
        MATERIALS[choose_mode(rng, style.material)],
        rng,
        relief=relief(rng, distortion),
        bumpiness=0.15 * noise,
        tint=style.tint,
        angle=style.angle,
        intensity=intensity,
    )


def choose_mode(rng, style=None):
    if style in MATERIALS:
        return style
    return MATERIAL_NAMES[rng.choice(len(MATERIAL_NAMES), p=_MIX_WEIGHTS)]
