import random

import cv2
import numpy as np

from config import Config


def apply_prism(img, map_x, map_y):

    shift = random.uniform(1, 7)

    b, g, r = cv2.split(img)

    b = cv2.remap(b, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    # b = cv2.GaussianBlur(b, (3, 3), 0)

    g = cv2.remap(
        g, map_x + shift, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )
    # g = cv2.GaussianBlur(g, (3, 3), 0)
    r = cv2.remap(
        r, map_x - shift, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )
    r = cv2.GaussianBlur(r, (3, 3), 0)

    return cv2.merge([b, g, r])


def apply_ripple(img, map_x, map_y):

    h, w = img.shape[:2]

    xx, yy = np.meshgrid(np.arange(w), np.arange(h))

    freq = random.uniform(0.01, 0.05)

    amp = random.uniform(0.5, 1.5)

    ripple_x = map_x + amp * np.sin(yy * freq)

    ripple_y = map_y + amp * np.cos(xx * freq)

    r = cv2.remap(
        img,
        ripple_x.astype(np.float32),
        ripple_y.astype(np.float32),
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    r = cv2.GaussianBlur(r, (3, 3), 0)

    return r


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

    r = cv2.remap(
        img,
        new_x.astype(np.float32),
        new_y.astype(np.float32),
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )

    r = cv2.GaussianBlur(r, (5, 5), 0)

    return r


def apply_crystal(img, map_x, map_y):

    jitter = 1

    jitter_x = map_x + np.random.uniform(-jitter, jitter, map_x.shape)

    jitter_y = map_y + np.random.uniform(-jitter, jitter, map_y.shape)

    return cv2.remap(
        img,
        jitter_x.astype(np.float32),
        jitter_y.astype(np.float32),
        cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_REPLICATE,
    )


def apply_hazy(img):

    blur = cv2.GaussianBlur(img, (9, 9), 0)

    return cv2.addWeighted(img, 0.6, blur, 0.4, 0)


def apply_ice(img):

    h, w = img.shape[:2]

    noise = np.random.randn(h, w).astype(np.float32)

    noise = cv2.GaussianBlur(noise, (5, 5), 0)

    noise = cv2.GaussianBlur(noise, (1, 1), 0)

    map_x = np.tile(np.arange(w), (h, 1)).astype(np.float32)

    map_y = np.tile(np.arange(h).reshape(-1, 1), (1, w)).astype(np.float32)

    map_x += noise * 1.3

    map_y += noise * 1.3
    r = cv2.remap(
        img, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )

    r = cv2.GaussianBlur(r, (13, 1), 0)
    # if random.random() < 0.5:
    #     r = cv2.GaussianBlur(r, (3, 27), 0)
    # else    :
    #     r = cv2.GaussianBlur(r, (27, 3), 0)

    return r


def apply_frosted(img):

    k = random.choice(Config.FROSTED_KERNEL_CHOICES)

    return cv2.GaussianBlur(img, (k, k), 0)


def apply_directional_frost(img, ksize=25):
    #Gargabe dont use this, it looks bad
    kernel = np.zeros((ksize, ksize))
    kernel[ksize // 2, :] = np.ones(ksize)
    kernel /= ksize

    blurred = cv2.filter2D(img, -1, kernel)

    return cv2.addWeighted(img, 0.4, blurred, 0.6, 0)


def apply_chromatic_glass(img, map_x, map_y):
    h, w = img.shape[:2]
    cx, cy = w // 2, h // 2

    dx = map_x - cx
    dy = map_y - cy
    r = np.sqrt(dx**2 + dy**2).astype(np.float32)

    shift = (r * 0.05 + 1.0).astype(np.float32)
    # shift = (r * 0.002).astype(np.float32)
    b, g, rch = cv2.split(img)

    b = cv2.remap(
        b,
        (map_x - shift).astype(np.float32),
        map_y,
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    g = cv2.remap(
        g,
        map_x,
        map_y,
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    rch = cv2.remap(
        rch,
        (map_x + shift).astype(np.float32),
        map_y,
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )

    return cv2.merge([b, g, rch])


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

    match mode:
        case "frosted":
            return apply_frosted(img)

        case "clear":
            return apply_clear(img, map_x, map_y)

        case "chromatic":
            return apply_chromatic_glass(img, map_x, map_y)

        case "prism":
            return apply_prism(img, map_x, map_y)

        case "ripple":
            return apply_ripple(img, map_x, map_y)

        case "magnify":
            return apply_magnify(img, map_x, map_y)

        case "crystal":
            return apply_crystal(img, map_x, map_y)

        case "ice":
            return apply_ice(img)

        case "hazy":
            return apply_hazy(img)

        case "glossy":
            return apply_glossy(img)

        case _:
            raise ValueError(f"Unknown mode: {mode}")
