/**
 * @fileoverview The UI model both front ends share: state tables, material
 * catalogue, settings validation, presets, the painted-cell layout and the
 * face board geometry. Everything here is pure, so it is unit tested
 * without a browser.
 */

/** Photo lifecycle; see docs/frontend-design.md. */
export const PHOTO_TABLE = {
  empty: {choose: 'loading'},
  loading: {found: 'ready', none: 'noFaces', fail: 'failed', choose: 'loading'},
  ready: {choose: 'loading', expire: 'loading', addFace: 'ready', reset: 'empty'},
  noFaces: {choose: 'loading', addFace: 'ready', reset: 'empty'},
  failed: {choose: 'loading', reset: 'empty'},
};

/** Latest-wins rendering: one in flight, at most one queued. */
export const RENDER_TABLE = {
  idle: {request: 'busy'},
  busy: {request: 'queued', done: 'idle', fail: 'failed'},
  queued: {request: 'queued', done: 'busy', fail: 'busy'},
  failed: {request: 'busy'},
};

/** Must match utils/materials.py MATERIAL_NAMES (checked by a test). */
export const MATERIALS = [
  'frosted', 'clear', 'glossy', 'prism', 'ripple', 'magnify',
  'crystal', 'ice', 'hazy', 'chromatic', 'liquid',
];

/** Board marker colour per material (CSS rgb), as web/painter.py draws them. */
export const MATERIAL_COLORS = Object.freeze({
  random: 'rgb(255 255 255)',
  frosted: 'rgb(236 240 245)',
  clear: 'rgb(125 211 252)',
  glossy: 'rgb(250 204 21)',
  prism: 'rgb(244 114 182)',
  ripple: 'rgb(56 189 248)',
  magnify: 'rgb(163 230 53)',
  crystal: 'rgb(192 132 252)',
  ice: 'rgb(103 232 249)',
  hazy: 'rgb(148 163 184)',
  chromatic: 'rgb(251 146 60)',
  liquid: 'rgb(52 211 153)',
});

/** Short board label: "RND" for the random mix, else two capitals. */
export const materialLabel = (name) => (name === 'random' ? 'RND' : name.slice(0, 2).toUpperCase());

/** Materials whose grain direction the angle control steers. */
export const DIRECTIONAL = new Set(['prism', 'ice']);

/** Must match utils/tints.py TINT_MODES. */
export const TINT_MODES = ['none', 'color', 'palette', 'auto', 'rainbow', 'noise'];

export const DEFAULT_SETTINGS = Object.freeze({
  grid: 4,
  seed: 7,
  seamless: true,
  likeness: 0.9,
  intensity: 1.0,
  distortionMin: 5,
  distortionMax: 12,
  noise: 2,
});

export const DEFAULT_BRUSH = Object.freeze({
  material: 'liquid',
  tint: Object.freeze({mode: 'none', color: '#5aaaff', strength: 0.5}),
  angle: null,
});

export const PRESETS = Object.freeze({
  /**
   * Smooth frosted panes with crisp edges and mild cool washes. Crisp edges
   * keep each pane's tint distinct, and half intensity leaves feature
   * shapes readable but not identifiable.
   */
  frostedPanes: Object.freeze({
    label: 'Frosted panes',
    settings: {grid: 3, seamless: false, intensity: 0.5},
    brush: {material: 'frosted', tint: {mode: 'palette', color: '#5aaaff', strength: 0.55}, angle: null},
  }),
  liquidGlass: Object.freeze({
    label: 'Liquid glass',
    settings: {grid: 2, seamless: false, intensity: 1.0},
    brush: {material: 'liquid', tint: {mode: 'none', color: '#5aaaff', strength: 0.5}, angle: null},
  }),
});

export const MAX_SEED = 2 ** 32 - 1;

const clamp = (value, low, high) => Math.min(Math.max(value, low), high);

function finiteOr(value, fallback) {
  const number = typeof value === 'string' && value.trim() === '' ? NaN : Number(value);
  return Number.isFinite(number) ? number : fallback;
}

/**
 * Settings as the renderer may trust them. Empty, negative or out-of-range
 * inputs fall back or clamp instead of reaching the renderer, and min/max
 * distortion are ordered.
 * @param {!Object} raw
 * @return {!Object}
 */
export function normalizeSettings(raw) {
  const d = DEFAULT_SETTINGS;
  const low = clamp(finiteOr(raw.distortionMin, d.distortionMin), 0, 30);
  const high = clamp(finiteOr(raw.distortionMax, d.distortionMax), 0, 30);
  return {
    grid: clamp(Math.round(finiteOr(raw.grid, d.grid)), 1, 12),
    seed: clamp(Math.round(Math.abs(finiteOr(raw.seed, d.seed))), 0, MAX_SEED),
    seamless: raw.seamless === undefined ? d.seamless : Boolean(raw.seamless),
    likeness: clamp(finiteOr(raw.likeness, d.likeness), 0, 1),
    intensity: clamp(finiteOr(raw.intensity, d.intensity), 0.1, 1.5),
    distortionMin: Math.min(low, high),
    distortionMax: Math.max(low, high),
    noise: clamp(finiteOr(raw.noise, d.noise), 0, 10),
  };
}

/** Brush as the renderer may trust it. */
export function normalizeBrush(raw) {
  const material = MATERIALS.includes(raw.material) || raw.material === 'random' ? raw.material : DEFAULT_BRUSH.material;
  const tint = raw.tint ?? {};
  const color = /^#[0-9a-f]{6}$/i.test(tint.color) ? tint.color.toLowerCase() : DEFAULT_BRUSH.tint.color;
  const angle = raw.angle === null || raw.angle === undefined || raw.angle === '' ? null : clamp(finiteOr(raw.angle, 0), 0, 180);
  return {
    material,
    tint: {
      mode: TINT_MODES.includes(tint.mode) ? tint.mode : 'none',
      color,
      strength: clamp(finiteOr(tint.strength, DEFAULT_BRUSH.tint.strength), 0, 1),
    },
    angle,
  };
}

