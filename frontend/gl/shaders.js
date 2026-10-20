/**
 * @fileoverview GLSL ES 3.0 sources: a port of utils/optics.py,
 * utils/surfaces.py, utils/tints.py and the tile blending of utils/face.py.
 *
 * Conventions: every offscreen texture stores image rows top-down, so a
 * texel's row is the photo row (y grows downward, as in the Python code).
 * Only the final pass into the canvas flips rows. All light is linear
 * (sRGB ^ 2.2, matching utils/face.py).
 */

export const PYRAMID_SIGMAS = [0, 1, 2, 4, 8, 16, 32, 64, 128];

export const VERTEX = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

/** Copies the photo into the canvas unchanged (rows flipped for display). */
export const COPY_PHOTO = `#version 300 es
precision highp float;
uniform sampler2D uPhoto;
uniform float uHeight;
out vec4 outColor;
void main() {
  ivec2 p = ivec2(int(gl_FragCoord.x), int(uHeight - gl_FragCoord.y));
  outColor = vec4(texelFetch(uPhoto, p, 0).rgb, 1.0);
}
`;

/** Region of the photo -> linear light, rows top-down. */
export const SOURCE = `#version 300 es
precision highp float;
uniform sampler2D uPhoto;
uniform ivec2 uOrigin;
out vec4 outColor;
void main() {
  ivec2 p = uOrigin + ivec2(gl_FragCoord.xy);
  outColor = vec4(pow(texelFetch(uPhoto, p, 0).rgb, vec3(2.2)), 1.0);
}
`;

/**
 * One direction of a Gaussian blur. Taps are capped so cost stays bounded
 * for wide blurs; beyond 48 taps per side they are spread out and linear
 * filtering fills the gaps.
 */
export const BLUR = `#version 300 es
precision highp float;
uniform sampler2D uTex;
uniform vec2 uSize;
uniform vec2 uDir;
uniform float uSigma;
out vec4 outColor;
void main() {
  vec2 uv = gl_FragCoord.xy / uSize;
  if (uSigma < 0.3) { outColor = texture(uTex, uv); return; }
  int taps = int(min(ceil(3.0 * uSigma), 48.0));
  float step = 3.0 * uSigma / float(taps);
  vec4 sum = texture(uTex, uv);
  float total = 1.0;
  for (int i = 1; i <= 48; i++) {
    if (i > taps) break;
    float x = float(i) * step;
    float w = exp(-0.5 * x * x / (uSigma * uSigma));
    vec2 o = uDir * x / uSize;
    sum += w * (texture(uTex, uv + o) + texture(uTex, uv - o));
    total += 2.0 * w;
  }
  outColor = sum / total;
}
`;

