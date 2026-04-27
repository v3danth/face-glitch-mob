import random

import cv2
import numpy as np

from config import Config


def apply_prism(img, map_x, map_y):

    shift = random.uniform(1, 3)

    b, g, r = cv2.split(img)

    b = cv2.remap(b, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    g = cv2.remap(
        g, map_x + shift, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
    )
    r = cv2.remap(
        r, map_x - shift, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
    )

    return cv2.merge([b, g, r])


def apply_ripple(img, map_x, map_y):

    h, w = img.shape[:2]

    xx, yy = np.meshgrid(np.arange(w), np.arange(h))

    freq = random.uniform(0.05, 0.15)

    amp = random.uniform(1, 3)

    ripple_x = map_x + amp * np.sin(yy * freq)

    ripple_y = map_y + amp * np.cos(xx * freq)

    return cv2.remap(
        img,
        ripple_x.astype(np.float32),
        ripple_y.astype(np.float32),
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )


def apply_magnify(img, map_x, map_y):

    h, w = img.shape[:2]

    cx, cy = w // 2, h // 2

    dx = map_x - cx

    dy = map_y - cy

    r = np.sqrt(dx**2 + dy**2)

    sigma = min(h, w) / 3

    factor = 1 + 0.3 * np.exp(-(r**2) / (2 * sigma**2))

    new_x = cx + dx / factor

    new_y = cy + dy / factor

    return cv2.remap(
        img,
        new_x.astype(np.float32),
        new_y.astype(np.float32),
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )


def apply_crystal(img, map_x, map_y):

    jitter = 3

    jitter_x = map_x + np.random.uniform(-jitter, jitter, map_x.shape)

    jitter_y = map_y + np.random.uniform(-jitter, jitter, map_y.shape)

    return cv2.remap(
        img,
        jitter_x.astype(np.float32),
        jitter_y.astype(np.float32),
        cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_REFLECT,
    )


def apply_hazy(img):

    blur = cv2.GaussianBlur(img, (25, 25), 0)

    return cv2.addWeighted(img, 0.6, blur, 0.4, 0)


def apply_ice(img):

    h, w = img.shape[:2]

    noise = np.random.randn(h, w).astype(np.float32)

    noise = cv2.GaussianBlur(noise, (9, 9), 0)

    map_x = np.tile(np.arange(w), (h, 1)).astype(np.float32)

    map_y = np.tile(np.arange(h).reshape(-1, 1), (1, w)).astype(np.float32)

    map_x += noise * 5

    map_y += noise * 5

    return cv2.remap(
        img, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
    )


def apply_frosted(img):

    k = random.choice(Config.FROSTED_KERNEL_CHOICES)

    return cv2.GaussianBlur(img, (k, k), 0)


def apply_clear(img, map_x, map_y):

    b, g, r = cv2.split(img)

    # adds color distortion to the image to simulate clear glass
    # without colour distortion, the image looks more like a frosted glass effect
    # without colour is better

    # b = cv2.remap(b, map_x, map_y, cv2.INTER_LINEAR)
    # g = cv2.remap(g, map_x, map_y, cv2.INTER_LINEAR)
    # r = cv2.remap(r, map_x, map_y, cv2.INTER_LINEAR)

    # rand_no = random.random()
    # if rand_no < 0.3:
    #     r = cv2.remap(r, map_x + 2, map_y, cv2.INTER_LINEAR)
    # elif rand_no < 0.6:
    #     r = cv2.remap(r, map_x + 2, map_y, cv2.INTER_LINEAR)
    #     pass
    # else:
    #     # g = cv2.remap(g, map_x, map_y, cv2.INTER_LINEAR)
    #     pass

    merged = cv2.merge([b, g, r])

    return cv2.GaussianBlur(
        merged, (Config.CLEAR_BLUR_KERNEL, Config.CLEAR_BLUR_KERNEL), 0
    )


def create_highlight(h, w):

    highlight = np.zeros((h, w, 3), dtype=np.float32)

    cv2.line(highlight, (0, h // 2), (w, h // 2), (255, 255, 255), 1)

    return cv2.GaussianBlur(highlight, (15, 15), 0)


def apply_glossy(img):

    blurred = cv2.GaussianBlur(
        img, (Config.GLOSSY_BLUR_KERNEL, Config.GLOSSY_BLUR_KERNEL), 0
    )

    h, w = img.shape[:2]

    highlight = create_highlight(h, w)

    return cv2.addWeighted(
        blurred.astype(np.float32),
        Config.GLOSSY_WEIGHT,
        highlight,
        Config.HIGHLIGHT_WEIGHT,
        0,
    ).astype(np.uint8)


def apply_material(img, map_x, map_y, mode):

    if mode == "frosted":

        return apply_frosted(img)

    elif mode == "clear":

        return apply_clear(img, map_x, map_y)

    elif mode == "prism":

        return apply_prism(img, map_x, map_y)

    elif mode == "ripple":

        return apply_ripple(img, map_x, map_y)

    elif mode == "magnify":

        return apply_magnify(img, map_x, map_y)

    elif mode == "crystal":

        return apply_crystal(img, map_x, map_y)

    elif mode == "ice":

        return apply_ice(img)

    elif mode == "hazy":

        return apply_hazy(img)

    else:

        return apply_glossy(img)
