import os
import argparse
import logging
import cv2

from config import Config
from utils.detect import detect_faces
from utils.face import stylized_face_glass
from utils.materials import MATERIAL_NAMES

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("face_glitch_mob")


def get_mode_settings(mode: str):
    modes = {
        "low": {"grid": 4, "scale": 0.6},
        "medium": {"grid": 6, "scale": 0.5},
        "high": {"grid": 8, "scale": 0.4},
    }
    return modes.get(mode, modes["medium"])


def process_single_image(input_path: str, output_path: str, grid_size: int, scale: float, style: str, feather: bool, threshold: float, likeness: float, intensity: float) -> bool:
    logger.info(f"Processing image: {input_path}")
    image = cv2.imread(input_path)
    if image is None:
        logger.error(f"Could not load image: {input_path}")
        return False

    # Detect on a downscaled copy, render on the full-resolution photo.
    faces = detect_faces(
        image, Config.FACE_DETECT_SCALE, Config.FACE_DETECT_MIN_NEIGHBORS, threshold, scale
    )
    logger.info(f"Detected {len(faces)} face(s) in {input_path}")

    for box in faces:
        image = stylized_face_glass(
            image,
            box,
            grid_size=grid_size,
            style=style,
            feather_edges=feather,
            likeness=likeness,
            intensity=intensity,
        )

    logger.info(f"Applied glass glitch style '{style or 'random'}' to {len(faces)} verified face(s)")

    # Ensure output directory exists
    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    cv2.imwrite(output_path, image)
    logger.info(f"Saved output → {output_path}")
    return True


def process_bulk(input_dir: str, output_dir: str, grid_size: int, scale: float, style: str, feather: bool, threshold: float, likeness: float, intensity: float):
    if not os.path.exists(input_dir):
        logger.error(f"Input directory does not exist: {input_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)
    supported_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')

    files = [f for f in os.listdir(input_dir) if f.lower().endswith(supported_extensions)]
    if not files:
        logger.warning(f"No image files found in {input_dir}")
        return

    logger.info(f"Starting batch processing of {len(files)} image(s) in {input_dir}")
    success_count = 0

    for filename in files:
        in_path = os.path.join(input_dir, filename)
        out_path = os.path.join(output_dir, filename)
        try:
            if process_single_image(
                input_path=in_path,
                output_path=out_path,
                grid_size=grid_size,
                scale=scale,
                style=style,
                feather=feather,
                threshold=threshold,
                likeness=likeness,
                intensity=intensity,
            ):
                success_count += 1
        except Exception as e:
            logger.error(f"Failed to process {filename}: {str(e)}")

    logger.info(f"Batch processing completed! Successfully processed {success_count}/{len(files)} image(s)")


def main():
    parser = argparse.ArgumentParser(
        description="Face Glitch Mob CLI: Apply stylized glass privacy tiles to faces."
    )

    parser.add_argument("-i", "--input", required=True, help="Input image file or folder path")
    parser.add_argument("-o", "--output", required=True, help="Output image file or folder path")
    parser.add_argument(
        "-m", "--mode", default="medium", choices=["low", "medium", "high"],
        help="Preset mode determining default scale and grid size (default: medium)"
    )
    parser.add_argument(
        "-g", "--grid", type=int, default=None, help="Override tile grid size (number of tiles per side)"
    )
    parser.add_argument(
        "-s", "--style", default=None,
        choices=[*MATERIAL_NAMES, "random"],
        help="Specify a glass material style (default: random mixture)"
    )
    parser.add_argument(
        "--no-feather", action="store_false", dest="feather",
        help="Disable edge-feathering for glass tiles (hard rectangular tiles)"
    )
    parser.add_argument(
        "-t", "--threshold", type=float, default=None,
        help=f"Face detection confidence weight threshold (default: {Config.FACE_DETECT_WEIGHT_THRESHOLD})"
    )

    parser.add_argument(
        "-l", "--likeness", type=float, default=Config.LIKENESS,
        help=f"0-1: keep the face recognisable as a thumbnail but hidden when zoomed (default: {Config.LIKENESS})"
    )

    parser.add_argument(
        "--intensity", type=float, default=Config.INTENSITY,
        help=f"Glass blur and distortion strength; lower shows more of the face (default: {Config.INTENSITY})"
    )

    args = parser.parse_args()

    settings = get_mode_settings(args.mode)
    grid_size = args.grid or settings["grid"]
    scale = settings["scale"]
    style = None if args.style == "random" else args.style
    threshold = args.threshold if args.threshold is not None else Config.FACE_DETECT_WEIGHT_THRESHOLD

    # Determine if input is a directory or file
    if os.path.isdir(args.input):
        process_bulk(
            input_dir=args.input,
            output_dir=args.output,
            grid_size=grid_size,
            scale=scale,
            style=style,
            feather=args.feather,
            threshold=threshold,
            likeness=args.likeness,
            intensity=args.intensity,
        )
    else:
        process_single_image(
            input_path=args.input,
            output_path=args.output,
            grid_size=grid_size,
            scale=scale,
            style=style,
            feather=args.feather,
            threshold=threshold,
            likeness=args.likeness,
            intensity=args.intensity,
        )


if __name__ == "__main__":
    main()
