"""
Physical glass materials and the renderer that shades one tile.

A material is a surface shape plus optical constants. Every visual trait,
including blur, colour fringes, rim glow and highlights, comes out of the
optics in utils.optics rather than from per-style image filters.
"""

from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

from . import optics, surfaces
from .tints import Tint, tint_layers


@dataclass(frozen=True)
class Material:
    surface: Callable
    """Height-field builder from utils.surfaces."""
    ior: float = 1.52
    """Refractive index at 587.6 nm (crown glass is 1.52)."""
    abbe: float | None = 59.0
    """Abbe number; lower disperses colours more, None disables dispersion."""
    roughness: float = 0.0
    """RMS angle, in radians, that the surface scatters transmitted light."""
    gloss: float = 0.12
    """GGX alpha of the top face; lower gives sharper highlights."""
    haze: float = 0.0
    """Fraction of light scattered inside the bulk, as in opal glass."""
    absorption: tuple = (0.0, 0.0, 0.0)
    """Beer-Lambert coefficients per tile size of glass path, B, G, R."""
    gap: float = 0.6
    """Distance from the glass base to the photo, in tile sizes."""
    bumps: float = 1.0
    """Scale of manufacturing ripple; 0 for flawless glass."""
    directional: bool = False
    """Whether the surface builder takes an `angle` for its grain."""
    weight: float = 0.05
    """Relative chance of this material in the random mix."""


MATERIALS = {
    "frosted": Material(
        surfaces.etched,
        abbe=None,
        roughness=0.2,
        gloss=0.6,
        gap=1.0,
        bumps=0.0,
        weight=0.30,
    ),
    "clear": Material(
        surfaces.cathedral, roughness=0.06, gloss=0.05, gap=1.0, weight=0.10
    ),
    "glossy": Material(
        surfaces.pillow, roughness=0.12, gloss=0.04, gap=0.7, weight=0.10
    ),
    "prism": Material(
        surfaces.ridges,
        ior=1.75,
        abbe=25.0,
        gloss=0.05,
        gap=1.2,
        directional=True,
        weight=0.10,
    ),
    "ripple": Material(
        surfaces.waves,
        ior=1.333,
        abbe=55.0,
        roughness=0.05,
        gloss=0.06,
        gap=1.2,
        weight=0.10,
    ),
    "magnify": Material(surfaces.lens, gloss=0.05, gap=1.0),
    "crystal": Material(
        surfaces.facets, ior=1.62, abbe=36.0, gloss=0.03, gap=1.0
    ),
    "ice": Material(
        surfaces.streaks,
        ior=1.309,
        abbe=57.0,
        roughness=0.1,
        gloss=0.2,
        absorption=(0.0, 0.15, 0.45),
        gap=1.0,
        directional=True,
    ),
    "hazy": Material(
        surfaces.cathedral, roughness=0.05, gloss=0.25, haze=0.65, gap=0.6
    ),
    "chromatic": Material(
        surfaces.lens, ior=1.8, abbe=15.0, gloss=0.05, gap=1.6
    ),
    "liquid": Material(
        surfaces.capsule,
        roughness=0.22,
        gloss=0.06,
        gap=0.5,
        bumps=0.0,
        weight=0.10,
    ),
}

MATERIAL_NAMES = list(MATERIALS)

# Opal glass scatters light over a lobe this wide, in tile sizes.
_HAZE_SPREAD = 0.5

# Scatter of the frosted pane behind rounded tiles, in tile sizes.
_BACKPLATE_SPREAD = 0.2

# Every tile sits on a flat slab this thick, in tile sizes, so even the
# thinnest point of a surface still has glass to absorb light.
_BASE_SLAB = 0.15


def scattered(source, window, sigma):
    """
    The photo as seen through a rough surface, over a window of the source.

    Blurring only the window the tile can sample keeps the cost
    proportional to the tile, not the face. Returns the blurred crop and
    its top-left corner in source coordinates.
    """
    x0, y0, x1, y1 = window
    crop = source[y0:y1, x0:x1]
    if sigma < 0.3:
        return crop, (x0, y0)
    blurred = cv2.GaussianBlur(crop, (0, 0), sigma, borderType=cv2.BORDER_REFLECT)
    return blurred, (x0, y0)


