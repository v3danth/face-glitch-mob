import assert from 'node:assert/strict';
import {test} from 'node:test';

import {MATERIALS, normalizeBrush, normalizeSettings} from '../shared/model.js';
import {detectionWindows, drawnFaceBox, mergeDetections, squareFaceBox} from './faces.js';
import {MATERIAL_NAMES, MATERIAL_TABLE, channelIors} from './materials.js';
import {
  TEXELS_PER_TILE, TINT, faceGeometry, hash01, mixMaterial, packTiles, resolveTile, tileRandom,
} from './tiles.js';

const settings = normalizeSettings({});

test('material table matches the shared catalogue, in order', () => {
  assert.deepEqual(MATERIAL_NAMES, MATERIALS);
});

test('Cauchy IORs match utils/optics.py channel_iors (R, G, B)', () => {
  const cases = {clear: [1.519037, 1.521889, 1.527975], prism: [1.746721, 1.756431, 1.777145], chromatic: [1.794171, 1.811433, 1.848257]};
  for (const [name, want] of Object.entries(cases)) {
    const m = MATERIAL_TABLE[name];
    channelIors(m.ior, m.abbe).forEach((got, i) => assert.ok(Math.abs(got - want[i]) < 1e-5, `${name}[${i}] ${got}`));
  }
  assert.deepEqual(channelIors(1.52, null), [1.52, 1.52, 1.52]);
});

test('hash is deterministic, in [0, 1), and sensitive to every input', () => {
  const a = hash01(7, 0, 1, 2, 3);
  assert.equal(a, hash01(7, 0, 1, 2, 3));
  assert.ok(a >= 0 && a < 1);
  for (const other of [hash01(8, 0, 1, 2, 3), hash01(7, 1, 1, 2, 3), hash01(7, 0, 2, 2, 3), hash01(7, 0, 1, 3, 3), hash01(7, 0, 1, 2, 4)]) {
    assert.notEqual(a, other);
  }
});

test('hash is roughly uniform', () => {
  const bins = new Array(10).fill(0);
  for (let i = 0; i < 20000; i++) bins[Math.floor(hash01(i, 3) * 10)]++;
  for (const count of bins) assert.ok(Math.abs(count - 2000) < 200, `bin ${count}`);
});

test('same seed and cell give the same tile; painting one cell never reshuffles others', () => {
  const brush = normalizeBrush({material: 'random', tint: {mode: 'auto', strength: 0.5}});
  const one = resolveTile(brush, settings, tileRandom(7, 0, 1, 1));
  const again = resolveTile(brush, settings, tileRandom(7, 0, 1, 1));
  assert.deepEqual(one, again);
  const neighbour = resolveTile(brush, settings, tileRandom(7, 0, 1, 2));
  assert.notDeepEqual(neighbour, one);
});

test('random mix follows the material weights', () => {
  const counts = {};
  for (let i = 0; i < 20000; i++) {
    const name = mixMaterial(hash01(i, 99));
    counts[name] = (counts[name] ?? 0) + 1;
  }
  assert.ok(Math.abs(counts.frosted / 20000 - 0.30) < 0.02, `frosted ${counts.frosted}`);
  assert.ok(Math.abs(counts.crystal / 20000 - 0.05) < 0.01, `crystal ${counts.crystal}`);
  assert.equal(mixMaterial(0.999999), 'liquid');
});

test('relief spans the distortion range and scales with intensity', () => {
  const s = normalizeSettings({distortionMin: 8, distortionMax: 8, intensity: 0.5});
  const tile = resolveTile(normalizeBrush({material: 'clear'}), s, tileRandom(1, 0, 0, 0));
  assert.equal(tile.relief, 0.5);
});

test('tints resolve to what the shader understands', () => {
  const draw = tileRandom(3, 0, 0, 0);
  const dyed = resolveTile(normalizeBrush({material: 'clear', tint: {mode: 'color', color: '#ff0000', strength: 0.6}}), settings, draw);
  assert.equal(dyed.tint.kind, TINT.dye);
  assert.deepEqual(dyed.tint.rgb, [1, 0, 0]);
  const clear = resolveTile(normalizeBrush({material: 'clear', tint: {mode: 'color', color: '#ff0000', strength: 0}}), settings, draw);
  assert.equal(clear.tint.kind, TINT.none);
  let tinted = 0;
  for (let i = 0; i < 2000; i++) {
    const t = resolveTile(normalizeBrush({material: 'frosted', tint: {mode: 'palette', strength: 0.5}}), settings, tileRandom(i, 0, 0, 0));
    if (t.tint.kind === TINT.dye) tinted++;
  }
  assert.ok(Math.abs(tinted / 2000 - 0.55) < 0.04, `palette share ${tinted / 2000}`);
});

