from pathlib import Path
from typing import TypedDict

import cv2
import numpy as np

from ml.coverage import (CoverageInputError, INSUFFICIENT_DATA, FULL_CONFIDENCE, OVERLAY_SUFFIX, compute_coverage, build_overlay)

class CoverageReport(TypedDict):
    coverage_pct: float
    mask_path: str
    confidence: float
    quality_issues: list[str]
    suggested_status: str | None


def read_image(path: Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray:
    """np.fromfile + imdecode instead of cv2.imread, which fails silently on non-ASCII
    Windows paths."""
    if not path.is_file():
        raise CoverageInputError(f"Image not found: {path}")
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), flags)
    if image is None:
        raise CoverageInputError(f"Not a readable image: {path}")
    return image


def write_png(path: Path, image: np.ndarray) -> None:
    encoded, buffer = cv2.imencode(".png", image)
    if not encoded:
        raise CoverageInputError(f"Could not encode overlay for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer.tofile(str(path))


def _load_roof_mask(roof_mask: str | Path | np.ndarray | None) -> np.ndarray | None:
    if roof_mask is None or isinstance(roof_mask, np.ndarray):
        return roof_mask
    return read_image(Path(roof_mask), cv2.IMREAD_GRAYSCALE) > 0


def analyze_coverage(
    image_path: str | Path,
    roof_mask: str | Path | np.ndarray | None = None,
    output_dir: str | Path | None = None,
) -> CoverageReport:
    """The overlay PNG lands next to the photo unless output_dir is given; the frontend
    shows it so a reviewer can see what was counted as coated."""
    image_path = Path(image_path)
    image = read_image(image_path)
    analysis = compute_coverage(image, _load_roof_mask(roof_mask))
    mask_path = Path(output_dir or image_path.parent) / f"{image_path.stem}{OVERLAY_SUFFIX}"
    write_png(mask_path, build_overlay(image, analysis))
    return CoverageReport(
        coverage_pct=round(analysis.coverage_pct, 1),
        mask_path=str(mask_path),
        confidence=round(analysis.confidence, 2),
        quality_issues=list(analysis.quality_issues),
        suggested_status=INSUFFICIENT_DATA if analysis.confidence < FULL_CONFIDENCE else None,
    )
