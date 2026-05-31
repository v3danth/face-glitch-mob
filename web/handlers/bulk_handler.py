import os
import cv2
import logging

from config import Config
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

    if not os.path.exists(input_dir):
        return f"Error: Input directory does not exist: {input_dir}"

    try:
        os.makedirs(output_dir, exist_ok=True)
        supported_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
        files = [f for f in os.listdir(input_dir) if f.lower().endswith(supported_extensions)]

        if not files:
            return f"Warning: No compatible image files found in '{input_dir}'."

        # Dynamically apply configs
        Config.DISTORTION_STRENGTH_MIN = float(distortion_min)
        Config.DISTORTION_STRENGTH_MAX = float(distortion_max)
        Config.NOISE_FACTOR = float(noise_factor)

        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + Config.FACE_CASCADE_PATH
        )

        style_val = None if style == "random" else style
        success_count = 0
        total_faces = 0

        for filename in files:
            in_path = os.path.join(input_dir, filename)
            out_path = os.path.join(output_dir, filename)

            img = cv2.imread(in_path)
            if img is None:
                continue

            if face_scale != 1.0:
                h, w = img.shape[:2]
                img = cv2.resize(img, (int(w * face_scale), int(h * face_scale)))

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces, _, weights = face_cascade.detectMultiScale3(
                gray,
                scaleFactor=float(detect_scale),
                minNeighbors=int(detect_neighbors),
                outputRejectLevels=True
            )

            faces_in_img = 0
            for (x, y, w, h), weight in zip(faces, weights):
                if weight > float(detect_threshold):
                    img = stylized_face_glass(
                        img,
                        (x, y, w, h),
                        grid_size=int(grid_size),
                        style=style_val,
                        feather_edges=feather_edges
                    )
                    faces_in_img += 1

            cv2.imwrite(out_path, img)
            success_count += 1
            total_faces += faces_in_img

        return f"Success: Processed {success_count}/{len(files)} images and stylized {total_faces} faces.\nOutputs saved to: {output_dir}"

    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")
        return f"Bulk processing error: {str(e)}"
