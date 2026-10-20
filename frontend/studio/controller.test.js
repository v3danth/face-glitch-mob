import assert from 'node:assert/strict';
import {test} from 'node:test';

import {BOARD, PRESETS} from '../shared/model.js';
import {PhotoExpired, createStudio} from './controller.js';

/** Seeded random numbers so every failure replays exactly. */
function randomFrom(seed) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

/**
 * A server that is slow by random amounts, keeps two photos (so other tabs
 * evict this one), and sometimes fails. It tracks in-flight calls so the
 * simulator knows when everything has settled.
 */
function fakeServer(random) {
  const store = new Map();
  let nextId = 0;
  let pending = 0;
  const later = (fn) => {
    pending++;
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        pending--;
        try {
          resolve(fn());
        } catch (error) {
          reject(error);
        }
      }, Math.floor(random() * 6));
    });
  };
  const keep = (id, file) => {
    store.set(id, file);
    while (store.size > 2) store.delete(store.keys().next().value);
  };
  return {
    store,
    get pending() {
      return pending;
    },
    evictAll: () => store.clear(),
    api: {
      upload: (file) => later(() => {
        if (file.broken) throw new Error('Not a readable image.');
        const id = `p${nextId++}`;
        keep(id, file);
        const faces = Array.from({length: file.faces}, (_, i) => ({x: 10 + i * 100, y: 10, w: 90, h: 90}));
        return {id, width: 400, height: 200, faces};
      }),
      render: (body) => later(() => {
        if (!store.has(body.photo)) throw new PhotoExpired('expired');
        if (random() < 0.05) throw new Error('server hiccup');
        return {patches: [{photo: body.photo, file: store.get(body.photo)}], ms: 1, body};
      }),
    },
    decode: (file) => later(() => ({file})),
  };
}

async function settle(server) {
  for (let i = 0; i < 400; i++) {
    await new Promise((resolve) => setTimeout(resolve, 2));
    if (server.pending === 0) {
      await new Promise((resolve) => setTimeout(resolve, 2));
      if (server.pending === 0) return;
    }
  }
  throw new Error('requests never settled');
}

function episode(seed) {
  const random = randomFrom(seed);
  const server = fakeServer(random);
  const refused = [];
  const wrongDraws = [];
  let shown = null;
  // Assigned below; drawResult reads it when a render lands.
  let studio = null;
  studio = createStudio({
    api: server.api,
    decode: server.decode,
    onRefused: (name, state, event) => refused.push(`${name}: ${event} in ${state}`),
    view: {
      photoLoaded() {},
      async drawResult(patches, result) {
        // Even a momentary draw of another photo's glass is a visible bug.
        if (patches[0].file !== studio.app.file) wrongDraws.push(`${patches[0].file.name} over ${studio.app.file.name}`);
        shown = {file: patches[0].file, body: result.body};
      },
      changed() {},
    },
  });
  const pick = (items) => items[Math.floor(random() * items.length)];
  const files = Array.from({length: 4}, (_, i) => ({name: `f${i}`, faces: i % 3, broken: i === 3}));

  const actions = [
    () => studio.choosePhoto(pick(files)),
    () => studio.setSettings({...studio.app.settings, grid: pick([1, 2, 3, 4, '', '9', -2])}),
    () => studio.setSettings({...studio.app.settings, seed: pick([7, '', -5, 'x', 2 ** 40])}),
    () => studio.setSettings({...studio.app.settings, intensity: random() * 2, seamless: random() < 0.5}),
    () => studio.setBrush({material: pick(['ice', 'frosted', 'random', 'lava']), tint: {mode: pick(['none', 'palette', 'neon'])}}),
    () => studio.clickBoard(random() * 2 * (BOARD.slot + BOARD.gap), random() * BOARD.slot),
    () => studio.applyPreset(pick(Object.keys(PRESETS))),
    () => studio.paintAll(),
    () => studio.clear(),
    () => studio.addFace({x: random() * 300, y: random() * 100, w: random() * 120, h: random() * 120}),
    () => server.evictAll(),
  ];
  return {studio, server, refused, wrongDraws, actions, pick, random, shown: () => shown};
}

test('random users never reach an undesigned state or see stale glass', async () => {
  const problems = [];
  for (let seed = 1; seed <= 150; seed++) {
    const run = episode(seed);
    const script = [];
    for (let step = 0; step < 30; step++) {
      const action = run.pick(run.actions);
      script.push(action.toString().slice(6, 60));
      action();
      // Sometimes act before anything settles (rapid clicks), sometimes after.
      if (run.random() < 0.4) await settle(run.server);
    }
    await settle(run.server);
    const {studio} = run;
    const fail = (message) => problems.push(`seed ${seed}: ${message}\n    last steps: ${script.slice(-5).join(' | ')}`);

    if (run.refused.length) fail(`refused moves ${run.refused.join(', ')}`);
    if (run.wrongDraws.length) fail(`drew another photo's glass: ${run.wrongDraws[0]}`);
    if (studio.app.layout.grid !== studio.app.settings.grid) fail('layout grid differs from settings grid');
    if (!['idle', 'failed'].includes(studio.render.state)) fail(`render stuck in ${studio.render.state}`);
    if (studio.photo.state === 'loading') fail('photo stuck loading');
    if (studio.photo.state === 'ready' && studio.render.state === 'idle') {
      const shown = run.shown();
      if (!shown) fail('ready but nothing was ever drawn');
      else if (shown.file !== studio.app.file) fail(`shows ${shown.file.name} but the photo is ${studio.app.file.name}`);
      else assert.deepEqual(shown.body, studio.currentRequest(), `seed ${seed}: shown glass is not the current settings`);
    }
  }
  assert.deepEqual(problems, []);
});

test('a slow upload of an older photo never replaces a newer one', async () => {
  const run = episode(99);
  const {studio} = run;
  studio.choosePhoto({name: 'old', faces: 1});
  studio.choosePhoto({name: 'new', faces: 2});
  await settle(run.server);
  assert.equal(studio.app.file.name, 'new');
  assert.equal(studio.app.faces.length, 2);
  assert.equal(run.shown().file.name, 'new');
});

test('an evicted photo is re-uploaded and rendered without user action', async () => {
  const run = episode(7);
  const {studio} = run;
  studio.choosePhoto({name: 'mine', faces: 1});
  await settle(run.server);
  run.server.evictAll();
  studio.paintAll();
  await settle(run.server);
  assert.equal(studio.photo.state, 'ready');
  assert.ok(run.server.store.has(studio.app.photoId));
  assert.deepEqual(run.shown().body, studio.currentRequest());
});

test('no faces offers a way out by drawing one', async () => {
  const run = episode(3);
  const {studio} = run;
  studio.choosePhoto({name: 'wall', faces: 0});
  await settle(run.server);
  assert.equal(studio.photo.state, 'noFaces');
  assert.equal(studio.addFace({x: 5, y: 5, w: 4, h: 4}), false);
  assert.equal(studio.addFace({x: 5, y: 5, w: 60, h: 60}), true);
  await settle(run.server);
  assert.equal(studio.photo.state, 'ready');
  assert.ok(run.shown());
});
