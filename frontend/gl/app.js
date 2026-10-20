/**
 * @fileoverview Glass GL page: wires controls to the shared model and the
 * WebGL renderer.
 *
 * Handlers send machine events and replace model values; paint() is the
 * only place that reads state to draw. See docs/frontend-design.md.
 */

import {createMachine} from '../shared/machine.js';
import {
  DEFAULT_BRUSH, DEFAULT_SETTINGS, MATERIALS, PHOTO_TABLE, PRESETS, RENDER_TABLE, TINT_MODES,
  applyPreset, cellAt, emptyLayout, layoutForGrid, normalizeBrush, normalizeSettings, paintAll, toggleCell,
} from '../shared/model.js';
import {drawBoard} from './board.js';
import {detectFaces} from './detector.js';
import {drawnFaceBox} from './faces.js';
import {GlassRenderer} from './renderer.js';

const $ = (id) => document.getElementById(id);
const STORAGE_KEY = 'glass-gl.v1';
const params = new URLSearchParams(location.search);

const SETTING_INPUTS = ['grid', 'seed', 'seamless', 'likeness', 'intensity', 'distortionMin', 'distortionMax', 'noise'];
const BRUSH_INPUTS = ['material', 'tintMode', 'tintColor', 'tintStrength', 'randomAngle', 'angle'];

const view = {
  settings: normalizeSettings(DEFAULT_SETTINGS),
  brush: normalizeBrush(DEFAULT_BRUSH),
  layout: emptyLayout(DEFAULT_SETTINGS.grid),
  faces: [],
  photoToken: 0,
  marking: false,
  drag: null,
  cursor: null,
};

const photo = createMachine('photo', PHOTO_TABLE, 'empty');
const render = createMachine('render', RENDER_TABLE, 'idle');
let renderer = null;

// ---------------------------------------------------------------- storage

function loadSaved() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}');
    if (saved.settings) view.settings = normalizeSettings({...DEFAULT_SETTINGS, ...saved.settings});
    if (saved.brush) view.brush = normalizeBrush(saved.brush);
  } catch {
    // Private windows and blocked storage just start from defaults.
  }
  view.layout = emptyLayout(view.settings.grid);
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({settings: view.settings, brush: view.brush}));
  } catch {
    // Saving preferences is a convenience; the page works without it.
  }
}

// ---------------------------------------------------------------- controls

function settingsFromControls() {
  return normalizeSettings({
    grid: $('grid').value,
    seed: $('seed').value,
    seamless: $('seamless').checked,
    likeness: $('likeness').value,
    intensity: $('intensity').value,
    distortionMin: $('distortionMin').value,
    distortionMax: $('distortionMax').value,
    noise: $('noise').value,
  });
}

function brushFromControls() {
  return normalizeBrush({
    material: $('material').value,
    tint: {mode: $('tintMode').value, color: $('tintColor').value, strength: $('tintStrength').value},
    angle: $('randomAngle').checked ? null : $('angle').value,
  });
}

function writeControls() {
  const s = view.settings;
  for (const key of SETTING_INPUTS) {
    if (key === 'seamless') $(key).checked = s.seamless;
    else $(key).value = String(s[key]);
  }
  const b = view.brush;
  $('material').value = b.material;
  $('tintMode').value = b.tint.mode;
  $('tintColor').value = b.tint.color;
  $('tintStrength').value = String(b.tint.strength);
  $('randomAngle').checked = b.angle === null;
  $('angle').value = String(b.angle ?? 0);
  writeOutputs();
}

function writeOutputs() {
  const s = view.settings;
  $('gridOut').value = `${s.grid} x ${s.grid}`;
  $('likenessOut').value = s.likeness.toFixed(2);
  $('intensityOut').value = s.intensity.toFixed(2);
  $('distortionMinOut').value = s.distortionMin.toFixed(1);
  $('distortionMaxOut').value = s.distortionMax.toFixed(1);
  $('noiseOut').value = s.noise.toFixed(1);
  $('tintStrengthOut').value = view.brush.tint.strength.toFixed(2);
  $('angleOut').value = view.brush.angle === null ? 'random' : `${view.brush.angle} deg`;
  $('angle').disabled = view.brush.angle === null;
  $('tintColor').disabled = view.brush.tint.mode !== 'color';
}

