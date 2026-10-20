/**
 * @fileoverview Glass Studio DOM bindings. Behaviour lives in controller.js;
 * this file turns DOM events into controller calls and draws what the
 * controller's state says.
 */

import {PhotoExpired, createStudio} from './controller.js';
import {
  BOARD, DEFAULT_BRUSH, DEFAULT_SETTINGS, DIRECTIONAL, MATERIALS, MATERIAL_COLORS, PRESETS, TINT_MODES,
  boardSize, gridEdges, materialLabel, normalizeBrush, normalizeSettings, parseCellKey, slotOrigin,
} from '../shared/model.js';

const PREFS_KEY = 'glass-studio:prefs:v1';
const SETTING_IDS = ['grid', 'intensity', 'likeness', 'seamless', 'seed', 'distortionMin', 'distortionMax', 'noise'];
const BRUSH_IDS = ['material', 'tintMode', 'tintColor', 'tintStrength', 'randomAngle', 'angle'];

const $ = (id) => document.getElementById(id);
const ui = {
  file: $('file'), drop: $('drop'), status: $('status'), drawFace: $('draw-face'), download: $('download'),
  presets: $('presets'), board: $('board'), legend: $('legend'), result: $('result'), timing: $('timing'),
  paintAll: $('paint-all'), clear: $('clear'),
};

// ---- network ----

async function errorText(response) {
  try {
    const body = await response.json();
    return typeof body.detail === 'string' ? body.detail : `Request failed (${response.status}).`;
  } catch {
    return `Request failed (${response.status}).`;
  }
}

const api = {
  async upload(file) {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch('/api/photos', {method: 'POST', body: form});
    if (!response.ok) throw new Error(await errorText(response));
    return response.json();
  },
  async render(body) {
    const response = await fetch('/api/render', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (response.status === 404) throw new PhotoExpired('Photo expired.');
    if (!response.ok) throw new Error(await errorText(response));
    return response.json();
  },
};

// ---- drawing ----

let drawing = null;

const view = {
  photoLoaded(image, body) {
    ui.result.width = body.width;
    ui.result.height = body.height;
    ui.result.getContext('2d').drawImage(image, 0, 0);
  },
  async drawResult(patches, result) {
    const images = await Promise.all(patches.map(async (patch) => {
      const image = new Image();
      image.src = patch.data;
      await image.decode();
      return {patch, image};
    }));
    const ctx = ui.result.getContext('2d');
    ctx.drawImage(studio.app.image, 0, 0);
    for (const {patch, image} of images) ctx.drawImage(image, patch.x, patch.y);
    ui.timing.textContent = `${result.ms} ms on the server`;
  },
  changed() {
    // Coalesce bursts of state changes into one paint per frame.
    if (view.pending) return;
    view.pending = requestAnimationFrame(() => {
      view.pending = 0;
      paint();
    });
  },
  pending: 0,
};

const studio = createStudio({
  api,
  view,
  decode: (file) => createImageBitmap(file, {imageOrientation: 'from-image'}),
});

const STATUS = {
  empty: () => 'No photo yet.',
  loading: () => 'Finding faces...',
  ready: () => {
    const n = studio.app.faces.length;
    return `${n} face${n === 1 ? '' : 's'}. Click cells on the board to paint them.`;
  },
  noFaces: () => 'No faces found. Use "Draw a face box" and drag across a face on the result.',
  failed: () => studio.app.message || 'Something went wrong. Choose the photo again.',
};

function paint() {
  const state = studio.photo.state;
  const renderFailed = studio.render.state === 'failed';
  ui.status.textContent = renderFailed ? studio.app.message : STATUS[state]();
  ui.status.classList.toggle('error', state === 'failed' || renderFailed);
  const ready = state === 'ready';
  ui.download.disabled = !(ready && studio.app.rendered);
  ui.drawFace.disabled = !(ready || state === 'noFaces');
  for (const button of [ui.paintAll, ui.clear, ...ui.presets.querySelectorAll('button')]) button.disabled = !ready;
  if (ui.drawFace.disabled) setDrawing(false);
  writeOutputs();
  drawBoard();
}

function drawBoard() {
  const {faces, layout, image} = studio.app;
  const {width, height} = boardSize(faces.length);
  if (ui.board.width !== width || ui.board.height !== height) Object.assign(ui.board, {width, height});
  const ctx = ui.board.getContext('2d');
  ctx.fillStyle = '#111827';
  ctx.fillRect(0, 0, width, height);
  faces.forEach((face, index) => {
    const origin = slotOrigin(index);
    if (image) ctx.drawImage(ui.result, face.x, face.y, face.w, face.h, origin.x, origin.y, BOARD.slot, BOARD.slot);
    const xs = gridEdges(face.w, layout.grid).map((edge) => origin.x + (edge * BOARD.slot) / face.w);
    const ys = gridEdges(face.h, layout.grid).map((edge) => origin.y + (edge * BOARD.slot) / face.h);
    ctx.strokeStyle = 'rgba(255,255,255,0.75)';
    ctx.lineWidth = 1;
    for (const x of xs) line(ctx, x, origin.y, x, origin.y + BOARD.slot);
    for (const y of ys) line(ctx, origin.x, y, origin.x + BOARD.slot, y);
    drawMarkers(ctx, index, xs, ys);
  });
}

function drawMarkers(ctx, faceIndex, xs, ys) {
  ctx.font = `${Math.max(10, Math.min(15, (xs[1] - xs[0]) / 4))}px system-ui, sans-serif`;
  ctx.textBaseline = 'top';
  for (const [key, style] of Object.entries(studio.app.layout.cells)) {
    const {face, row, col} = parseCellKey(key);
    if (face !== faceIndex) continue;
    ctx.strokeStyle = ctx.fillStyle = MATERIAL_COLORS[style.material];
    ctx.lineWidth = 2;
    ctx.strokeRect(xs[col] + 2, ys[row] + 2, xs[col + 1] - xs[col] - 4, ys[row + 1] - ys[row] - 4);
    ctx.fillText(materialLabel(style.material), xs[col] + 5, ys[row] + 5);
  }
}

function line(ctx, x0, y0, x1, y1) {
  ctx.beginPath();
  ctx.moveTo(x0 + 0.5, y0 + 0.5);
  ctx.lineTo(x1 + 0.5, y1 + 0.5);
  ctx.stroke();
}

function canvasPoint(canvas, event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) * canvas.width) / rect.width,
    y: ((event.clientY - rect.top) * canvas.height) / rect.height,
  };
}

