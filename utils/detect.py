import threading

import cv2

from config import Config

_local = threading.local()


def face_cascade():
    """
    This thread's Haar cascade, loaded once per thread.

    CascadeClassifier keeps per-call scratch data inside the object, so two
    threads sharing one corrupt each other (seen as a getScaleData assertion
    under concurrent uploads). One per thread keeps detections parallel.
    """
    cascade = getattr(_local, "cascade", None)
    if cascade is None:
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + Config.FACE_CASCADE_PATH)
        _local.cascade = cascade
    return cascade


def detect_faces(image_bgr, scale_factor, min_neighbors, threshold, working_scale=1.0):
    """
    Face boxes (x, y, w, h) whose detector confidence exceeds threshold.

    Detection runs on a copy resized by working_scale, which is faster and
    suits the cascade's window sizes, but the boxes come back in the
    original image's pixels so glass is rendered at full resolution.
    """
    full_h, full_w = image_bgr.shape[:2]
    working_scale = float(working_scale)
    if working_scale != 1.0:
        image_bgr = cv2.resize(
            image_bgr, None, fx=working_scale, fy=working_scale, interpolation=cv2.INTER_AREA
        )
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    boxes, _, weights = face_cascade().detectMultiScale3(
        gray,
        scaleFactor=float(scale_factor),
        minNeighbors=int(min_neighbors),
        outputRejectLevels=True,
    )
    return [
        clamp_box([v / working_scale for v in box], full_w, full_h)
        for box, weight in zip(boxes, weights)
        if weight > float(threshold)
    ]


def clamp_box(box, width, height):
    """Rounds a box to whole pixels that lie inside a width x height image."""
    x, y, w, h = (int(round(v)) for v in box)
    x, y = min(max(x, 0), width - 1), min(max(y, 0), height - 1)
    return x, y, max(min(w, width - x), 1), max(min(h, height - y), 1)


def overlap(a, b):
    """Intersection over union of two (x, y, w, h) boxes."""
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / (a[2] * a[3] + b[2] * b[3] - inter)


def detect_faces_multiscale(
    image_bgr, scale_factor, min_neighbors, threshold, long_sides=(600, 900, 1200), min_votes=2
):
    """
    Face boxes found consistently across several detection sizes.

    Haar confidence for one face swings wildly with scale (on a 12 MP test
    photo: 5.5 at 1000 px, missing at 1600 px, 6.0 at 2000 px), so a single
    size with a hard threshold misses real faces. Real faces recur at most
    sizes while false positives flicker, so boxes are clustered across sizes
    and kept when seen at least min_votes times with a best confidence above
    threshold. The kept box is the confidence-weighted mean of its cluster.
    Sizes 600/900/1200 found the face and rejected a lamp reflection that
    800-2000 accepted, in 0.4 s instead of 1.1 s on that photo.
    """
    height, width = image_bgr.shape[:2]
    clusters = []
    for side in sorted({min(s, max(height, width)) for s in long_sides}):
        scale = side / max(height, width)
        small = cv2.resize(image_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        boxes, _, weights = face_cascade().detectMultiScale3(
            gray, scaleFactor=float(scale_factor), minNeighbors=int(min_neighbors), outputRejectLevels=True
        )
        for box, weight in zip(boxes, weights):
            full = [v / scale for v in box]
            home = next((c for c in clusters if overlap(c["boxes"][0], full) > 0.4), None)
            if home is None:
                clusters.append({"boxes": [full], "weights": [float(weight)]})
            else:
                home["boxes"].append(full)
                home["weights"].append(float(weight))

    faces = []
    for cluster in clusters:
        if len(cluster["boxes"]) < min_votes or max(cluster["weights"]) <= float(threshold):
            continue
        total = sum(max(w, 1e-3) for w in cluster["weights"])
        mean = [
            sum(box[i] * max(w, 1e-3) for box, w in zip(cluster["boxes"], cluster["weights"])) / total
            for i in range(4)
        ]
        faces.append(clamp_box(mean, width, height))
    return sorted(faces, key=lambda f: (f[1], f[0]))