/** Buttons follow the photo state; rendering reads state, never sets it. */
function renderControls() {
  const state = photo.state;
  const hasFaces = state === 'ready';
  for (const id of ['paintAll', 'clearCells']) $(id).disabled = !hasFaces;
  for (const button of $('presets').querySelectorAll('button')) button.disabled = !hasFaces;
  $('download').disabled = !(state === 'ready' || state === 'noFaces');
  $('markFace').disabled = !photo.can('addFace');
  $('removePhoto').disabled = !photo.can('reset');
  if (!photo.can('addFace')) setMarking(false);
}

function setStatus(text, isError = false) {
  $('status').textContent = text;
  $('status').classList.toggle('error', isError);
}

function setMarking(on) {
  view.marking = on;
  $('markFace').setAttribute('aria-pressed', String(on));
  document.querySelector('.photo-wrap').classList.toggle('marking', on);
  drawOverlay();
}

// ---------------------------------------------------------------- rendering

/** Latest wins: a request while a frame is pending folds into it. */
function requestRender() {
  if (!render.send('request')) return;
  if (render.state === 'busy') requestAnimationFrame(frame);
}

function frame() {
  try {
    paint();
    render.send('done');
  } catch (error) {
    console.error(error);
    setStatus(`Render failed: ${error.message}`, true);
    render.send('fail');
  }
  if (render.state === 'busy') requestAnimationFrame(frame);
}

function paint() {
  if (!renderer) return;
  const state = photo.state;
  if (state === 'ready' || state === 'noFaces') {
    const faces = state === 'ready' ? view.faces : [];
    renderer.render(faces, view.settings, view.layout);
    drawBoard($('board'), $('photo'), faces, view.layout, document.activeElement === $('board') ? view.cursor : null);
  } else if (state === 'empty') {
    drawBoard($('board'), $('photo'), [], view.layout);
  }
  drawOverlay();
}

function drawOverlay() {
  const overlay = $('overlay');
  const photoCanvas = $('photo');
  overlay.width = photoCanvas.clientWidth;
  overlay.height = photoCanvas.clientHeight;
  const ctx = overlay.getContext('2d');
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  if (!view.marking || !photoCanvas.width) return;
  const k = overlay.width / photoCanvas.width;
  ctx.lineWidth = 2;
  ctx.strokeStyle = '#38bdf8';
  for (const f of view.faces) ctx.strokeRect(f.x * k, f.y * k, f.w * k, f.h * k);
  if (view.drag) {
    ctx.setLineDash([6, 4]);
    const {a, b} = view.drag;
    ctx.strokeRect(Math.min(a.x, b.x) * k, Math.min(a.y, b.y) * k, Math.abs(b.x - a.x) * k, Math.abs(b.y - a.y) * k);
  }
}

// ---------------------------------------------------------------- photo

/**
 * Loads a photo and finds faces. A newer choice supersedes an older one
 * still loading: each load carries a token and stale results are dropped.
 */
async function choosePhoto(blob, label, forcedFaces = null) {
  const token = ++view.photoToken;
  photo.send('choose');
  setStatus(`Loading ${label}...`);
  try {
    const bitmap = await createImageBitmap(blob, {imageOrientation: 'from-image'});
    if (token !== view.photoToken) return bitmap.close();
    renderer.setPhoto(bitmap);
    view.faces = [];
    view.layout = emptyLayout(view.settings.grid);
    let faces = forcedFaces;
    let note = '';
    if (!faces) {
      setStatus('Looking for faces on this device...');
      const started = performance.now();
      try {
        faces = await detectFaces(bitmap);
        note = ` (${Math.round(performance.now() - started)} ms)`;
      } catch (error) {
        console.warn('face detector unavailable', error);
        faces = [];
        note = '. The face detector could not load (offline?)';
      }
    }
    if (token !== view.photoToken) return bitmap.close();
    view.faces = faces;
    photo.send(faces.length ? 'found' : 'none');
    setStatus(faces.length ?
      `Found ${faces.length} face(s)${note}. Click cells on the board to paint them.` :
      `No faces found${note}. Use "Mark a face" and drag over each face.`);
    bitmap.close();
    requestRender();
  } catch (error) {
    if (token !== view.photoToken) return;
    console.warn('photo could not be opened', error); // a user-facing outcome, not a bug
    photo.send('fail');
    setStatus(`Could not open that photo: ${error.message}`, true);
  }
}