// ---- forms ----

function readSettingsForm() {
  return Object.fromEntries(SETTING_IDS.map((id) => [id, id === 'seamless' ? $(id).checked : $(id).value]));
}

function readBrushForm() {
  return {
    material: $('material').value,
    tint: {mode: $('tintMode').value, color: $('tintColor').value, strength: $('tintStrength').value},
    angle: $('randomAngle').checked ? null : $('angle').value,
  };
}

function writeForms() {
  const {settings, brush} = studio.app;
  for (const id of SETTING_IDS) {
    if (id === 'seamless') $(id).checked = settings.seamless;
    else $(id).value = settings[id];
  }
  $('material').value = brush.material;
  $('tintMode').value = brush.tint.mode;
  $('tintColor').value = brush.tint.color;
  $('tintStrength').value = brush.tint.strength;
  $('randomAngle').checked = brush.angle === null;
  $('angle').value = brush.angle ?? 0;
  writeOutputs();
}

function writeOutputs() {
  for (const output of document.querySelectorAll('output[for]')) output.value = $(output.htmlFor.value).value;
  const {brush} = studio.app;
  const directional = DIRECTIONAL.has(brush.material) || brush.material === 'random';
  $('randomAngle').disabled = !directional;
  $('angle').disabled = !directional || brush.angle === null;
  $('tintColor').disabled = brush.tint.mode !== 'color';
}

function fillChoices() {
  const option = (value, text = value) => Object.assign(document.createElement('option'), {value, textContent: text});
  $('material').append(option('random', 'random mix'), ...MATERIALS.map((name) => option(name)));
  $('tintMode').append(...TINT_MODES.map((mode) => option(mode)));
  for (const [name, preset] of Object.entries(PRESETS)) {
    const button = Object.assign(document.createElement('button'), {type: 'button', textContent: preset.label});
    button.dataset.preset = name;
    ui.presets.append(button);
  }
  ui.legend.innerHTML = ['random', ...MATERIALS]
      .map((name) => `<span><i style="background:${MATERIAL_COLORS[name]}"></i>${materialLabel(name)} ${name}</span>`)
      .join('');
}

// ---- preferences (per-viewer convenience; the photo is never stored) ----

