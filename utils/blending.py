import numpy as np


def create_fade_mask(height, width):

    mask = np.ones((height, width, 3), dtype=np.float32)

    fade = int(min(height, width) * 0.08)

    for k in range(fade):

        val = k / fade

        mask[k, :] *= val

        mask[-k - 1, :] *= val

        mask[:, k] *= val

        mask[:, -k - 1] *= val

    return mask


def blend(region, processed, mask):

    region = region.astype(np.float32)

    processed = processed.astype(np.float32)

    blended = region * (1 - mask) + processed * mask

    return blended.astype(np.uint8)
