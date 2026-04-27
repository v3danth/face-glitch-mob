import cv2

from config import Config
from utils.face import stylized_face_glass


def main():
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + Config.FACE_CASCADE_PATH
    )
    image = cv2.imread(Config.INPUT_IMAGE)
    image = cv2.resize(
        image, None, fx=Config.FACE_SCALE_FACTOR, fy=Config.FACE_SCALE_FACTOR
    )
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces, _, weights = face_cascade.detectMultiScale3(
        gray,
        Config.FACE_DETECT_SCALE,
        Config.FACE_DETECT_MIN_NEIGHBORS,
        outputRejectLevels=True,
    )
    for (x, y, w, h), weight in zip(faces, weights):
        if weight > Config.FACE_DETECT_WEIGHT_THRESHOLD:
            image = stylized_face_glass(image, (x, y, w, h), Config.GRID_SIZE)
    # cv2.imshow("Result", image)
    # cv2.waitKey(0)
    cv2.imwrite(Config.OUTPUT_PATH, image)


if __name__ == "__main__":

    main()
