/**
 * @fileoverview Glass catalogue for the WebGL renderer.
 *
 * Mirrors utils/materials.py MATERIALS and utils/tints.py exactly; change
 * both together. A test checks the names against frontend/shared/model.js,
 * and the studio API exposes the Python values for cross-checking.
 */

/** Surface ids understood by the glass shader (see shaders.js surface()). */
export const SURFACE = Object.freeze({
  etched: 0, cathedral: 1, pillow: 2, ridges: 3, waves: 4,
  lens: 5, facets: 6, streaks: 7, capsule: 8,
});

const crown = {ior: 1.52, abbe: 59.0, roughness: 0.0, gloss: 0.12, haze: 0.0,
  absorption: [0, 0, 0], gap: 0.6, bumps: 1.0, directional: false, weight: 0.05};

/**
 * meanThickness is mean(surface.thickness) / (size * relief), measured from
 * the Python surfaces; dyes need the tile's mean glass path.
 */
export const MATERIAL_TABLE = Object.freeze({
  frosted: {...crown, surface: SURFACE.etched, abbe: null, roughness: 0.2, gloss: 0.6, gap: 1.0, bumps: 0.0, weight: 0.30, meanThickness: 0.0},
  clear: {...crown, surface: SURFACE.cathedral, roughness: 0.06, gloss: 0.05, gap: 1.0, weight: 0.10, meanThickness: 0.304},
  glossy: {...crown, surface: SURFACE.pillow, roughness: 0.12, gloss: 0.04, gap: 0.7, weight: 0.10, meanThickness: 0.074},
  prism: {...crown, surface: SURFACE.ridges, ior: 1.75, abbe: 25.0, gloss: 0.05, gap: 1.2, directional: true, weight: 0.10, meanThickness: 0.188},
  ripple: {...crown, surface: SURFACE.waves, ior: 1.333, abbe: 55.0, roughness: 0.05, gloss: 0.06, gap: 1.2, weight: 0.10, meanThickness: 0.038},
  magnify: {...crown, surface: SURFACE.lens, gloss: 0.05, gap: 1.0, meanThickness: 0.090},
  crystal: {...crown, surface: SURFACE.facets, ior: 1.62, abbe: 36.0, gloss: 0.03, gap: 1.0, meanThickness: 0.201},
  ice: {...crown, surface: SURFACE.streaks, ior: 1.309, abbe: 57.0, roughness: 0.1, gloss: 0.2, absorption: [0.0, 0.15, 0.45], gap: 1.0, directional: true, meanThickness: 0.044},
  hazy: {...crown, surface: SURFACE.cathedral, roughness: 0.05, gloss: 0.25, haze: 0.65, gap: 0.6, meanThickness: 0.279},
  chromatic: {...crown, surface: SURFACE.lens, ior: 1.8, abbe: 15.0, gloss: 0.05, gap: 1.6, meanThickness: 0.090},
  liquid: {...crown, surface: SURFACE.capsule, roughness: 0.22, gloss: 0.06, gap: 0.5, bumps: 0.0, weight: 0.10, meanThickness: 0.158},
});

export const MATERIAL_NAMES = Object.keys(MATERIAL_TABLE);

/** utils/tints.py PALETTE (RGB) and the share of tiles it tints. */
export const PALETTE = Object.freeze([[62, 72, 140], [104, 92, 156], [146, 110, 150], [88, 104, 150]]);
export const PALETTE_TINTED_SHARE = 0.55;

/** Constants from utils/materials.py and utils/face.py. */
export const HAZE_SPREAD = 0.5;
export const BACKPLATE_SPREAD = 0.2;
export const BASE_SLAB = 0.15;
export const OVERLAP = 0.35;
export const LIKENESS_SIGMA = 0.3;

// Fraunhofer lines (micrometres) and the R, G, B channel wavelengths.
const LAMBDA_D = 0.5876;
const LAMBDA_F = 0.4861;
const LAMBDA_C = 0.6563;
export const CHANNEL_WAVELENGTHS_RGB = Object.freeze([0.610, 0.550, 0.465]);

/**
 * Per-channel (R, G, B) refractive index from n_d and the Abbe number via
 * Cauchy's law, as utils/optics.py channel_iors (which returns B, G, R).
 */
export function channelIors(nd, abbe) {
  if (abbe === null) return [nd, nd, nd];
  const b = (nd - 1) / (abbe * (LAMBDA_F ** -2 - LAMBDA_C ** -2));
  const a = nd - b / LAMBDA_D ** 2;
  return CHANNEL_WAVELENGTHS_RGB.map((lambda) => a + b / lambda ** 2);
}