function removePhoto() {
  if (!photo.send('reset')) return;
  view.photoToken++;
  view.faces = [];
  view.layout = emptyLayout(view.settings.grid);
  renderer.clearPhoto();
  $('photo').width = 0;
  $('photo').height = 0;
  setStatus('No photo yet.');
  requestRender();
}

function photoPoint(event) {
  const rect = $('overlay').getBoundingClientRect();
  const k = $('photo').width / rect.width;
  return {x: (event.clientX - rect.left) * k, y: (event.clientY - rect.top) * k};
}

// ---------------------------------------------------------------- board

function boardHit(event) {
  const board = $('board');
  const rect = board.getBoundingClientRect();
  const x = ((event.clientX - rect.left) * board.width) / rect.width;
  const y = ((event.clientY - rect.top) * board.height) / rect.height;
  return cellAt(view.faces, view.layout.grid, x, y);
}

/** Arrow keys walk cells across faces; Enter or Space paints like a click. */
function onBoardKey(event) {
  if (photo.state !== 'ready' || !view.faces.length) return;
  const n = view.layout.grid;
  const c = view.cursor && view.cursor.face < view.faces.length ? {...view.cursor} : {face: 0, row: 0, col: 0};
  const moves = {
    ArrowLeft: () => (c.col > 0 ? c.col-- : c.face > 0 && (c.face--, (c.col = n - 1))),
    ArrowRight: () => (c.col < n - 1 ? c.col++ : c.face < view.faces.length - 1 && (c.face++, (c.col = 0))),
    ArrowUp: () => c.row > 0 && c.row--,
    ArrowDown: () => c.row < n - 1 && c.row++,
  };
  if (moves[event.key]) {
    moves[event.key]();
  } else if (event.key === 'Enter' || event.key === ' ') {
    paintCell({face: c.face, row: Math.min(c.row, n - 1), col: Math.min(c.col, n - 1)});
  } else {
    return;
  }
  event.preventDefault();
  view.cursor = {face: c.face, row: Math.min(c.row, n - 1), col: Math.min(c.col, n - 1)};
  requestRender();
}

function paintCell(hit) {
  if (!hit || photo.state !== 'ready') return;
  view.layout = toggleCell(view.layout, hit, view.brush);
  requestRender();
}

// ---------------------------------------------------------------- wiring

function onSettingsInput() {
  view.settings = settingsFromControls();
  // Any grid change, however it happens, carries the painting onto the new grid.
  view.layout = layoutForGrid(view.layout, view.settings.grid);
  writeOutputs();
  save();
  requestRender();
}

function onBrushInput() {
  view.brush = brushFromControls();
  writeOutputs();
  save();
}

function applyNamedPreset(name) {
  if (photo.state !== 'ready') return;
  const next = applyPreset(name, view.settings, view.faces.length);
  Object.assign(view, next);
  writeControls();
  save();
  requestRender();
}

function populateSelects() {
  $('material').replaceChildren(...['random', ...MATERIALS].map((name) => new Option(name, name)));
  $('tintMode').replaceChildren(...TINT_MODES.map((name) => new Option(name, name)));
  $('presets').replaceChildren(...Object.entries(PRESETS).map(([name, preset]) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = preset.label;
    button.addEventListener('click', () => applyNamedPreset(name));
    return button;
  }));
}

function wire() {
  for (const id of SETTING_INPUTS) $(id).addEventListener('input', onSettingsInput);
  // Typed values settle on change: show what the renderer actually uses.
  for (const id of SETTING_INPUTS) $(id).addEventListener('change', writeControls);
  for (const id of BRUSH_INPUTS) $(id).addEventListener('input', onBrushInput);

  $('file').addEventListener('change', () => {
    const file = $('file').files[0];
    if (file) choosePhoto(file, file.name);
    $('file').value = '';
  });
  const drop = $('drop');
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault();
    drop.classList.remove('over');
    const file = [...e.dataTransfer.files].find((f) => f.type.startsWith('image/'));
    if (file) choosePhoto(file, file.name);
  });

  $('board').addEventListener('click', (e) => paintCell(boardHit(e)));
  $('board').addEventListener('keydown', onBoardKey);
  $('board').addEventListener('focus', requestRender);
  $('board').addEventListener('blur', requestRender);
  $('paintAll').addEventListener('click', () => {
    view.layout = paintAll(view.settings.grid, view.faces.length, view.brush);
    requestRender();
  });
  $('clearCells').addEventListener('click', () => {
    view.layout = emptyLayout(view.settings.grid);
    requestRender();
  });
  $('removePhoto').addEventListener('click', removePhoto);
  $('markFace').addEventListener('click', () => setMarking(!view.marking));
  $('download').addEventListener('click', download);

  const overlay = $('overlay');
  overlay.addEventListener('pointerdown', (e) => {
    if (!view.marking) return;
    overlay.setPointerCapture(e.pointerId);
    view.drag = {a: photoPoint(e), b: photoPoint(e)};
  });
  overlay.addEventListener('pointermove', (e) => {
    if (!view.drag) return;
    view.drag.b = photoPoint(e);
    drawOverlay();
  });
  overlay.addEventListener('pointerup', () => {
    if (!view.drag) return;
    const {a, b} = view.drag;
    view.drag = null;
    const box = drawnFaceBox(a, b, $('photo').width, $('photo').height);
    if (box && photo.send('addFace')) {
      view.faces = [...view.faces, box];
      setStatus(`${view.faces.length} face(s). Click cells on the board to paint them.`);
      requestRender();
    }
    drawOverlay();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && view.marking) setMarking(false);
  });
  window.addEventListener('resize', drawOverlay);
  photo.subscribe(renderControls);
}

