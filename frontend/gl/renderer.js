/**
 * @fileoverview WebGL2 pipeline that renders glass over every face at the
 * photo's full resolution.
 *
 * Per face: source (linear light) -> blur pyramid (cached while the face
 * region is unchanged) -> glass pass -> coarse blurs for the likeness band
 * swap -> composite into the canvas. Only the last three run on a slider
 * change, so drags stay interactive.
 */

import {LIKENESS_SIGMA} from './materials.js';
import * as shaders from './shaders.js';
import {TEXELS_PER_TILE, faceGeometry, packTiles, resolveTile, tileRandom} from './tiles.js';
import {cellKey} from '../shared/model.js';

const RANDOM_BASE = Object.freeze({material: 'random', tint: {mode: 'none', color: '#5aaaff', strength: 0}, angle: null});

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(`shader compile failed: ${gl.getShaderInfoLog(shader)}`);
  }
  return shader;
}

function program(gl, fragment) {
  const p = gl.createProgram();
  gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, shaders.VERTEX));
  gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, fragment));
  gl.bindAttribLocation(p, 0, 'aPos');
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(`link failed: ${gl.getProgramInfoLog(p)}`);
  const uniforms = {};
  const count = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < count; i++) {
    const name = gl.getActiveUniform(p, i).name.replace(/\[0\]$/, '');
    uniforms[name] = gl.getUniformLocation(p, name);
  }
  return {p, u: uniforms};
}

export class GlassRenderer {
  /** @param {!HTMLCanvasElement} canvas */
  constructor(canvas) {
    const gl = canvas.getContext('webgl2', {preserveDrawingBuffer: true, antialias: false, premultipliedAlpha: false});
    if (!gl) throw new Error('WebGL2 is not available in this browser');
    this.gl = gl;
    this.canvas = canvas;
    // Float targets keep blurs and the likeness band swap free of banding.
    this.floatTargets = Boolean(gl.getExtension('EXT_color_buffer_float'));
    gl.getExtension('OES_texture_float_linear');
    this.programs = {
      copy: program(gl, shaders.COPY_PHOTO),
      source: program(gl, shaders.SOURCE),
      blur: program(gl, shaders.BLUR),
      glass: program(gl, shaders.GLASS),
      composite: program(gl, shaders.COMPOSITE),
    };
    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    this.photo = null;
    this.faceCache = new Map();
    this.tileTexture = gl.createTexture();
  }

