"""Synthetic top-down roof photos for the coverage tests.

Generated rather than checked in, so the expected coverage of each image is known
exactly from how it was drawn. Mild sensor noise keeps the images from being
unrealistically clean.
"""

from __future__ import annotations

import numpy as np

IMAGE_SIZE_PX = 400
ROOF_START_PX, ROOF_END_PX = 100, 300
GRASS_BGR = (60, 140, 60)
BITUMEN_BGR = (70, 70, 70)
COATING_BGR = (245, 245, 245)
NOISE_STD = 4.0
NOISE_SEED = 11
SPECK_SIZE_PX = 12
SPECK_SPACING_PX = 24


def _scene(roof_bgr: tuple[int, int, int]) -> np.ndarray:
    image = np.zeros((IMAGE_SIZE_PX, IMAGE_SIZE_PX, 3), dtype=np.float32)
    image[:] = GRASS_BGR
    image[ROOF_START_PX:ROOF_END_PX, ROOF_START_PX:ROOF_END_PX] = roof_bgr
    return image


def _finish(image: np.ndarray, brightness: float = 1.0) -> np.ndarray:
    noise = np.random.default_rng(NOISE_SEED).normal(0, NOISE_STD, image.shape)
    return np.clip(image * brightness + noise, 0, 255).astype(np.uint8)


def fully_coated_roof(brightness: float = 1.0) -> np.ndarray:
    return _finish(_scene(COATING_BGR), brightness)


def half_coated_roof(brightness: float = 1.0) -> np.ndarray:
    image = _scene(BITUMEN_BGR)
    middle = (ROOF_START_PX + ROOF_END_PX) // 2
    image[ROOF_START_PX:ROOF_END_PX, ROOF_START_PX:middle] = COATING_BGR
    return _finish(image, brightness)


def uncoated_roof(brightness: float = 1.0) -> np.ndarray:
    return _finish(_scene(BITUMEN_BGR), brightness)


def speckled_roof() -> np.ndarray:
    """Coating applied in scattered dabs, the fragmented case."""
    image = _scene(BITUMEN_BGR)
    for row in range(ROOF_START_PX + 6, ROOF_END_PX - SPECK_SIZE_PX, SPECK_SPACING_PX):
        for col in range(ROOF_START_PX + 6, ROOF_END_PX - SPECK_SIZE_PX, SPECK_SPACING_PX):
            image[row : row + SPECK_SIZE_PX, col : col + SPECK_SIZE_PX] = COATING_BGR
    return _finish(image)


def flat_grey_photo() -> np.ndarray:
    image = np.full((IMAGE_SIZE_PX, IMAGE_SIZE_PX, 3), BITUMEN_BGR, dtype=np.float32)
    return _finish(image)


def roof_square_mask() -> np.ndarray:
    mask = np.zeros((IMAGE_SIZE_PX, IMAGE_SIZE_PX), dtype=np.uint8)
    mask[ROOF_START_PX:ROOF_END_PX, ROOF_START_PX:ROOF_END_PX] = 255
    return mask


def coated_half_mask() -> np.ndarray:
    mask = np.zeros((IMAGE_SIZE_PX, IMAGE_SIZE_PX), dtype=np.uint8)
    middle = (ROOF_START_PX + ROOF_END_PX) // 2
    mask[ROOF_START_PX:ROOF_END_PX, ROOF_START_PX:middle] = 255
    return mask
