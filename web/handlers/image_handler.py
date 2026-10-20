import logging
import cv2
import numpy as np

from utils.detect import detect_faces
from utils.face import stylized_face_glass
from utils.tiles import TileStyle
from utils.tints import Tint, parse_color

logger = logging.getLogger("face_glitch_mob_web_image")


def process_web_image(
    input_image,
    style,
    grid_size,
    distortion_min,
    distortion_max,
    noise_factor,
    feather_edges,
    likeness,
    intensity,
    tint_mode,
    tint_color,
    tint_strength,
    face_scale,
    detect_scale,
    detect_neighbors,
    detect_threshold
):
    if input_image is None:
        return None, "Please upload an image first."

    try:
        # Gradio's Image preprocessing hands us RGB; convert defensively for
        # RGBA or greyscale uploads arriving through the API.
        img_bgr = cv2.cvtColor(np.array(input_image.convert("RGB")), cv2.COLOR_RGB2BGR)
        boxes = detect_faces(img_bgr, detect_scale, detect_neighbors, detect_threshold, face_scale)

        logger.info(f"Detected {len(boxes)} face(s).")
        style_val = TileStyle(
            material=None if style == "random" else style,
            tint=Tint(tint_mode, parse_color(tint_color), float(tint_strength)),
        )
        processed_count = 0

        output_img = img_bgr.copy()
        for box in boxes:
            output_img = stylized_face_glass(
                output_img,
                box,
                grid_size=int(grid_size),
                style=style_val,
                feather_edges=feather_edges,
                likeness=float(likeness),
                intensity=float(intensity),
                distortion=(float(distortion_min), float(distortion_max)),
                noise=float(noise_factor),
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