  /** @param {!ImageBitmap} bitmap */
  setPhoto(bitmap) {
    const gl = this.gl;
    const max = gl.getParameter(gl.MAX_TEXTURE_SIZE);
    if (bitmap.width > max || bitmap.height > max) {
      throw new Error(`photo is ${bitmap.width}x${bitmap.height}; this GPU handles up to ${max}px per side`);
    }
    this.clearFaces();
    if (this.photo) gl.deleteTexture(this.photo.texture);
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, bitmap);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    this.photo = {texture, width: bitmap.width, height: bitmap.height};
    this.canvas.width = bitmap.width;
    this.canvas.height = bitmap.height;
  }

  clearPhoto() {
    this.clearFaces();
    if (this.photo) this.gl.deleteTexture(this.photo.texture);
    this.photo = null;
  }

  clearFaces() {
    for (const entry of this.faceCache.values()) this.release(entry);
    this.faceCache.clear();
  }

  target(w, h) {
    const gl = this.gl;
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    if (this.floatTargets) {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
    } else {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    }
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    // Mirrored edges match cv2.BORDER_REFLECT in the Python renderer.
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.MIRRORED_REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.MIRRORED_REPEAT);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    return {tex, fbo, w, h};
  }

  release(entry) {
    const gl = this.gl;
    for (const t of [entry.source, ...entry.levels.slice(1), entry.tmp, entry.glass, entry.coarseSource, entry.coarseGlass]) {
      gl.deleteTexture(t.tex);
      gl.deleteFramebuffer(t.fbo);
    }
  }

  draw(target, prog, bind) {
    const gl = this.gl;
    gl.bindFramebuffer(gl.FRAMEBUFFER, target ? target.fbo : null);
    if (target) gl.viewport(0, 0, target.w, target.h);
    gl.useProgram(prog.p);
    bind(prog.u);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  texture(unit, tex) {
    const gl = this.gl;
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, tex);
    return unit;
  }

  blur(from, to, tmp, sigma) {
    const gl = this.gl;
    for (const [src, dst, dir] of [[from, tmp, [1, 0]], [tmp, to, [0, 1]]]) {
      this.draw(dst, this.programs.blur, (u) => {
        gl.uniform1i(u.uTex, this.texture(0, src.tex));
        gl.uniform2f(u.uSize, dst.w, dst.h);
        gl.uniform2f(u.uDir, ...dir);
        gl.uniform1f(u.uSigma, sigma);
      });
    }
  }

  /** Source, pyramid and coarse source for a face region; cached by region. */
  faceResources(index, geometry) {
    const {region, tile} = geometry;
    const key = `${region.x},${region.y},${region.w},${region.h},${tile.toFixed(3)}`;
    const cached = this.faceCache.get(index);
    if (cached?.key === key) return cached;
    if (cached) this.release(cached);

    const gl = this.gl;
    const make = () => this.target(region.w, region.h);
    const source = make();
    this.draw(source, this.programs.source, (u) => {
      gl.uniform1i(u.uPhoto, this.texture(0, this.photo.texture));
      gl.uniform2i(u.uOrigin, region.x, region.y);
    });
    const tmp = make();
    const levels = [source];
    for (const sigma of shaders.PYRAMID_SIGMAS.slice(1)) {
      const level = make();
      this.blur(source, level, tmp, sigma);
      levels.push(level);
    }
    const coarseSource = make();
    this.blur(source, coarseSource, tmp, LIKENESS_SIGMA * tile);
    const entry = {key, source, levels, tmp, coarseSource, glass: make(), coarseGlass: make()};
    this.faceCache.set(index, entry);
    return entry;
  }

  /** Every tile of one face, resolved and packed into the tile texture. */
  uploadTiles(faceIndex, settings, layout) {
    const gl = this.gl;
    const tiles = [];
    for (let row = 0; row < settings.grid; row++) {
      for (let col = 0; col < settings.grid; col++) {
        const style = layout.cells[cellKey(faceIndex, row, col)] ?? RANDOM_BASE;
        tiles.push(resolveTile(style, settings, tileRandom(settings.seed, faceIndex, row, col)));
      }
    }
    gl.bindTexture(gl.TEXTURE_2D, this.tileTexture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, TEXELS_PER_TILE, tiles.length, 0, gl.RGBA, gl.FLOAT, packTiles(tiles, settings));
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  }

  /**
   * Draws the photo and glass over every face into the canvas.
   * @param {!Array<{x: number, y: number, w: number, h: number}>} faces
   * @param {!Object} settings normalized settings
   * @param {{grid: number, cells: !Object}} layout on settings.grid
   */
  render(faces, settings, layout) {
    const gl = this.gl;
    if (!this.photo) return;
    const {width, height} = this.photo;
    gl.disable(gl.SCISSOR_TEST);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, width, height);
    this.draw(null, this.programs.copy, (u) => {
      gl.uniform1i(u.uPhoto, this.texture(0, this.photo.texture));
      gl.uniform1f(u.uHeight, height);
    });

    faces.forEach((box, index) => {
      const geometry = faceGeometry(box, settings, width, height);
      const res = this.faceResources(index, geometry);
      const {region, face, margin, xs, ys} = geometry;
      this.uploadTiles(index, settings, layout);

      this.draw(res.glass, this.programs.glass, (u) => {
        res.levels.forEach((level, i) => gl.uniform1i(u[`uL${i}`], this.texture(i, level.tex)));
        gl.uniform1i(u.uTiles, this.texture(9, this.tileTexture));
        gl.uniform2f(u.uRegion, region.w, region.h);
        gl.uniform1i(u.uGrid, settings.grid);
        gl.uniform1fv(u.uXs, padEdges(xs));
        gl.uniform1fv(u.uYs, padEdges(ys));
        gl.uniform1f(u.uMargin, margin);
        gl.uniform1f(u.uNoise, settings.noise);
        gl.uniform1f(u.uIntensity, settings.intensity);
      });
      this.blur(res.glass, res.coarseGlass, res.tmp, LIKENESS_SIGMA * geometry.tile);

      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, width, height);
      gl.enable(gl.SCISSOR_TEST);
      gl.scissor(region.x, height - region.y - region.h, region.w, region.h);
      this.draw(null, this.programs.composite, (u) => {
        gl.uniform1i(u.uSource, this.texture(0, res.source.tex));
        gl.uniform1i(u.uGlass, this.texture(1, res.glass.tex));
        gl.uniform1i(u.uCoarseSource, this.texture(2, res.coarseSource.tex));
        gl.uniform1i(u.uCoarseGlass, this.texture(3, res.coarseGlass.tex));
        gl.uniform2f(u.uRegion, region.w, region.h);
        gl.uniform4f(u.uRegionRect, region.x, region.y, region.w, region.h);
        gl.uniform4f(u.uFace, face.x, face.y, face.w, face.h);
        gl.uniform1f(u.uMargin, margin);
        gl.uniform1f(u.uLikeness, settings.likeness);
        gl.uniform1f(u.uHeight, height);
      });
      gl.disable(gl.SCISSOR_TEST);
    });
    // Faces removed since the last frame free their textures.
    for (const index of [...this.faceCache.keys()]) {
      if (index >= faces.length) {
        this.release(this.faceCache.get(index));
        this.faceCache.delete(index);
      }
    }
  }

  /** Blocks until the GPU has finished, so timings measure real work. */
  finish() {
    const pixel = new Uint8Array(4);
    this.gl.readPixels(0, 0, 1, 1, this.gl.RGBA, this.gl.UNSIGNED_BYTE, pixel);
  }
}

/** Edge arrays are fixed-size uniforms (grid <= 12, so 13 edges). */
function padEdges(edges) {
  const out = new Float32Array(13);
  out.set(edges.slice(0, 13));
  for (let i = edges.length; i < 13; i++) out[i] = edges[edges.length - 1];
  return out;
}
