"""
Coloured glass, modelled by how the colour gets into the light.

Dyed glass absorbs (Beer-Lambert), so thick parts of a tile such as a lens
centre or a liquid-glass rim come out deeper than thin parts. Dichroic
coatings interfere (thin-film optics), so the colour swirls with coating
thickness and viewing angle, like a soap bubble. Pigment grains scatter
colour at random per pixel.
"""

import colorsys
import re
from dataclasses import dataclass

import numpy as np

from . import optics
from .surfaces import smooth_noise

TINT_MODES = ["none", "color", "palette", "auto", "rainbow", "noise"]
"""none: clear glass. color: dyed one colour. palette: muted cool washes on
about half the tiles. auto: a random vivid hue per tile. rainbow: dichroic
thin-film coating. noise: white-noise pigment grains."""

# Muted cool washes (RGB). Against warm skin they read as soft shade rather
# than colour, and untinted tiles between them keep the face's warmth.
PALETTE = ((62, 72, 140), (104, 92, 156), (146, 110, 150), (88, 104, 150))
PALETTE_TINTED_SHARE = 0.55


@dataclass(frozen=True)
class Tint:
    mode: str = "none"
    color: tuple = (90, 170, 255)
    """RGB colour of the dye for mode "color"."""
    strength: float = 0.5
    """0 leaves the glass clear, 1 gives fully saturated colour."""


# Fraction of room light that dyed glass scatters back in its own colour.
# Without it a blue tile over warm skin turns grey, since a dye can only
# subtract light the photo does not have.
_BODY_SCATTER = 0.2

# Index of a typical dichroic coating layer (TiO2/SiO2 stacks average here).
_FILM_IOR = 1.9

# Peak reflectance of the coating; real dichroic glass reaches about 0.6.
_FILM_PEAK = 0.6

# Dominant wavelengths of the B, G, R channels in nanometres.
_CHANNEL_NM = np.array(optics.CHANNEL_WAVELENGTHS, dtype=np.float32) * 1000.0


def parse_color(value):
    """RGB tuple from "#rrggbb" or "rgb(a)(r, g, b, ...)", as UI pickers send."""
    if isinstance(value, (tuple, list)):
        return tuple(int(c) for c in value[:3])
    text = str(value).strip()
    if text.startswith("#") and len(text) in (4, 5):
        return tuple(int(c * 2, 16) for c in text[1:4])
    if text.startswith("#") and len(text) >= 7:
        return tuple(int(text[i : i + 2], 16) for i in (1, 3, 5))
    numbers = re.findall(r"[\d.]+", text)
    if len(numbers) >= 3:
        return tuple(int(float(n)) for n in numbers[:3])
    raise ValueError(f"unrecognised colour: {value!r}")


def random_hue(rng):
    """A vivid RGB colour, so auto tints read like stained-glass offcuts."""
    hue = rng.uniform(0.0, 1.0)
    saturation = rng.uniform(0.55, 0.9)
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, saturation, 1.0))


def dye_layers(rgb, strength, path):
    """
    Transmission and body scatter of glass dyed to `rgb`, per BGR channel.

    The absorption coefficient is chosen so a pixel with the tile's mean
    glass path transmits exactly the requested colour; thicker pixels then
    darken and saturate the way real coloured glass does.
    """
    linear = (np.array(rgb[::-1], dtype=np.float32) / 255.0) ** 2.2
    hue = linear / max(float(linear.max()), 1e-3)
    target = 1.0 - strength * (1.0 - hue)
    absorption = -np.log(np.clip(target, 1e-3, 1.0)) / max(float(path.mean()), 1e-3)
    return optics.transmittance(path, absorption), _BODY_SCATTER * strength * hue


def film_reflectance(nz, rng, strength):
    """
    Per-pixel BGR reflectance of a dichroic thin film.

    Light reflected from the top and bottom of the film interferes with a
    phase of 4 pi n d cos(theta_t) / lambda, so each wavelength peaks at a
    different film thickness. A coating that varies smoothly from 250 to
    900 nm across the tile gives rainbow swirls.
    """
    h, w = nz.shape
    sigma = max(min(h, w) / 4.0, 1.0)
    film_nm = 575.0 + 325.0 * np.tanh(smooth_noise(h, w, rng, sigma))
    sin_t = np.sqrt(np.clip(1.0 - nz * nz, 0.0, 1.0)) / _FILM_IOR
    cos_t = np.sqrt(1.0 - sin_t * sin_t)
    phase = (4.0 * np.pi * _FILM_IOR) * (film_nm * cos_t)[..., None] / _CHANNEL_NM
    return strength * _FILM_PEAK * np.sin(phase / 2.0) ** 2


def pigment_transmittance(shape, rng, strength):
    """Independent random absorption per pixel and channel: white noise."""
    grains = rng.uniform(0.0, 1.0, (*shape, 3)).astype(np.float32)
    return 1.0 - strength * grains


def tint_layers(tint, path, nz, rng):
    """
    How the tint changes the light leaving one tile.

    Returns (transmission, reflection) as BGR arrays: the transmitted light
    is multiplied by the first, and the second is extra reflectance of the
    room on top of Fresnel. Energy is conserved: whatever a coating reflects
    it no longer transmits.
    """
    shape = nz.shape
    if tint.mode == "none" or tint.strength <= 0:
        return 1.0, 0.0
    if tint.mode == "color":
        return dye_layers(tint.color, tint.strength, path)
    if tint.mode == "palette":
        if rng.uniform() > PALETTE_TINTED_SHARE:
            return 1.0, 0.0
        color = PALETTE[rng.integers(len(PALETTE))]
        return dye_layers(color, tint.strength, path)
    if tint.mode == "auto":
        return dye_layers(random_hue(rng), tint.strength, path)
    if tint.mode == "rainbow":
        reflectance = film_reflectance(nz, rng, tint.strength)
        return 1.0 - reflectance, reflectance
    if tint.mode == "noise":
        return pigment_transmittance(shape, rng, tint.strength), 0.0
    raise ValueError(f"unknown tint mode: {tint.mode}")