/** The glass: every tile covering this pixel, shaded and cross-faded. */
export const GLASS = `#version 300 es
precision highp float;
precision highp int;
precision highp sampler2D;

uniform sampler2D uL0, uL1, uL2, uL3, uL4, uL5, uL6, uL7, uL8;
uniform sampler2D uTiles;
uniform vec2 uRegion;
uniform int uGrid;
uniform float uXs[13];
uniform float uYs[13];
uniform float uMargin;
uniform float uNoise;
uniform float uIntensity;

out vec4 outColor;

const float PI = 3.14159265;
const float NOISE_NORM = 5.66;        // 1 / std of gnoise, measured
const float SIGMAS[9] = float[9](0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0);
const vec3 LIGHT = vec3(-0.4479, -0.6470, 0.6172);  // utils/optics.py LIGHT_DIR
const float LIGHT_INTENSITY = 2.5;
const vec3 ENV_TINT = vec3(0.95, 0.98, 1.0);        // optics _ENV_TINT, as RGB
const vec3 CHANNEL_NM = vec3(610.0, 550.0, 465.0);
const float FILM_IOR = 1.9;
const float FILM_PEAK = 0.6;
const float BODY_SCATTER = 0.2;
const float BASE_SLAB = 0.15;
const float HAZE_SPREAD = 0.5;
const float BACKPLATE_SPREAD = 0.2;

uint pcg(uint v) {
  uint state = v * 747796405u + 2891336453u;
  uint word = ((state >> ((state >> 28u) + 4u)) ^ state) * 277803737u;
  return (word >> 22u) ^ word;
}
float rnd(uint a, uint b) { return float(pcg(a ^ pcg(b))) / 4294967296.0; }

vec2 grad2(vec2 p) {
  p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
  return -1.0 + 2.0 * fract(sin(p) * 43758.5453123);
}
float gnoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  return mix(mix(dot(grad2(i), f), dot(grad2(i + vec2(1, 0)), f - vec2(1, 0)), u.x),
             mix(dot(grad2(i + vec2(0, 1)), f - vec2(0, 1)), dot(grad2(i + vec2(1, 1)), f - vec2(1, 1)), u.x), u.y);
}
/** Unit-variance noise correlated over about sigma pixels, like smooth_noise. */
float smoothNoise(vec2 q, vec2 sigma, float seed) {
  return NOISE_NORM * gnoise(q / (4.0 * sigma) + vec2(mod(seed * 0.731, 97.0), mod(seed * 1.37, 89.0)));
}

vec3 level(int i, vec2 uv) {
  if (i == 0) return texture(uL0, uv).rgb;
  if (i == 1) return texture(uL1, uv).rgb;
  if (i == 2) return texture(uL2, uv).rgb;
  if (i == 3) return texture(uL3, uv).rgb;
  if (i == 4) return texture(uL4, uv).rgb;
  if (i == 5) return texture(uL5, uv).rgb;
  if (i == 6) return texture(uL6, uv).rgb;
  if (i == 7) return texture(uL7, uv).rgb;
  return texture(uL8, uv).rgb;
}
/** The photo seen through a surface that scatters by sigma pixels. */
vec3 scattered(vec2 p, float sigma) {
  vec2 uv = p / uRegion;
  sigma = clamp(sigma, 0.0, 128.0);
  int i = 0;
  for (int k = 1; k < 9; k++) if (sigma >= SIGMAS[k]) i = k;
  if (i == 8) return level(8, uv);
  float t = (sigma - SIGMAS[i]) / (SIGMAS[i + 1] - SIGMAS[i]);
  return mix(level(i, uv), level(i + 1, uv), t);
}

float pow4(float x) { x *= x; return x * x; }  // pow() is undefined for x < 0

vec4 tex(int tile, int k) { return texelFetch(uTiles, ivec2(k, tile), 0); }

float quarterRound(float d, float width) {
  float t = clamp(d / width, 0.0, 1.0);
  return sqrt(1.0 - (1.0 - t) * (1.0 - t));
}
float insetDistance(vec2 q, vec2 size, float radius) {
  float r = min(radius, min(size.x, size.y) * 0.5);
  vec2 d = abs(q - size * 0.5) - (size * 0.5 - r);
  return r - length(max(d, 0.0)) - min(max(d.x, d.y), 0.0);
}

/**
 * Height of the tile's top face at local pixel centre q (relative to the
 * thinnest point, approximately), and coverage for rounded tiles.
 * Mirrors utils/surfaces.py; slopes come from surfaceSlope().
 */
vec2 height(int id, vec2 q, vec2 size, float relief, float angle, float seed, float meanThick) {
  float s = min(size.x, size.y);
  vec2 idx = q - 0.5;                                  // numpy pixel index
  vec2 uv = -1.0 + 2.0 * idx / max(size - 1.0, vec2(1.0));
  if (id == 1) {                                       // cathedral
    float sigma = max(s / 5.0, 1.0);
    float h = 0.6 * sigma * relief * smoothNoise(q, vec2(sigma), seed);
    return vec2(max(h + meanThick * s * relief, 0.0), 1.0);
  }
  if (id == 2) {                                       // pillow
    float peak = 0.12 * s * relief;
    return vec2(peak * (1.0 - pow4(uv.x)) * (1.0 - pow4(uv.y)), 1.0);
  }
  if (id == 3) {                                       // ridges
    vec2 across = vec2(sin(angle), cos(angle));
    float period = max(s / 2.0, 3.0);
    return vec2(0.75 * relief * mod(dot(idx, across), period), 1.0);
  }
  if (id == 4) {                                       // waves
    uint u = uint(seed * 4096.0);
    vec2 c = vec2(-0.5 + 2.0 * rnd(u, 11u), -0.5 + 2.0 * rnd(u, 12u)) * size;
    float r = length(idx - c);
    float k = 2.0 * PI / max(s * 0.4, 2.0);
    float a = 0.7 * relief / k;
    float h = a * sin(k * r + 2.0 * PI * rnd(u, 13u)) * exp(-r / (2.0 * s));
    return vec2(max(h + meanThick * s * relief, 0.0), 1.0);
  }
  if (id == 5) {                                       // squircle lens
    float sag = 0.2 * s * relief;
    return vec2(sag * max(1.0 - sqrt(pow4(uv.x) + pow4(uv.y)), 0.0), 1.0);
  }
  if (id == 7) {                                       // streaks
    vec2 along = vec2(cos(angle), -sin(angle));
    vec2 across = vec2(sin(angle), cos(angle));
    vec2 rotated = vec2(dot(q, along), dot(q, across));
    float h = 0.9 * relief * smoothNoise(rotated, vec2(max(s / 2.5, 1.0), 0.9), seed);
    return vec2(max(h + meanThick * s * relief, 0.0), 1.0);
  }
  if (id == 8) {                                       // capsule (liquid glass)
    float d = insetDistance(q, size, 0.22 * s);
    float h = 0.2 * s * relief * quarterRound(d, max(0.24 * s, 1.5));
    return vec2(h, clamp(d + 0.5, 0.0, 1.0));
  }
  return vec2(0.0, 1.0);                               // etched: optically flat
}

/** Facets have exact per-cell slopes; returns (thickness, gx, gy). */
vec3 facets(vec2 q, vec2 size, float relief, float seed, float meanThick) {
  uint u = uint(seed * 4096.0);
  int count = 5 + int(rnd(u, 1u) * 5.0);
  vec2 idx = q - 0.5;
  float best = 1e9;
  int cell = 0;
  vec2 site = vec2(0.0);
  for (int i = 0; i < 9; i++) {
    if (i >= count) break;
    vec2 p = vec2(rnd(u, uint(20 + i)), rnd(u, uint(40 + i))) * size;
    float d = dot(idx - p, idx - p);
    if (d < best) { best = d; cell = i; site = p; }
  }
  float tilt = (0.25 + 0.4 * rnd(u, uint(60 + cell))) * relief;
  float a = 2.0 * PI * rnd(u, uint(80 + cell));
  vec2 g = tilt * vec2(cos(a), sin(a));
  float s = min(size.x, size.y);
  return vec3(max(dot(g, idx - site) + meanThick * s * relief, 0.0), g);
}

struct Surf { float thick; vec2 g; float cover; };

Surf surfaceAt(int id, vec2 q, vec2 size, float relief, float angle, float seed, float meanThick, float bumps) {
  Surf s;
  if (id == 6) {
    vec3 f = facets(q, size, relief, seed, meanThick);
    s.thick = f.x; s.g = f.yz; s.cover = 1.0;
  } else if (id == 3) {
    vec2 h = height(id, q, size, relief, angle, seed, meanThick);
    s.thick = h.x; s.g = 0.75 * relief * vec2(sin(angle), cos(angle)); s.cover = 1.0;
  } else {
    vec2 h = height(id, q, size, relief, angle, seed, meanThick);
    float hx = height(id, q + vec2(0.5, 0.0), size, relief, angle, seed, meanThick).x
             - height(id, q - vec2(0.5, 0.0), size, relief, angle, seed, meanThick).x;
    float hy = height(id, q + vec2(0.0, 0.5), size, relief, angle, seed, meanThick).x
             - height(id, q - vec2(0.0, 0.5), size, relief, angle, seed, meanThick).x;
    s.thick = h.x; s.g = vec2(hx, hy); s.cover = h.y;
  }
  if (bumps > 0.0) {                                   // manufacturing ripple
    float bx = smoothNoise(q + vec2(0.5, 0.0), vec2(1.5), seed + 7.0) - smoothNoise(q - vec2(0.5, 0.0), vec2(1.5), seed + 7.0);
    float by = smoothNoise(q + vec2(0.0, 0.5), vec2(1.5), seed + 7.0) - smoothNoise(q - vec2(0.0, 0.5), vec2(1.5), seed + 7.0);
    s.g += bumps * vec2(bx, by);
  }
  return s;
}

/** Snell's law for the view ray (0, 0, -1); offset on the photo, pixels. */
vec2 refractOffset(vec3 n, float depth, float ior) {
  float eta = 1.0 / ior;
  float k = 1.0 - eta * eta * (1.0 - n.z * n.z);
  float c = eta * n.z - sqrt(k);
  return c * n.xy * depth / (eta - c * n.z);
}
float fresnel(float c, float ior) {
  float r0 = (ior - 1.0) / (ior + 1.0);
  r0 *= r0;
  return r0 + (1.0 - r0) * pow(1.0 - c, 5.0);
}
vec3 environment(vec3 n) {
  float ry = 2.0 * n.z * n.y;
  float sky = clamp(0.5 - 0.6 * ry, 0.0, 1.0);
  return (0.12 + 0.85 * sky * sky) * ENV_TINT;
}
float specular(vec3 n, float alpha, float ior) {
  vec3 h = normalize(LIGHT + vec3(0.0, 0.0, 1.0));
  float ndh = clamp(dot(n, h), 0.0, 1.0);
  float a2 = alpha * alpha;
  float d = a2 / (PI * pow(ndh * ndh * (a2 - 1.0) + 1.0, 2.0));
  return dot(n, LIGHT) > 0.0 ? LIGHT_INTENSITY * d * fresnel(h.z, ior) / (4.0 * n.z) : 0.0;
}

vec3 transmitted(vec2 p, vec3 n, float depth, vec3 iors, float sigma) {
  return vec3(scattered(p + refractOffset(n, depth, iors.r), sigma).r,
              scattered(p + refractOffset(n, depth, iors.g), sigma).g,
              scattered(p + refractOffset(n, depth, iors.b), sigma).b);
}

/** One tile's light at region pixel p; ext is its extended rectangle. */
vec3 shadeTile(int tile, vec2 p, vec4 ext) {
  vec4 t0 = tex(tile, 0), t1 = tex(tile, 1), t2 = tex(tile, 2), t3 = tex(tile, 3), t4 = tex(tile, 4), t5 = tex(tile, 5);
  int id = int(t0.x + 0.5);
  float relief = t0.y, angle = t0.z, seed = t0.w;
  vec3 iors = t1.rgb;
  float iorD = t1.a, rough = t2.x, gloss = t2.y, haze = t2.z, gap = t2.w;
  vec3 absorption = t3.rgb;
  float bumps = t3.a * 0.15 * uNoise;
  int tintKind = int(t4.x + 0.5);
  float tintStrength = t4.y, meanPath = t4.z;
  float meanThick = max(meanPath - BASE_SLAB, 0.0) / max(relief, 1e-4);

  vec2 size = ext.zw - ext.xy;
  float s = min(size.x, size.y);
  vec2 q = p - ext.xy;

  Surf here = surfaceAt(id, q, size, relief, angle, seed, meanThick, bumps);
  Surf right = surfaceAt(id, q + vec2(1.0, 0.0), size, relief, angle, seed, meanThick, bumps);
  Surf down = surfaceAt(id, q + vec2(0.0, 1.0), size, relief, angle, seed, meanThick, bumps);

  vec3 n = normalize(vec3(-here.g, 1.0));
  float depth = here.thick + gap * s;
  vec3 light = transmitted(p, n, depth, iors, depth * tan(rough));
  if (haze > 0.0) {
    light = mix(light, transmitted(p, n, depth, iors, HAZE_SPREAD * uIntensity * s), haze);
  }

  // Pixel footprint widens the highlight (utils/optics.py filtered_roughness).
  vec2 dgx = vec2(right.g.x - here.g.x, down.g.x - here.g.x);
  vec2 dgy = vec2(right.g.y - here.g.y, down.g.y - here.g.y);
  float variance = 0.25 * (dot(dgx, dgx) + dot(dgy, dgy));
  float alpha = sqrt(gloss * gloss + min(2.0 * variance, 0.18));

  float path = here.thick + BASE_SLAB * s;
  vec3 coatT = vec3(1.0);
  vec3 coatR = vec3(0.0);
  if (tintKind == 1) {                                 // dyed glass
    vec3 target = 1.0 - tintStrength * (1.0 - t5.rgb);
    vec3 k = -log(clamp(target, 1e-3, 1.0)) / max(meanPath * s, 1e-3);
    coatT = exp(-k * path);
    coatR = BODY_SCATTER * tintStrength * t5.rgb;
  } else if (tintKind == 2) {                          // dichroic thin film
    float film = 575.0 + 325.0 * tanh(smoothNoise(q, vec2(max(s / 4.0, 1.0)), seed + 31.0));
    float sinT = sqrt(clamp(1.0 - n.z * n.z, 0.0, 1.0)) / FILM_IOR;
    float cosT = sqrt(1.0 - sinT * sinT);
    vec3 phase = 4.0 * PI * FILM_IOR * film * cosT / CHANNEL_NM;
    vec3 sn = sin(phase * 0.5);
    coatR = tintStrength * FILM_PEAK * sn * sn;
    coatT = 1.0 - coatR;
  } else if (tintKind == 3) {                          // pigment grains
    uvec2 ip = uvec2(p);
    uint u = uint(seed * 4096.0) ^ (ip.x * 73856093u) ^ (ip.y * 19349663u);
    coatT = 1.0 - tintStrength * vec3(rnd(u, 1u), rnd(u, 2u), rnd(u, 3u));
  }

  float F = fresnel(n.z, iorD);
  vec3 absorbed = exp(-path * absorption / s);
  vec3 color = (1.0 - F) * absorbed * coatT * light
             + (F + coatR) * environment(n)
             + specular(n, alpha, iorD);

  if (here.cover < 1.0) {                              // frosted backplate
    vec3 back = scattered(p, BACKPLATE_SPREAD * s);
    color = here.cover * color + (1.0 - here.cover) * coatT * back;
  }
  return color;
}

float smoothstep01(float t) { t = clamp(t, 0.0, 1.0); return t * t * (3.0 - 2.0 * t); }
float crossfade(float c, float a, float b) {
  if (uMargin <= 0.0) return (c >= a && c < b) ? 1.0 : 0.0;
  return smoothstep01((c - (a - uMargin)) / (2.0 * uMargin)) * smoothstep01(((b + uMargin) - c) / (2.0 * uMargin));
}

void main() {
  vec2 p = gl_FragCoord.xy;                            // region pixel centre
  int col = 0, row = 0;
  for (int i = 1; i < 13; i++) {
    if (i < uGrid && p.x >= uXs[i]) col = i;
    if (i < uGrid && p.y >= uYs[i]) row = i;
  }
  vec3 sum = vec3(0.0);
  float total = 0.0;
  for (int dr = -1; dr <= 1; dr++) {
    int r = row + dr;
    if (r < 0 || r >= uGrid) continue;
    float wy = crossfade(p.y, uYs[r], uYs[r + 1]);
    if (wy <= 0.0) continue;
    for (int dc = -1; dc <= 1; dc++) {
      int c = col + dc;
      if (c < 0 || c >= uGrid) continue;
      float w = wy * crossfade(p.x, uXs[c], uXs[c + 1]);
      if (w <= 0.0) continue;
      vec4 ext = vec4(max(uXs[c] - uMargin, 0.0), max(uYs[r] - uMargin, 0.0),
                      min(uXs[c + 1] + uMargin, uRegion.x), min(uYs[r + 1] + uMargin, uRegion.y));
      sum += w * shadeTile(r * uGrid + c, p, ext);
      total += w;
    }
  }
  outColor = total > 1e-6 ? vec4(sum / total, 1.0) : vec4(texture(uL0, p / uRegion).rgb, 1.0);
}
`;

