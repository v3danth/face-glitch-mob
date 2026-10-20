import assert from 'node:assert/strict';
import {test} from 'node:test';

import {createMachine} from './machine.js';
import {
  BOARD, DEFAULT_BRUSH, PHOTO_TABLE, RENDER_TABLE, applyPreset, cellAt, emptyLayout,
  gridEdges, layoutForGrid, normalizeBrush, normalizeSettings, paintAll, roundHalfEven, toggleCell,
} from './model.js';

const quiet = () => {
  const refused = [];
  return {refused, hooks: {onRefused: (name, state, event) => refused.push(`${state}:${event}`)}};
};

test('photo table: every designed move lands where the design doc says', () => {
  const expected = [
    ['empty', 'choose', 'loading'], ['loading', 'found', 'ready'], ['loading', 'none', 'noFaces'],
    ['loading', 'fail', 'failed'], ['loading', 'choose', 'loading'], ['ready', 'choose', 'loading'],
    ['ready', 'expire', 'loading'], ['ready', 'addFace', 'ready'], ['noFaces', 'addFace', 'ready'],
    ['noFaces', 'choose', 'loading'], ['failed', 'choose', 'loading'], ['ready', 'reset', 'empty'],
    ['noFaces', 'reset', 'empty'], ['failed', 'reset', 'empty'],
  ];
  for (const [from, event, to] of expected) {
    const {hooks} = quiet();
    const machine = createMachine('photo', PHOTO_TABLE, from, hooks);
    assert.equal(machine.send(event), true, `${from} --${event}-->`);
    assert.equal(machine.state, to);
  }
});

test('photo table: undesigned moves are refused and leave the state alone', () => {
  for (const [from, event] of [['empty', 'found'], ['empty', 'expire'], ['ready', 'found'], ['failed', 'addFace'], ['loading', 'reset']]) {
    const {refused, hooks} = quiet();
    const machine = createMachine('photo', PHOTO_TABLE, from, hooks);
    assert.equal(machine.send(event), false);
    assert.equal(machine.state, from);
    assert.deepEqual(refused, [`${from}:${event}`]);
  }
});

test('render table: latest wins, never more than one queued', () => {
  const {refused, hooks} = quiet();
  const render = createMachine('render', RENDER_TABLE, 'idle', hooks);
  for (const event of ['request', 'request', 'request', 'done', 'done']) render.send(event);
  assert.equal(render.state, 'idle');
  assert.deepEqual(refused, []);
  assert.equal(render.send('done'), false);
});

test('every state has a way out', () => {
  for (const table of [PHOTO_TABLE, RENDER_TABLE]) {
    for (const [state, moves] of Object.entries(table)) {
      assert.ok(Object.values(moves).some((next) => next !== state), `${state} is a dead end`);
    }
  }
});

test('sync replays any known state and rejects unknown ones', () => {
  const machine = createMachine('photo', PHOTO_TABLE, 'loading', quiet().hooks);
  machine.sync('empty');
  assert.equal(machine.state, 'empty');
  assert.throws(() => machine.sync('nowhere'));
});

test('random walk of UI-driven events never hits a refused move', () => {
  // The studio only sends what the current state allows (it checks can()),
  // plus server replies that the design says can arrive in that state.
  const {refused, hooks} = quiet();
  const photo = createMachine('photo', PHOTO_TABLE, 'empty', hooks);
  const render = createMachine('render', RENDER_TABLE, 'idle', hooks);
  let seed = 1;
  const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 5000; i++) {
    const machine = random() < 0.5 ? photo : render;
    const allowed = Object.keys(machine === photo ? PHOTO_TABLE[photo.state] : RENDER_TABLE[render.state]);
    machine.send(allowed[Math.floor(random() * allowed.length)]);
  }
  assert.deepEqual(refused, []);
});

test('settings: empty, negative and inverted inputs never reach the renderer', () => {
  const s = normalizeSettings({seed: '', grid: '99', intensity: -3, distortionMin: 25, distortionMax: 2, likeness: 'x'});
  assert.equal(s.seed, 7);
  assert.equal(s.grid, 12);
  assert.equal(s.intensity, 0.1);
  assert.deepEqual([s.distortionMin, s.distortionMax], [2, 25]);
  assert.equal(s.likeness, 0.9);
  assert.equal(normalizeSettings({seed: -5}).seed, 5);
  assert.equal(normalizeSettings({seed: 2 ** 40}).seed, 2 ** 32 - 1);
});

