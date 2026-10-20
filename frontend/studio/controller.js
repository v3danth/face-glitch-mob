/**
 * @fileoverview The Studio's behaviour without the DOM: photo and render
 * machines, the model, and the async upload/render flows. The network and
 * drawing are injected, so simulated users can drive it in Node with a fake
 * server that is slow, fails or evicts photos (controller.test.js).
 */

import {createMachine} from '../shared/machine.js';
import {
  DEFAULT_BRUSH, DEFAULT_SETTINGS, PHOTO_TABLE, RENDER_TABLE, applyPreset, cellAt, emptyLayout,
  layoutForGrid, normalizeBrush, normalizeSettings, paintAll, renderRequest, toggleCell,
} from '../shared/model.js';

/** Unpainted cells use the random mix with clear glass. */
export const BASE_STYLE = normalizeBrush({material: 'random', tint: {mode: 'none'}});

export const MIN_FACE_BOX = 12;

/** Thrown by api.render when the server no longer has the photo. */
export class PhotoExpired extends Error {}

/**
 * @param {{
 *   api: {upload: function(*): !Promise<!Object>, render: function(!Object): !Promise<!Object>},
 *   decode: function(*): !Promise<*>,
 *   view: {
 *     photoLoaded: function(*, !Object): void,
 *     drawResult: function(!Array<!Object>, !Object): !Promise<void>,
 *     changed: function(): void,
 *   },
 *   onRefused: (function(string, string, string): void)|undefined,
 * }} deps
 */
export function createStudio({api, decode, view, onRefused}) {
  const hooks = {onRefused, onChange: () => view.changed()};
  const photo = createMachine('photo', PHOTO_TABLE, 'empty', hooks);
  const render = createMachine('render', RENDER_TABLE, 'idle', {onRefused});

  const app = {
    file: null,
    token: 0,
    photoId: null,
    image: null,
    faces: [],
    settings: normalizeSettings(DEFAULT_SETTINGS),
    brush: normalizeBrush(DEFAULT_BRUSH),
    layout: emptyLayout(DEFAULT_SETTINGS.grid),
    rendered: false,
    lastRender: null,
    message: '',
  };

  async function choosePhoto(file) {
    photo.send('choose');
    const token = ++app.token;
    Object.assign(app, {file, photoId: null, faces: [], rendered: false, layout: emptyLayout(app.settings.grid)});
    view.changed();
    try {
      const [image, body] = await Promise.all([decode(file), api.upload(file)]);
      if (token !== app.token) return;
      Object.assign(app, {image, photoId: body.id, faces: body.faces});
      view.photoLoaded(image, body);
      photo.send(body.faces.length ? 'found' : 'none');
      requestRender();
    } catch (error) {
      if (token !== app.token) return;
      app.message = error.message;
      photo.send('fail');
    }
  }

  /**
   * The server evicted the photo: upload the file again and carry on. If
   * the user already chose another photo, that upload supersedes this one.
   */
  async function reupload() {
    if (!photo.can('expire')) return;
    photo.send('expire');
    const token = ++app.token;
    try {
      const body = await api.upload(app.file);
      if (token !== app.token) return;
      app.photoId = body.id;
      photo.send('found');
      requestRender();
    } catch (error) {
      if (token !== app.token) return;
      app.message = error.message;
      photo.send('fail');
    }
  }

  function currentRequest() {
    return {photo: app.photoId, faces: app.faces, ...renderRequest(app.settings, app.layout, BASE_STYLE)};
  }

  function requestRender() {
    if (photo.state !== 'ready') return;
    const before = render.state;
    render.send('request');
    if (before === 'idle' || before === 'failed') startRender();
  }

  async function startRender() {
    if (photo.state !== 'ready') {
      render.sync('idle');
      return;
    }
    const token = app.token;
    const body = currentRequest();
    try {
      const result = await api.render(body);
      if (token === app.token) {
        await view.drawResult(result.patches, result);
        app.rendered = true;
        app.lastRender = {token, body};
      }
      render.send('done');
    } catch (error) {
      if (error instanceof PhotoExpired) {
        render.sync('idle');
        reupload();
        return;
      }
      app.message = `Render failed: ${error.message}`;
      render.send('fail');
    }
    view.changed();
    if (render.state === 'busy') startRender();
  }

  function editLayout(change) {
    if (photo.state !== 'ready') return;
    app.layout = change(app.layout);
    view.changed();
    requestRender();
  }

  return {
    photo,
    render,
    app,
    choosePhoto,
    requestRender,
    currentRequest,
    setSettings(raw) {
      app.settings = normalizeSettings(raw);
      app.layout = layoutForGrid(app.layout, app.settings.grid);
      view.changed();
      requestRender();
    },
    setBrush(raw) {
      app.brush = normalizeBrush(raw);
      view.changed();
    },
    /** Paints the board cell under (x, y); returns whether a cell was hit. */
    clickBoard(x, y) {
      const hit = photo.state === 'ready' ? cellAt(app.faces, app.layout.grid, x, y) : null;
      if (hit) editLayout((layout) => toggleCell(layout, hit, app.brush));
      return Boolean(hit);
    },
    applyPreset(name) {
      if (photo.state !== 'ready') return;
      ({settings: app.settings, brush: app.brush, layout: app.layout} = applyPreset(name, app.settings, app.faces.length));
      view.changed();
      requestRender();
    },
    paintAll() {
      editLayout(() => paintAll(app.settings.grid, app.faces.length, app.brush));
    },
    clear() {
      editLayout(() => emptyLayout(app.settings.grid));
    },
    /** Adds a hand-drawn face box; returns false when it is too small. */
    addFace(box) {
      if (!photo.can('addFace')) return false;
      if (box.w < MIN_FACE_BOX || box.h < MIN_FACE_BOX) return false;
      app.faces = [...app.faces, box];
      photo.send('addFace');
      requestRender();
      return true;
    },
  };
}
