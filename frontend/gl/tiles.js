/**
 * @fileoverview Per-tile decisions and their packing for the shader.
 *
 * Everything random about a tile (material for the random mix, relief,
 * grain angle, auto hue, palette pick, noise seed) comes from a hash of
 * (seed, face, row, col), so the same seed always gives the same glass and
 * painting one cell never reshuffles the others.
 */

import {gridEdges} from '../shared/model.js';
import {
  BASE_SLAB, MATERIAL_NAMES, MATERIAL_TABLE, OVERLAP, PALETTE, PALETTE_TINTED_SHARE, channelIors,
} from './materials.js';

/** 32-bit integer mix (lowbias32 by Chris Wellons). */
function mix32(x) {
  x ^= x >>> 16;
  x = Math.imul(x, 0x7feb352d);
  x ^= x >>> 15;
  x = Math.imul(x, 0x846ca68b);
  x ^= x >>> 16;
  return x >>> 0;
}

/** Deterministic uniform in [0, 1) for a list of integers. */
export function hash01(...values) {
  let h = 0x9e3779b9;
  for (const v of values) h = mix32(h ^ mix32((v | 0) >>> 0));
  return h / 4294967296;
}

/** Tile-local random stream: draw(k) is the k-th uniform for this tile. */
export function tileRandom(seed, face, row, col) {
  const s = seed >>> 0;
  return (k) => hash01(s, face, row, col, k);
}

/** Expands the random-mix weights into cumulative thresholds. */
const MIX = (() => {
  const total = MATERIAL_NAMES.reduce((sum, name) => sum + MATERIAL_TABLE[name].weight, 0);
  let acc = 0;
  return MATERIAL_NAMES.map((name) => ({name, until: (acc += MATERIAL_TABLE[name].weight / total)}));
})();

export function mixMaterial(u) {
  return (MIX.find((entry) => u < entry.until) ?? MIX[MIX.length - 1]).name;
}

function srgbToLinear(c) {
  return (c / 255) ** 2.2;
}

function hsvToRgb(h, s, v) {
  const i = Math.floor(h * 6);
  const f = h * 6 - i;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);
  return [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][i % 6].map((c) => Math.trunc(c * 255));
}

function hexToRgb(hex) {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
}

/** Tint kinds understood by the shader. */
export const TINT = Object.freeze({none: 0, dye: 1, rainbow: 2, noise: 3});

/**
 * What one tile is made of, with every random choice resolved.
 * @param {!Object} style A normalized brush (model.js normalizeBrush).
 * @param {!Object} settings Normalized settings.
 * @param {function(number): number} draw Tile random stream.
 */
export function resolveTile(style, settings, draw) {
  const name = style.material === 'random' ? mixMaterial(draw(0)) : style.material;
  const material = MATERIAL_TABLE[name];
  const strength = settings.distortionMin + (settings.distortionMax - settings.distortionMin) * draw(1);
  const relief = (strength / 8) * settings.intensity;
  const angle = style.angle ?? draw(2) * 180;

  let tint = {kind: TINT.none, strength: 0, rgb: [1, 1, 1]};
  const {mode, strength: tintStrength} = style.tint;
  if (tintStrength > 0) {
    let color = null;
    if (mode === 'color') color = hexToRgb(style.tint.color);
    if (mode === 'auto') color = hsvToRgb(draw(3), 0.55 + 0.35 * draw(4), 1);
    if (mode === 'palette' && draw(5) <= PALETTE_TINTED_SHARE) color = PALETTE[Math.floor(draw(6) * PALETTE.length)];
    if (color) {
      const linear = color.map(srgbToLinear);
      const peak = Math.max(...linear, 1e-3);
      tint = {kind: TINT.dye, strength: tintStrength, rgb: linear.map((c) => c / peak)};
    }
    if (mode === 'rainbow') tint = {kind: TINT.rainbow, strength: tintStrength, rgb: [1, 1, 1]};
    if (mode === 'noise') tint = {kind: TINT.noise, strength: tintStrength, rgb: [1, 1, 1]};
  }
  return {name, material, relief, angle, tint, noiseSeed: draw(7) * 1000};
}

/** Texels (RGBA floats) per tile in the tile data texture. */
export const TEXELS_PER_TILE = 6;

/**
 * Packs resolved tiles into a Float32Array for an RGBA32F texture of
 * TEXELS_PER_TILE x tiles.length. Layout (one row per tile):
 *   0: surface id, relief, angle (radians), noise seed
 *   1: ior R, ior G, ior B, ior d
 *   2: roughness * intensity, gloss, haze, gap
 *   3: absorption R, G, B (per tile size), bumps
 *   4: tint kind, tint strength, mean glass path / size, 0
 *   5: dye hue R, G, B (linear, max 1), 0
 */
export function packTiles(tiles, settings) {
  const data = new Float32Array(tiles.length * TEXELS_PER_TILE * 4);
  tiles.forEach((tile, index) => {
    const m = tile.material;
    const [ir, ig, ib] = channelIors(m.ior, m.abbe);
    const meanPath = m.meanThickness * tile.relief + BASE_SLAB;
    const values = [
      m.surface, tile.relief, (tile.angle * Math.PI) / 180, tile.noiseSeed,
      ir, ig, ib, m.ior,
      m.roughness * settings.intensity, m.gloss, m.haze, m.gap,
      ...m.absorption, m.bumps,
      tile.tint.kind, tile.tint.strength, meanPath, 0,
      ...tile.tint.rgb, 0,
    ];
    data.set(values, index * TEXELS_PER_TILE * 4);
  });
  return data;
}

/**
 * Geometry of one face's render: the region worked on (face box plus the
 * fade margin, clipped to the photo) and the tile edges in region pixels.
 * Mirrors utils/face.py stylized_face_glass.
 */
export function faceGeometry(box, settings, photoWidth, photoHeight) {
  const {x, y, w, h} = box;
  const tile = Math.min(w, h) / settings.grid;
  const margin = settings.seamless ? Math.round(OVERLAP * tile) : 0;
  const x0 = Math.max(x - margin, 0);
  const y0 = Math.max(y - margin, 0);
  const x1 = Math.min(x + w + margin, photoWidth);
  const y1 = Math.min(y + h + margin, photoHeight);
  return {
    region: {x: x0, y: y0, w: x1 - x0, h: y1 - y0},
    face: {x: x - x0, y: y - y0, w, h},
    tile,
    margin,
    xs: gridEdges(w, settings.grid).map((e) => e + x - x0),
    ys: gridEdges(h, settings.grid).map((e) => e + y - y0),
  };
}