test('brush: unknown material, tint or colour fall back to defaults', () => {
  const b = normalizeBrush({material: 'lava', tint: {mode: 'neon', color: 'red', strength: 7}, angle: '45'});
  assert.equal(b.material, DEFAULT_BRUSH.material);
  assert.deepEqual(b.tint, {mode: 'none', color: '#5aaaff', strength: 1});
  assert.equal(b.angle, 45);
});

test('layout: a preset survives any grid change, both ways', () => {
  const frosted = {...DEFAULT_BRUSH, material: 'frosted', tint: {mode: 'palette', color: '#5aaaff', strength: 0.55}};
  let layout = paintAll(3, 2, frosted);
  for (const grid of [5, 1, 12, 2, 3]) {
    layout = layoutForGrid(layout, grid);
    assert.equal(layout.grid, grid);
    assert.equal(Object.keys(layout.cells).length, 2 * grid * grid, `grid ${grid} lost painted cells`);
    assert.ok(Object.values(layout.cells).every((style) => style.material === 'frosted'));
  }
});

test('layout: a partial pattern keeps its place and shape on a new grid', () => {
  const ice = {...DEFAULT_BRUSH, material: 'ice'};
  // Bottom-right cell of a 2x2 grid is the bottom-right quarter of the face.
  const layout = layoutForGrid(toggleCell(emptyLayout(2), {face: 0, row: 1, col: 1}, ice), 4);
  assert.deepEqual(Object.keys(layout.cells).sort(), ['0:2:2', '0:2:3', '0:3:2', '0:3:3']);
  assert.equal(layoutForGrid(layout, 4), layout);
});

test('layout: carried cells always lie inside the new grid', () => {
  const layout = layoutForGrid(paintAll(12, 1, DEFAULT_BRUSH), 2);
  for (const key of Object.keys(layout.cells)) {
    const [, row, col] = key.split(':').map(Number);
    assert.ok(row < 2 && col < 2, key);
  }
});

test('layout: same brush toggles a cell off, a different one repaints it', () => {
  const hit = {face: 1, row: 0, col: 2};
  const once = toggleCell(emptyLayout(3), hit, DEFAULT_BRUSH);
  assert.deepEqual(toggleCell(once, hit, DEFAULT_BRUSH).cells, {});
  const other = toggleCell(once, hit, {...DEFAULT_BRUSH, material: 'ice'});
  assert.equal(other.cells['1:0:2'].material, 'ice');
});

test('preset paints every cell of every face on its own grid', () => {
  const {settings, layout} = applyPreset('frostedPanes', normalizeSettings({}), 2);
  assert.equal(settings.grid, 3);
  assert.equal(layout.grid, 3);
  assert.equal(Object.keys(layout.cells).length, 18);
  assert.equal(paintAll(2, 3, DEFAULT_BRUSH).grid, 2);
});

test('cell edges round like numpy so boundary clicks hit the same cell', () => {
  assert.deepEqual([0.5, 1.5, 2.5, -0.5].map(roundHalfEven), [0, 2, 2, 0]);
  // numpy: np.linspace(0, 103, 7).round() -> [0, 17, 34, 52, 69, 86, 103]
  assert.deepEqual(gridEdges(103, 6), [0, 17, 34, 52, 69, 86, 103]);
});

test('board clicks map to face, row and column; gaps map to nothing', () => {
  const faces = [{w: 90, h: 90}, {w: 60, h: 60}];
  assert.deepEqual(cellAt(faces, 3, 5, 5), {face: 0, row: 0, col: 0});
  assert.deepEqual(cellAt(faces, 3, BOARD.slot - 1, BOARD.slot - 1), {face: 0, row: 2, col: 2});
  assert.deepEqual(cellAt(faces, 3, BOARD.slot + BOARD.gap + BOARD.slot / 2, 5), {face: 1, row: 0, col: 1});
  assert.equal(cellAt(faces, 3, BOARD.slot + 2, 5), null);
  assert.equal(cellAt(faces, 3, 2 * (BOARD.slot + BOARD.gap) + 5, 5), null);
  assert.equal(cellAt(faces, 3, -1, 5), null);
});
