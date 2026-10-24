"""Estimates how much of a roof the reflective coating actually covers, from one photo.

An invoice cannot show that a contractor painted only half the roof; the photo can.
Classic OpenCV only, no deep learning: the cues are simple (coating is bright and
nearly colourless) and every step stays explainable to an auditor.

Pipeline: HSV -> scene-adaptive Otsu threshold on value, gated by low saturation ->
morphological open/close -> intersect with the roof region (given mask, or the largest
connected component that differs from the surroundings) -> coverage percentage, plus
a confidence that drops for dark, flat or fragmented photos.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ml.config import load_ml_thresholds

_THRESHOLDS = load_ml_thresholds("coverage")

MAX_CHANNEL_VALUE = 255.0
# Saturation is largely independent of illumination, so a fixed gate is safe here,
# unlike a fixed brightness threshold. White and light-grey coatings stay below it.
MAX_COATING_SATURATION = _THRESHOLDS["max_coating_saturation"]
# Otsu always splits, even a uniform image; below this gap between the two class means
# the scene has no real bright/dark modes and the split would only cut sensor noise.
MIN_MODE_SEPARATION = _THRESHOLDS["min_mode_separation"]
# Used only when the scene has no contrast to adapt to; such photos also get low
# confidence, so this absolute fallback never decides a payout on its own.
UNIFORM_SCENE_MIN_COATING_VALUE = _THRESHOLDS["uniform_scene_min_coating_value"]

# Kernel scales with the photo so cleaning behaves the same at any resolution.
MORPH_KERNEL_FRACTION = _THRESHOLDS["morph_kernel_fraction"]
MIN_MORPH_KERNEL_PX = _THRESHOLDS["min_morph_kernel_px"]
# Frame width sampled to learn the surroundings' colour when no roof mask is given.
BORDER_FRACTION = _THRESHOLDS["border_fraction"]
# Lab distance from the surroundings beyond which a pixel belongs to the roof; Lab is
# perceptually uniform, so one distance means the same visible difference everywhere.
ROOF_COLOR_DISTANCE = _THRESHOLDS["roof_color_distance"]
# A smaller "roof" means the photo is cropped to the roof and the border is roof too.
MIN_ROOF_FRACTION = _THRESHOLDS["min_roof_fraction"]

MIN_MEAN_BRIGHTNESS = _THRESHOLDS["min_mean_brightness"]
MIN_CONTRAST_STD = _THRESHOLDS["min_contrast_std"]
MAX_COATING_FRAGMENTS = _THRESHOLDS["max_coating_fragments"]
FULL_CONFIDENCE = 1.0
INSUFFICIENT_DATA = "insufficient_data"

# Cyan rather than green: real roof photos are framed by vegetation.
OVERLAY_COLOR_BGR = (255, 200, 0)
OVERLAY_ALPHA = 0.45
ROOF_OUTLINE_COLOR_BGR = (0, 0, 255)
ROOF_OUTLINE_THICKNESS_PX = 2
OVERLAY_SUFFIX = "_coverage.png"


class CoverageInputError(ValueError):
    """Raised when the photo or the roof mask cannot be used."""


@dataclass(frozen=True)
class CoverageAnalysis:
    coverage_pct: float
    confidence: float
    quality_issues: tuple[str, ...]
    roof_mask: np.ndarray
    coating_mask: np.ndarray


def _morph_kernel(shape: tuple[int, ...]) -> np.ndarray:
    size = max(MIN_MORPH_KERNEL_PX, int(min(shape[:2]) * MORPH_KERNEL_FRACTION) | 1)
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def clean_mask(mask: np.ndarray) -> np.ndarray:
    """Opening removes isolated specks, closing fills pinholes; in this order a few noisy
    pixels can neither create coverage nor punch holes into it."""
    kernel = _morph_kernel(mask.shape)
    opened = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, kernel)
    return cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel).astype(bool)


def largest_component(mask: np.ndarray) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    if count <= 1:
        return np.zeros_like(mask, dtype=bool)
    largest_label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return labels == largest_label


def _border_pixels(image: np.ndarray) -> np.ndarray:
    border = max(1, int(min(image.shape[:2]) * BORDER_FRACTION))
    frame = np.ones(image.shape[:2], dtype=bool)
    frame[border:-border, border:-border] = False
    return image[frame]


def detect_roof_region(image_bgr: np.ndarray) -> np.ndarray:
    """Assumes a top-down photo with the roof in the middle and surroundings at the
    edges. When nothing stands out from the edges, the photo is taken to be cropped to
    the roof and the whole frame counts as roof."""
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    background = np.median(_border_pixels(lab), axis=0)
    differs = np.linalg.norm(lab - background, axis=2) > ROOF_COLOR_DISTANCE
    roof = largest_component(clean_mask(differs))
    if roof.mean() < MIN_ROOF_FRACTION:
        return np.ones(image_bgr.shape[:2], dtype=bool)
    return roof


def _hsv_channels(image_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    return hsv[..., 1] / MAX_CHANNEL_VALUE, hsv[..., 2] / MAX_CHANNEL_VALUE


def adaptive_value_threshold(value: np.ndarray) -> float:
    """Otsu over the whole scene adapts to the light the photo was taken in: under dim
    light the coating is darker, but still the bright mode of its own photo."""
    value_u8 = np.round(value * MAX_CHANNEL_VALUE).astype(np.uint8)
    otsu, _ = cv2.threshold(value_u8, 0, MAX_CHANNEL_VALUE, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    threshold = otsu / MAX_CHANNEL_VALUE
    low, high = value[value <= threshold], value[value > threshold]
    if low.size == 0 or high.size == 0 or high.mean() - low.mean() < MIN_MODE_SEPARATION:
        return UNIFORM_SCENE_MIN_COATING_VALUE
    return threshold


def detect_coating(image_bgr: np.ndarray) -> np.ndarray:
    saturation, value = _hsv_channels(image_bgr)
    bright = value > adaptive_value_threshold(value)
    return clean_mask(bright & (saturation <= MAX_COATING_SATURATION))


def count_fragments(mask: np.ndarray) -> int:
    count, _ = cv2.connectedComponents(mask.astype(np.uint8))
    return count - 1


def assess_photo_quality(
    image_bgr: np.ndarray, coating_on_roof: np.ndarray
) -> tuple[float, tuple[str, ...]]:
    """Each check is a ratio to its requirement, capped at 1; confidence is the weakest,
    so one bad property is enough to stop the photo from deciding a payout."""
    _, value = _hsv_channels(image_bgr)
    fragments = count_fragments(coating_on_roof)
    scores = {
        "too_dark": value.mean() / MIN_MEAN_BRIGHTNESS,
        "low_contrast": value.std() / MIN_CONTRAST_STD,
        "fragmented": MAX_COATING_FRAGMENTS / fragments if fragments else FULL_CONFIDENCE,
    }
    issues = tuple(name for name, score in scores.items() if score < FULL_CONFIDENCE)
    return min(FULL_CONFIDENCE, *scores.values()), issues


def compute_coverage(
    image_bgr: np.ndarray, roof_mask: np.ndarray | None = None
) -> CoverageAnalysis:
    roof = detect_roof_region(image_bgr) if roof_mask is None else roof_mask.astype(bool)
    if roof.shape != image_bgr.shape[:2]:
        raise CoverageInputError(
            f"Roof mask shape {roof.shape} does not match image {image_bgr.shape[:2]}."
        )
    if not roof.any():
        raise CoverageInputError("Roof mask contains no roof pixels.")
    coating = detect_coating(image_bgr) & roof
    confidence, issues = assess_photo_quality(image_bgr, coating)
    return CoverageAnalysis(
        coverage_pct=float(coating.sum() / roof.sum() * 100),
        confidence=float(confidence),
        quality_issues=issues,
        roof_mask=roof,
        coating_mask=coating,
    )


def build_overlay(image_bgr: np.ndarray, analysis: CoverageAnalysis) -> np.ndarray:
    tinted = image_bgr.copy()
    tinted[analysis.coating_mask] = OVERLAY_COLOR_BGR
    overlay = cv2.addWeighted(tinted, OVERLAY_ALPHA, image_bgr, 1 - OVERLAY_ALPHA, 0)
    contours, _ = cv2.findContours(
        analysis.roof_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    cv2.drawContours(overlay, contours, -1, ROOF_OUTLINE_COLOR_BGR, ROOF_OUTLINE_THICKNESS_PX)
    return overlay