function loadPrefs() {
  try {
    const saved = JSON.parse(localStorage.getItem(PREFS_KEY) ?? 'null');
    if (!saved) return;
    studio.setSettings({...DEFAULT_SETTINGS, ...saved.settings});
    studio.setBrush({...DEFAULT_BRUSH, ...saved.brush});
  } catch {
    // Private windows and blocked storage just start from defaults.
  }
}

function savePrefs() {
  try {
    const {settings, brush} = studio.app;
    localStorage.setItem(PREFS_KEY, JSON.stringify({settings: normalizeSettings(settings), brush: normalizeBrush(brush)}));
  } catch {
    // Not saving preferences is harmless.
  }
}

// ---- events ----

function setDrawing(on) {
  ui.drawFace.setAttribute('aria-pressed', String(on));
  ui.result.classList.toggle('drawing', on);
  if (!on) drawing = null;
}

function choose(file) {
  if (!file) return;
  if (!file.type.startsWith('image/')) {
    ui.status.textContent = 'That file is not an image.';
    ui.status.classList.add('error');
    return;
  }
  studio.choosePhoto(file);
}

function bindEvents() {
  ui.file.addEventListener('change', () => choose(ui.file.files[0]));
  for (const type of ['dragenter', 'dragover']) {
    ui.drop.addEventListener(type, (event) => {
      event.preventDefault();
      ui.drop.classList.add('over');
    });
  }
  for (const type of ['dragleave', 'drop']) ui.drop.addEventListener(type, () => ui.drop.classList.remove('over'));
  ui.drop.addEventListener('drop', (event) => {
    event.preventDefault();
    choose(event.dataTransfer.files[0]);
  });
  // A photo dropped beside the target must not navigate away from the page.
  window.addEventListener('dragover', (event) => event.preventDefault());
  window.addEventListener('drop', (event) => event.preventDefault());

  for (const id of SETTING_IDS) {
    $(id).addEventListener('input', () => {
      studio.setSettings(readSettingsForm());
      savePrefs();
    });
  }
  // Show the value the renderer actually used, e.g. an empty seed becomes 7.
  $('seed').addEventListener('change', writeForms);
  for (const id of BRUSH_IDS) {
    $(id).addEventListener('input', () => {
      studio.setBrush(readBrushForm());
      savePrefs();
    });
  }

  ui.board.addEventListener('click', (event) => {
    const point = canvasPoint(ui.board, event);
    studio.clickBoard(point.x, point.y);
  });
  ui.presets.addEventListener('click', (event) => {
    const name = event.target.closest('button')?.dataset.preset;
    if (!name) return;
    studio.applyPreset(name);
    writeForms();
    savePrefs();
  });
  ui.paintAll.addEventListener('click', () => studio.paintAll());
  ui.clear.addEventListener('click', () => studio.clear());

  ui.drawFace.addEventListener('click', () => setDrawing(ui.drawFace.getAttribute('aria-pressed') !== 'true'));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setDrawing(false);
  });
  ui.result.addEventListener('pointerdown', (event) => {
    if (ui.drawFace.getAttribute('aria-pressed') !== 'true') return;
    drawing = canvasPoint(ui.result, event);
    ui.result.setPointerCapture(event.pointerId);
  });
  ui.result.addEventListener('pointerup', (event) => {
    if (!drawing) return;
    const start = drawing;
    const end = canvasPoint(ui.result, event);
    setDrawing(false);
    const box = {
      x: Math.round(Math.min(start.x, end.x)),
      y: Math.round(Math.min(start.y, end.y)),
      w: Math.round(Math.abs(end.x - start.x)),
      h: Math.round(Math.abs(end.y - start.y)),
    };
    if (!studio.addFace(box)) {
      ui.status.textContent = 'That box is too small; drag across the whole face.';
      ui.status.classList.add('error');
    }
  });

  ui.download.addEventListener('click', () => {
    ui.result.toBlob((blob) => {
      const link = Object.assign(document.createElement('a'), {
        href: URL.createObjectURL(blob),
        download: `glass-${(studio.app.file?.name ?? 'photo').replace(/\.[^.]+$/, '')}.png`,
      });
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    }, 'image/png');
  });
}

// Dev mode exposes the controller so tools/e2e_studio.mjs can check state.
if (new URLSearchParams(location.search).has('dev')) window.studio = studio;

fillChoices();
loadPrefs();
writeForms();
bindEvents();
paint();
