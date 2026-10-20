import cv2

from config import Config
from utils.detect import detect_faces
from utils.face import stylized_face_glass


def main():
    image = cv2.imread(Config.INPUT_IMAGE)
    faces = detect_faces(
        image,
        Config.FACE_DETECT_SCALE,
        Config.FACE_DETECT_MIN_NEIGHBORS,
        Config.FACE_DETECT_WEIGHT_THRESHOLD,
        Config.FACE_SCALE_FACTOR,
    )
    for box in faces:
        image = stylized_face_glass(image, box, Config.GRID_SIZE)
    cv2.imwrite(Config.OUTPUT_PATH, image)


if __name__ == "__main__":
    main()
