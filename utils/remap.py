import cv2


def create_remap(xx, yy, dx, dy):

    map_x = (xx + dx).astype("float32")

    map_y = (yy + dy).astype("float32")

    return map_x, map_y


def remap_image(block, map_x, map_y):

    return cv2.remap(
        block,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )
