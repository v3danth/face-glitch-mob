import logging
import cv2
import numpy as np

from config import Config
from utils.face import stylized_face_glass

logger = logging.getLogger("face_glitch_mob_web_image")


def process_web_image(
    input_image,
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
    if input_image is None:
        return None, "Please upload an image first."

    try:
        # Convert Gradio PIL/RGB Image to OpenCV BGR
        img_bgr = cv2.cvtColor(np.array(input_image), cv2.COLOR_RGB2BGR)

        # Scale down before processing if requested
        if face_scale != 1.0:
            h, w = img_bgr.shape[:2]
            new_w = int(w * face_scale)
            new_h = int(h * face_scale)
            img_bgr = cv2.resize(img_bgr, (new_w, new_h))

        # Dynamically set temporary configs for distortion function calls
        Config.DISTORTION_STRENGTH_MIN = float(distortion_min)
        Config.DISTORTION_STRENGTH_MAX = float(distortion_max)
        Config.NOISE_FACTOR = float(noise_factor)

        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + Config.FACE_CASCADE_PATH
        )

        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        faces, _, weights = face_cascade.detectMultiScale3(
            gray,
            scaleFactor=float(detect_scale),
            minNeighbors=int(detect_neighbors),
            outputRejectLevels=True
        )

        logger.info(f"Detected {len(faces)} face candidate(s).")
        style_val = None if style == "random" else style
        processed_count = 0

        output_img = img_bgr.copy()
        for (x, y, w, h), weight in zip(faces, weights):
            if weight > float(detect_threshold):
                output_img = stylized_face_glass(
                    output_img,
                    (x, y, w, h),
                    grid_size=int(grid_size),
                    style=style_val,
                    feather_edges=feather_edges
                )
                processed_count += 1

        # Convert back to RGB for Gradio UI display
        output_rgb = cv2.cvtColor(output_img, cv2.COLOR_BGR2RGB)

        if processed_count > 0:
            status_msg = f"Glitch complete: Obscured {processed_count} face(s) using style '{style}'."
        else:
            status_msg = "Warning: No faces met the verification threshold. Try reducing 'Verification Threshold' or 'Min Neighbors'."

        return output_rgb, status_msg

    except Exception as e:
        logger.error(f"Error in web processing: {str(e)}")
        return None, f"Error: {str(e)}"
