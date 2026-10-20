/**
 * @fileoverview In-browser face detection with MediaPipe Tasks Vision.
 *
 * The photo never leaves the page: the model and the WebAssembly runtime are
 * downloaded once, and detection runs locally. If they cannot load (offline,
 * blocked CDN) detection rejects and the user draws face boxes by hand.
 */

import {detectionWindows, mergeDetections, squareFaceBox} from './faces.js';

const TASKS_VISION = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14';
const MODEL = 'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite';

let detectorPromise = null;

function loadDetector() {
  detectorPromise ??= (async () => {
    const vision = await import(`${TASKS_VISION}/vision_bundle.mjs`);
    const files = await vision.FilesetResolver.forVisionTasks(`${TASKS_VISION}/wasm`);
    return vision.FaceDetector.createFromOptions(files, {
      baseOptions: {modelAssetPath: MODEL, delegate: 'CPU'},
      runningMode: 'IMAGE',
      // Real faces score above 0.9 on test photos; reflective clutter (lamps)
      // peaks near 0.6. Missed faces can always be marked by hand.
      minDetectionConfidence: 0.75,
    });
  })().catch((error) => {
    detectorPromise = null; // let a later photo retry
    throw error;
  });
  return detectorPromise;
}

/**
 * Square face boxes in photo pixels, found over several scales.
 * @param {!ImageBitmap} bitmap
 * @return {!Promise<!Array<{x: number, y: number, w: number, h: number}>>}
 */
export async function detectFaces(bitmap) {
  const detector = await loadDetector();
  const crop = new OffscreenCanvas(1, 1);
  const ctx = crop.getContext('2d');
  const found = [];
  for (const win of detectionWindows(bitmap.width, bitmap.height)) {
    // The detector sees a 128 px input; a 640 px crop keeps the cost flat.
    const scale = Math.min(640 / win.w, 1);
    crop.width = Math.round(win.w * scale);
    crop.height = Math.round(win.h * scale);
    ctx.drawImage(bitmap, win.x, win.y, win.w, win.h, 0, 0, crop.width, crop.height);
    for (const d of detector.detect(crop).detections) {
      const b = d.boundingBox;
      found.push({
        x: win.x + b.originX / scale,
        y: win.y + b.originY / scale,
        w: b.width / scale,
        h: b.height / scale,
        score: d.categories[0]?.score ?? 0,
      });
    }
  }
  return mergeDetections(found).map((box) => ({...squareFaceBox(box, bitmap.width, bitmap.height), score: box.score}));
}