function download() {
  if (!(photo.state === 'ready' || photo.state === 'noFaces')) return;
  $('photo').toBlob((blob) => {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'glass.png';
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }, 'image/png');
}

// ---------------------------------------------------------------- dev hooks

/**
 * Dev-only URL parameters for headless checks: ?demo=<image url>,
 * ?face=x,y,w,h (skips the detector), ?paint=<material>&tint=<mode>&
 * strength=<0..1>, setting overrides (?grid=3&seamless=0...), ?bench=1.
 */
async function runDevHooks() {
  if (!params.has('demo')) return;
  const overrides = {};
  for (const key of SETTING_INPUTS) if (params.has(key)) overrides[key] = key === 'seamless' ? params.get(key) === '1' : params.get(key);
  view.settings = normalizeSettings({...view.settings, ...overrides});
  if (params.has('paint')) {
    view.brush = normalizeBrush({
      material: params.get('paint'),
      tint: {mode: params.get('tint') ?? 'none', color: params.get('color') ?? '#5aaaff', strength: params.get('strength') ?? 0.5},
      angle: params.has('angle') ? params.get('angle') : null,
    });
  }
  writeControls();
  const forced = params.get('face')?.split(',').map(Number);
  const blob = await (await fetch(params.get('demo'))).blob();
  await choosePhoto(blob, 'demo', forced ? [{x: forced[0], y: forced[1], w: forced[2], h: forced[3]}] : null);
  if (params.has('paint')) view.layout = paintAll(view.settings.grid, view.faces.length, view.brush);
  paint();
  if (params.has('bench')) bench();
  document.body.dataset.ready = 'true';
}

/** Frame times for a full re-render (draw + GPU finish), steady and cold. */
function bench() {
  const report = {faces: view.faces, photo: [$('photo').width, $('photo').height], floatTargets: renderer.floatTargets};
  for (const grid of [3, 12]) {
    view.settings = normalizeSettings({...view.settings, grid});
    view.layout = emptyLayout(grid);
    let t = performance.now();
    renderer.render(view.faces, view.settings, view.layout);
    renderer.finish();
    const cold = performance.now() - t;
    const times = [];
    for (let i = 0; i < 20; i++) {
      view.settings = normalizeSettings({...view.settings, seed: i + 1});
      t = performance.now();
      renderer.render(view.faces, view.settings, view.layout);
      renderer.finish();
      times.push(performance.now() - t);
    }
    times.sort((a, b) => a - b);
    report[`grid${grid}`] = {
      coldMs: +cold.toFixed(1),
      p50Ms: +times[Math.floor(times.length * 0.5)].toFixed(1),
      p95Ms: +times[Math.floor(times.length * 0.95)].toFixed(1),
    };
  }
  $('bench').hidden = false;
  $('bench').textContent = JSON.stringify(report);
}

// ---------------------------------------------------------------- start

function start() {
  populateSelects();
  loadSaved();
  writeControls();
  wire();
  renderControls();
  try {
    renderer = new GlassRenderer($('photo'));
  } catch (error) {
    setStatus(`${error.message}. Try the Studio version instead.`, true);
    return;
  }
  runDevHooks().catch((error) => {
    setStatus(`Demo failed: ${error.message}`, true);
    document.body.dataset.ready = 'error';
  });
}

start();