def sample_window(source_shape, rect, margin):
    """Tile rectangle grown by margin and clipped to the source."""
    sh, sw = source_shape[:2]
    x, y, w, h = rect
    m = int(np.ceil(margin))
    return max(x - m, 0), max(y - m, 0), min(x + w + m, sw), min(y + h + m, sh)


def refract(source, rect, normals, depth, material, sigma):
    """Light transmitted through the glass, one refraction per colour."""
    x, y, w, h = rect
    max_shift = float(depth.max())
    window = sample_window(source.shape, rect, max_shift + 3.0 * sigma + 2.0)
    crop, (ox, oy) = scattered(source, window, sigma)
    channels = cv2.split(crop)

    xx = (np.arange(x, x + w, dtype=np.float32) - ox)[None, :]
    yy = (np.arange(y, y + h, dtype=np.float32) - oy)[:, None]
    out = np.empty((h, w, 3), dtype=np.float32)
    iors = optics.channel_iors(material.ior, material.abbe)
    for c, ior in enumerate(iors):
        dx, dy = optics.refraction_offsets(*normals, depth, ior)
        out[..., c] = cv2.remap(
            channels[c],
            (xx + dx).astype(np.float32),
            (yy + dy).astype(np.float32),
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )
    return out


def render_tile(
    source, rect, material, rng, relief, bumpiness, tint=Tint(), angle=None, intensity=1.0
):
    """
    Shades one glass tile lying over `source`, a linear-light float image.

    The result is transmitted light, attenuated by Fresnel loss, absorption
    and the tint, plus the reflected room and the key light's highlight.
    angle steers the grain of directional materials, in degrees; None is
    random. intensity scales scattering and surface relief together: 1 is
    the material as specified, lower lets more of the face through.
    """
    x, y, w, h = rect
    size = min(w, h)
    relief *= intensity
    if material.directional:
        surface = material.surface(h, w, rng, relief, angle=angle)
    else:
        surface = material.surface(h, w, rng, relief)
    if bumpiness * material.bumps > 0:
        surface = surfaces.with_bumps(surface, rng, bumpiness * material.bumps)

    normals = optics.surface_normals(surface.gx, surface.gy)
    nz = normals[2]
    depth = surface.thickness + material.gap * size
    sigma = float(depth.mean()) * np.tan(material.roughness * intensity)
    transmitted = refract(source, rect, normals, depth, material, sigma)

    if material.haze > 0:
        diffuse = refract(
            source, rect, normals, depth, material, _HAZE_SPREAD * intensity * size
        )
        transmitted = (1.0 - material.haze) * transmitted + material.haze * diffuse

    path = surface.thickness + _BASE_SLAB * size
    absorption = np.asarray(material.absorption, dtype=np.float32) / size
    coat_transmission, coat_reflection = tint_layers(tint, path, nz, rng)

    alpha = optics.filtered_roughness(material.gloss, surface.gx, surface.gy)
    reflectance = optics.fresnel(nz, material.ior)[..., None]
    light = (
        (1.0 - reflectance)
        * optics.transmittance(path, absorption)
        * coat_transmission
        * transmitted
        + (reflectance + coat_reflection) * optics.environment(*normals)
        + optics.specular(*normals, alpha, material.ior)[..., None]
    )

    if surface.coverage is None:
        return light

    # Outside a rounded tile the photo is seen through a frosted backplate,
    # so the corners between tiles never reveal the unaltered face.
    flat = optics.surface_normals(np.zeros_like(nz), np.zeros_like(nz))
    backplate = refract(source, rect, flat, depth, material, _BACKPLATE_SPREAD * size)
    coverage = surface.coverage[..., None]
    return coverage * light + (1.0 - coverage) * coat_transmission * backplate