/**
 * Likeness band swap, outer fade and sRGB encode, written into the canvas.
 * See utils/face.py keep_likeness and edge_fade.
 */
export const COMPOSITE = `#version 300 es
precision highp float;
uniform sampler2D uSource, uGlass, uCoarseSource, uCoarseGlass;
uniform vec2 uRegion;
uniform vec4 uRegionRect;     // x, y, w, h in photo pixels
uniform vec4 uFace;           // face box in region pixels
uniform float uMargin;
uniform float uLikeness;
uniform float uHeight;
out vec4 outColor;

float smoothstep01(float t) { t = clamp(t, 0.0, 1.0); return t * t * (3.0 - 2.0 * t); }
float edgeFade(float c, float a, float b) {
  if (uMargin <= 0.0) return (c >= a && c < b) ? 1.0 : 0.0;
  return smoothstep01((c - (a - uMargin)) / uMargin) * smoothstep01(((b + uMargin) - c) / uMargin);
}
void main() {
  vec2 photo = vec2(gl_FragCoord.x, uHeight - gl_FragCoord.y);
  vec2 p = photo - uRegionRect.xy;
  vec2 uv = p / uRegion;
  vec3 source = texture(uSource, uv).rgb;
  vec3 glass = texture(uGlass, uv).rgb
             + uLikeness * (texture(uCoarseSource, uv).rgb - texture(uCoarseGlass, uv).rgb);
  float inside = edgeFade(p.x, uFace.x, uFace.x + uFace.z) * edgeFade(p.y, uFace.y, uFace.y + uFace.w);
  vec3 color = mix(source, glass, inside);
  outColor = vec4(pow(clamp(color, 0.0, 1.0), vec3(1.0 / 2.2)), 1.0);
}
`;