/** Two brushes paint the same thing. */
export function sameBrush(a, b) {
  return JSON.stringify(normalizeBrush(a)) === JSON.stringify(normalizeBrush(b));
}

/**
 * Painted cells. Cells always carry the grid they were painted on, so a
 * grid change can never reinterpret old coordinates.
 * @typedef {{grid: number, cells: !Object<string, !Object>}}
 */
export function emptyLayout(grid) {
  return {grid, cells: {}};
}

export const cellKey = (face, row, col) => `${face}:${row}:${col}`;

export function parseCellKey(key) {
  const [face, row, col] = key.split(':').map(Number);
  return {face, row, col};
}

/**
 * The layout carried onto `grid`. Each new cell takes the style of the old
 * cell under its centre, so a fully painted face (a preset, paint all)
 * stays fully painted and a partial pattern keeps its shape. Every cell is
 * recomputed for the new grid, so old coordinates are never reinterpreted.
 */
export function layoutForGrid(layout, grid) {
  if (layout.grid === grid) return layout;
  const old = layout.grid;
  const source = (index) => Math.min(old - 1, Math.floor(((index + 0.5) * old) / grid));
  const faces = new Set(Object.keys(layout.cells).map((key) => parseCellKey(key).face));
  const cells = {};
  for (const face of faces) {
    for (let row = 0; row < grid; row++) {
      for (let col = 0; col < grid; col++) {
        const style = layout.cells[cellKey(face, source(row), source(col))];
        if (style) cells[cellKey(face, row, col)] = style;
      }
    }
  }
  return {grid, cells};
}

/** Paints a cell, or clears it when it already holds the same brush. */
export function toggleCell(layout, hit, brush) {
  const key = cellKey(hit.face, hit.row, hit.col);
  const cells = {...layout.cells};
  if (cells[key] && sameBrush(cells[key], brush)) {
    delete cells[key];
  } else {
    cells[key] = normalizeBrush(brush);
  }
  return {grid: layout.grid, cells};
}

export function paintAll(grid, faceCount, brush) {
  const style = normalizeBrush(brush);
  const cells = {};
  for (let face = 0; face < faceCount; face++) {
    for (let row = 0; row < grid; row++) {
      for (let col = 0; col < grid; col++) cells[cellKey(face, row, col)] = style;
    }
  }
  return {grid, cells};
}

/** Applies a preset; returns the new settings, brush and layout. */
export function applyPreset(name, settings, faceCount) {
  const preset = PRESETS[name];
  const next = normalizeSettings({...settings, ...preset.settings});
  const brush = normalizeBrush(preset.brush);
  return {settings: next, brush, layout: paintAll(next.grid, faceCount, brush)};
}

/**
 * numpy.round: halves go to the even neighbour. Cell edges must round the
 * way utils/face.py does, or a click on a boundary pixel would paint the
 * neighbouring cell.
 */
export function roundHalfEven(x) {
  const floor = Math.floor(x);
  const diff = x - floor;
  if (diff > 0.5) return floor + 1;
  if (diff < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

/** Cell boundaries along one side, matching utils/face.py tile_rects. */
export function gridEdges(length, grid) {
  return Array.from({length: grid + 1}, (_, i) => roundHalfEven((i * length) / grid));
}

export const BOARD = Object.freeze({slot: 320, gap: 12, columns: 3});

export function slotOrigin(index) {
  const step = BOARD.slot + BOARD.gap;
  return {x: (index % BOARD.columns) * step, y: Math.floor(index / BOARD.columns) * step};
}

export function boardSize(faceCount) {
  const step = BOARD.slot + BOARD.gap;
  const cols = Math.min(Math.max(faceCount, 1), BOARD.columns);
  const rows = Math.max(Math.ceil(faceCount / BOARD.columns), 1);
  return {width: cols * step - BOARD.gap, height: rows * step - BOARD.gap};
}

function cellIndex(edges, position) {
  let index = 0;
  while (index < edges.length - 2 && position >= edges[index + 1]) index++;
  return index;
}

/**
 * The (face, row, col) under board pixel (x, y), or null for a gap.
 * @param {!Array<{w: number, h: number}>} faces
 */
export function cellAt(faces, grid, x, y) {
  const step = BOARD.slot + BOARD.gap;
  const slotCol = Math.floor(x / step);
  const slotRow = Math.floor(y / step);
  const lx = x - slotCol * step;
  const ly = y - slotRow * step;
  const face = slotRow * BOARD.columns + slotCol;
  if (x < 0 || y < 0 || slotCol >= BOARD.columns || face >= faces.length) return null;
  if (lx >= BOARD.slot || ly >= BOARD.slot) return null;
  const {w, h} = faces[face];
  return {
    face,
    row: cellIndex(gridEdges(h, grid), (ly * h) / BOARD.slot),
    col: cellIndex(gridEdges(w, grid), (lx * w) / BOARD.slot),
  };
}

/** Request body for the studio API and input for the WebGL renderer. */
export function renderRequest(settings, layout, defaultBrush) {
  const cells = Object.entries(layout.cells).map(([key, style]) => ({...parseCellKey(key), style}));
  return {settings: normalizeSettings(settings), layout: {grid: layout.grid, cells}, base: normalizeBrush(defaultBrush)};
}