test('packTiles writes one row of texels per tile in the documented order', () => {
  const ice = resolveTile(normalizeBrush({material: 'ice', angle: 90}), settings, tileRandom(1, 0, 0, 0));
  const glossy = resolveTile(normalizeBrush({material: 'glossy'}), settings, tileRandom(1, 0, 0, 1));
  const data = packTiles([ice, glossy], settings);
  assert.equal(data.length, 2 * TEXELS_PER_TILE * 4);
  const row = (i) => data.slice(i * TEXELS_PER_TILE * 4, (i + 1) * TEXELS_PER_TILE * 4);
  const r0 = row(0);
  assert.equal(r0[0], MATERIAL_TABLE.ice.surface);
  assert.ok(Math.abs(r0[2] - Math.PI / 2) < 1e-6);
  assert.ok(Math.abs(r0[7] - 1.309) < 1e-6);
  assert.ok(Math.abs(r0[13] - 0.15) < 1e-6 && Math.abs(r0[14] - 0.45) < 1e-6);
  assert.equal(row(1)[0], MATERIAL_TABLE.glossy.surface);
});

test('face geometry matches utils/face.py: margin, clipping and tile edges', () => {
  const box = {x: 2796, y: 854, w: 206, h: 206};
  const seamless = faceGeometry(box, normalizeSettings({grid: 3, seamless: true}), 4032, 3024);
  assert.equal(seamless.margin, 24);
  assert.deepEqual(seamless.region, {x: 2772, y: 830, w: 254, h: 254});
  assert.deepEqual(seamless.xs, [24, 93, 161, 230]);
  const hard = faceGeometry(box, normalizeSettings({grid: 3, seamless: false}), 4032, 3024);
  assert.equal(hard.margin, 0);
  assert.deepEqual(hard.region, {x: 2796, y: 854, w: 206, h: 206});
  const corner = faceGeometry({x: 0, y: 0, w: 90, h: 90}, normalizeSettings({grid: 3, seamless: true}), 100, 100);
  assert.deepEqual(corner.region, {x: 0, y: 0, w: 100, h: 100});
  assert.deepEqual(corner.face, {x: 0, y: 0, w: 90, h: 90});
});

test('detector boxes become square, cover forehead and chin, and stay inside', () => {
  const sq = squareFaceBox({x: 100, y: 100, w: 80, h: 100}, 1000, 800);
  assert.equal(sq.w, sq.h);
  assert.equal(sq.w, 125);
  assert.ok(sq.y < 100 && sq.y + sq.h > 200);
  const edge = squareFaceBox({x: 980, y: 790, w: 40, h: 40}, 1000, 800);
  assert.ok(edge.x + edge.w <= 1000 && edge.y + edge.h <= 800 && edge.x >= 0 && edge.y >= 0);
});

test('drawn boxes are ordered, clipped, and ignored when tiny', () => {
  assert.deepEqual(drawnFaceBox({x: 300, y: 200}, {x: 100, y: 50}, 1000, 800), {x: 100, y: 50, w: 200, h: 150});
  assert.deepEqual(drawnFaceBox({x: -20, y: -20}, {x: 50, y: 50}, 1000, 800), {x: 0, y: 0, w: 50, h: 50});
  assert.equal(drawnFaceBox({x: 10, y: 10}, {x: 20, y: 300}, 1000, 800), null);
});

test('detection windows cover the photo at two scales and stay inside it', () => {
  const windows = detectionWindows(4032, 3024);
  assert.deepEqual(windows[0], {x: 0, y: 0, w: 4032, h: 3024});
  for (const w of windows) assert.ok(w.x >= 0 && w.y >= 0 && w.x + w.w <= 4032 && w.y + w.h <= 3024);
  assert.deepEqual([...new Set(windows.slice(1).map((w) => w.w))], [1512, 756]);
  assert.equal(detectionWindows(640, 480).length, 1);
});

test('the same face found in several windows is kept once, at its best score', () => {
  const merged = mergeDetections([
    {x: 100, y: 100, w: 50, h: 50, score: 0.7},
    {x: 104, y: 98, w: 52, h: 52, score: 0.9},
    {x: 110, y: 110, w: 20, h: 20, score: 0.8},
    {x: 400, y: 100, w: 50, h: 50, score: 0.6},
  ]);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].score, 0.9);
});
