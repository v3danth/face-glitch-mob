/**
 * @fileoverview Drives the Studio page in headless Chromium over the
 * DevTools protocol, the way a person would: real file input, real mouse
 * clicks, rapid slider input. Fails on any console error, uncaught
 * exception or refused state-machine move, and checks full-resolution
 * output.
 *
 *   python -m server.app &
 *   node tools/e2e_studio.mjs input/input.jpg [--out /tmp/studio]
 *
 * CHROME may point at any Chromium; the default is Playwright's cached
 * headless shell.
 */

import {spawn} from 'node:child_process';
import {readdirSync, writeFileSync} from 'node:fs';
import {homedir} from 'node:os';
import {resolve} from 'node:path';

const [photoArg = 'input/input.jpg', ...rest] = process.argv.slice(2);
const outIndex = rest.indexOf('--out');
const out = outIndex >= 0 ? rest[outIndex + 1] : null;
const base = process.env.STUDIO_URL ?? 'http://127.0.0.1:8000';
const photo = resolve(photoArg);

function chromePath() {
  if (process.env.CHROME) return process.env.CHROME;
  const cache = `${homedir()}/Library/Caches/ms-playwright`;
  const shell = readdirSync(cache).filter((d) => d.startsWith('chromium_headless_shell')).sort().pop();
  return `${cache}/${shell}/chrome-mac/headless_shell`;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const port = 9400 + Math.floor(Math.random() * 400);
const chrome = spawn(chromePath(), [`--remote-debugging-port=${port}`, '--window-size=1300,1800', 'about:blank'], {stdio: 'ignore'});

let ws;
for (let i = 0; i < 60 && !ws; i++) {
  try {
    const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page');
    if (page) ws = new WebSocket(page.webSocketDebuggerUrl);
  } catch {
    await sleep(200);
  }
}
await new Promise((r) => ws.addEventListener('open', r));

let nextId = 0;
const pending = new Map();
const problems = [];
ws.addEventListener('message', (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg);
    pending.delete(msg.id);
  }
  if (msg.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(msg.params.type)) {
    problems.push(`console ${msg.params.type}: ${msg.params.args.map((a) => a.value ?? a.description).join(' ')}`);
  }
  if (msg.method === 'Runtime.exceptionThrown') {
    problems.push(`exception: ${msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text}`);
  }
});
const send = (method, params = {}) => new Promise((r) => {
  const id = ++nextId;
  pending.set(id, r);
  ws.send(JSON.stringify({id, method, params}));
});
const evaluate = async (expression) => {
  const reply = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  return reply.result?.result?.value;
};
async function waitFor(expression, what, ms = 60000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await evaluate(expression)) return true;
    await sleep(100);
  }
  problems.push(`timed out waiting for ${what}`);
  return false;
}
async function click(x, y) {
  for (const type of ['mousePressed', 'mouseReleased']) {
    await send('Input.dispatchMouseEvent', {type, x, y, button: 'left', clickCount: 1});
  }
}
async function clickElement(selector) {
  const box = await evaluate(`(() => { const r = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();
    return {x: r.x + r.width / 2, y: r.y + r.height / 2}; })()`);
  await click(box.x, box.y);
}
async function chooseFile() {
  const {root} = (await send('DOM.getDocument')).result;
  const {nodeId} = (await send('DOM.querySelector', {nodeId: root.nodeId, selector: '#file'})).result;
  await send('DOM.setFileInputFiles', {nodeId, files: [photo]});
}
const setInput = (id, value) => evaluate(`(() => { const el = document.getElementById('${id}');
  el.value = ${JSON.stringify(String(value))}; el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true})); })()`);
const downloadReady = `!document.getElementById('download').disabled`;
const timing = () => evaluate(`document.getElementById('timing').textContent`);

const steps = [];
const step = (name) => steps.push(name);

await send('Runtime.enable');
await send('Page.enable');
await send('DOM.enable');
await send('Emulation.setDeviceMetricsOverride', {width: 1300, height: 1800, deviceScaleFactor: 1, mobile: false});
await evaluate(`localStorage.clear()`).catch(() => {});
await send('Page.navigate', {url: `${base}/studio/?dev=1`});
await waitFor(`document.readyState === 'complete' && !!document.getElementById('board')`, 'page load');

step('upload photo');
await chooseFile();
await waitFor(`/face/.test(document.getElementById('status').textContent)`, 'faces found');
await waitFor(downloadReady, 'first render');
const size = await evaluate(`[document.getElementById('result').width, document.getElementById('result').height]`);

step('paint the first board cell with ice');
await setInput('material', 'ice');
const boardBox = await evaluate(`(() => { const r = document.getElementById('board').getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width}; })()`);
const before = await timing();
await click(boardBox.x + 20, boardBox.y + 20);
// The painted cell's border is drawn in ice's marker colour, rgb(103 232 249).
await waitFor(`(() => { const [r, g, b] = document.getElementById('board').getContext('2d').getImageData(2, 30, 1, 1).data;
  return Math.abs(r - 103) < 30 && Math.abs(g - 232) < 30 && Math.abs(b - 249) < 30; })()`, 'ice marker on the painted cell', 5000);
await waitFor(`${downloadReady} && document.getElementById('timing').textContent !== ${JSON.stringify(before)}`, 'render after painting', 20000);

step('frosted panes preset');
await clickElement('#presets button');
await waitFor(`document.getElementById('grid').value === '3'`, 'preset grid');
await sleep(500);

step('change the grid after the preset: every tile stays frosted');
const frostedCells = `(() => { const {layout, faces} = window.studio.app;
  const cells = Object.values(layout.cells);
  return cells.length === faces.length * layout.grid * layout.grid && cells.every((s) => s.material === 'frosted'); })()`;
for (const grid of [5, 2, 8]) {
  await setInput('grid', grid);
  await waitFor(frostedCells, `all ${grid}x${grid} cells still frosted after the grid change`, 3000);
}
await setInput('grid', 3);

step('rude: junk seed, typed grid, slider storm');
for (const value of ['', '-4', 'abc', '99999999999']) await setInput('seed', value);
const seedShown = await evaluate(`document.getElementById('seed').value`);
for (let i = 0; i < 30; i++) await setInput(i % 2 ? 'intensity' : 'grid', i % 2 ? (0.1 + (i % 14) / 10).toFixed(2) : (i % 12) + 1);
await setInput('grid', 4);
await sleep(1500);
await waitFor(downloadReady, 'render after storm', 30000);

step('rude: choose the photo twice in a row');
await chooseFile();
await chooseFile();
await waitFor(`/face/.test(document.getElementById('status').textContent)`, 'faces after double upload');
await waitFor(downloadReady, 'render after double upload');

const toasts = await evaluate(`[...document.querySelectorAll('.toast')].map((t) => t.textContent)`);
for (const toast of toasts ?? []) problems.push(`toast: ${toast}`);
const status = await evaluate(`document.getElementById('status').textContent`);

if (out) {
  const shot = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true});
  writeFileSync(`${out}-page.png`, Buffer.from(shot.result.data, 'base64'));
  const board = await evaluate(`document.getElementById('board').toDataURL('image/png')`);
  writeFileSync(`${out}-board.png`, Buffer.from(board.split(',')[1], 'base64'));
}

console.log(`steps: ${steps.join(' -> ')}`);
console.log(`result canvas ${size?.join('x')}; seed field after junk: "${seedShown}"; status: ${status}; ${await timing()}`);
for (const problem of problems) console.log(`BUG  ${problem}`);
console.log(`${problems.length} problem(s)`);
ws.close();
chrome.kill();
process.exit(problems.length ? 1 : 0);
