/**
 * @fileoverview Face boxes: squaring detector output, user-drawn boxes, and
 * the multi-scale search that lets a 128 px detector find small faces in a
 * 12 MP photo.
 */

/**
 * Turns a tight detector box (brows to chin) into the square box the Haar
 * detector and the tile grid expect: forehead and chin included.
 */
export function squareFaceBox(box, photoWidth, photoHeight) {
  const side = Math.round(Math.max(box.w, box.h) * 1.25);
  const size = Math.max(Math.min(side, photoWidth, photoHeight), 1);
  const cx = box.x + box.w / 2;
  const cy = box.y + box.h / 2 - 0.08 * box.h;
  const x = Math.round(Math.min(Math.max(cx - size / 2, 0), photoWidth - size));
  const y = Math.round(Math.min(Math.max(cy - size / 2, 0), photoHeight - size));
  return {x, y, w: size, h: size};
}

/** A box dragged by the user, ordered and clipped; null if too small. */
export function drawnFaceBox(a, b, photoWidth, photoHeight, minSize = 16) {
  const x0 = Math.max(Math.min(a.x, b.x), 0);
  const y0 = Math.max(Math.min(a.y, b.y), 0);
  const x1 = Math.min(Math.max(a.x, b.x), photoWidth);
  const y1 = Math.min(Math.max(a.y, b.y), photoHeight);
  const w = Math.round(x1 - x0);
  const h = Math.round(y1 - y0);
  if (w < minSize || h < minSize) return null;
  return {x: Math.round(x0), y: Math.round(y0), w, h};
}

/**
 * Square crops to run the detector on: the whole photo, then overlapping
 * windows of half and a quarter of the short side. The short-range model
 * sees a 128 px input, so a face must fill a good share of the crop.
 */
export function detectionWindows(width, height, minWindow = 256) {
  const windows = [{x: 0, y: 0, w: width, h: height}];
  const short = Math.min(width, height);
  for (const side of [Math.floor(short / 2), Math.floor(short / 4)]) {
    if (side < minWindow) break;
    const stride = Math.floor(side / 2);
    for (let y = 0; y < height; y += stride) {
      for (let x = 0; x < width; x += stride) {
        const wx = Math.min(x, width - side);
        const wy = Math.min(y, height - side);
        if (!windows.some((w) => w.x === wx && w.y === wy && w.w === side)) windows.push({x: wx, y: wy, w: side, h: side});
        if (x + side >= width) break;
      }
      if (y + side >= height) break;
    }
  }
  return windows;
}

function iou(a, b) {
  const x0 = Math.max(a.x, b.x);
  const y0 = Math.max(a.y, b.y);
  const x1 = Math.min(a.x + a.w, b.x + b.w);
  const y1 = Math.min(a.y + a.h, b.y + b.h);
  const inter = Math.max(x1 - x0, 0) * Math.max(y1 - y0, 0);
  return inter / (a.w * a.h + b.w * b.h - inter);
}

/**
 * Non-maximum suppression: the same face found in several windows keeps
 * its highest-scoring box. A box mostly inside a stronger one is also
 * dropped, since a crop can cut a face into a smaller partial detection.
 */
export function mergeDetections(detections, overlap = 0.3) {
  const kept = [];
  for (const d of [...detections].sort((a, b) => b.score - a.score)) {
    const covered = kept.some((k) => {
      const inter = iou(k, d) * (k.w * k.h + d.w * d.h) / (1 + iou(k, d));
      return iou(k, d) > overlap || inter > 0.6 * d.w * d.h;
    });
    if (!covered) kept.push(d);
  }
  return kept.sort((a, b) => a.x - b.x);
}
