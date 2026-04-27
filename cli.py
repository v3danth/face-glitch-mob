import argparse

import cv2

from config import Config
from utils.face import stylized_face_glass


def get_mode_settings(mode: str):
    modes = {
        "low": {"grid": 4, "scale": 0.6},
        "medium": {"grid": 6, "scale": 0.5},
        "high": {"grid": 8, "scale": 0.4},
    }
    return modes.get(mode, modes["medium"])


def process_image(input_path: str, output_path: str, mode: str, grid_override: int):
    settings = get_mode_settings(mode)

    grid_size = grid_override or settings["grid"]
    scale = settings["scale"]

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + Config.FACE_CASCADE_PATH
    )

    image = cv2.imread(input_path)
    if image is None:
        raise ValueError(f"Could not load image: {input_path}")

    image = cv2.resize(image, None, fx=scale, fy=scale)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    faces, _, weights = face_cascade.detectMultiScale3(
        gray,
        Config.FACE_DETECT_SCALE,
        Config.FACE_DETECT_MIN_NEIGHBORS,
        outputRejectLevels=True,
    )

    print(f"[INFO] Faces detected: {len(faces)}")

    for (x, y, w, h), weight in zip(faces, weights):
        if weight > 0:
            image = stylized_face_glass(image, (x, y, w, h), grid_size)

    cv2.imwrite(output_path, image)
    print(f"[DONE] Saved output → {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Glass Face Privacy CLI")

    parser.add_argument("-i", "--input", required=True, help="Input image path")
    parser.add_argument("-o", "--output", required=True, help="Output image path")

    parser.add_argument(
        "-m", "--mode", default="medium", choices=["low", "medium", "high"]
    )

    parser.add_argument(
        "-g", "--grid", type=int, default=None, help="Override grid size"
    )

    args = parser.parse_args()

    process_image(
        input_path=args.input,
        output_path=args.output,
        mode=args.mode,
        grid_override=args.grid,
    )


if __name__ == "__main__":
    main()
