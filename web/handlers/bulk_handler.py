import os
import cv2
import logging

from utils.detect import detect_faces
from utils.face import stylized_face_glass

logger = logging.getLogger("face_glitch_mob_web_bulk")


def process_web_bulk(
    input_dir,
    output_dir,
    style,
    grid_size,
    distortion_min,
    distortion_max,
    noise_factor,
    feather_edges,
    face_scale,
    detect_scale,
    detect_neighbors,
    detect_threshold
):
    if not input_dir or not output_dir:
        return "Error: Please specify both input and output directory paths."

    if not os.path.isdir(input_dir):
        return f"Error: Input directory does not exist: {input_dir}"
    if os.path.realpath(input_dir) == os.path.realpath(output_dir):
        return "Error: Output directory must differ from the input, or the originals would be overwritten."

    os.makedirs(output_dir, exist_ok=True)
    supported_extensions = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
    files = sorted(f for f in os.listdir(input_dir) if f.lower().endswith(supported_extensions))
    if not files:
        return f"Warning: No compatible image files found in '{input_dir}'."

    style_val = None if style == "random" else style
    success_count = 0
    total_faces = 0
    failures = []

    for filename in files:
        try:
            img = cv2.imread(os.path.join(input_dir, filename))
            if img is None:
                failures.append(f"{filename}: not a readable image")
                continue
            boxes = detect_faces(img, detect_scale, detect_neighbors, detect_threshold, face_scale)
            for box in boxes:
                img = stylized_face_glass(
                    img,
                    box,
                    grid_size=int(grid_size),
                    style=style_val,
                    feather_edges=feather_edges,
                    distortion=(float(distortion_min), float(distortion_max)),
                    noise=float(noise_factor),
                )
            cv2.imwrite(os.path.join(output_dir, filename), img)
            success_count += 1
            total_faces += len(boxes)
        except Exception as e:
            logger.error(f"Batch failed on {filename}: {e}")
            failures.append(f"{filename}: {e}")

    report = f"Processed {success_count}/{len(files)} images and stylized {total_faces} faces.\nOutputs saved to: {output_dir}"
    if failures:
        report += "\nSkipped:\n" + "\n".join(failures)
    return report
