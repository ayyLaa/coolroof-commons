from pathlib import Path

import cv2
import numpy as np
import pytest

from ml.coverage import (
    INSUFFICIENT_DATA,
    CoverageInputError,
)
from app.infrastructure.coverage_files import analyze_coverage, write_png
from ml.tests.coverage_images import (
    IMAGE_SIZE_PX,
    coated_half_mask,
    flat_grey_photo,
    fully_coated_roof,
    half_coated_roof,
    roof_square_mask,
    speckled_roof,
    uncoated_roof,
)

# Morphology rounds the roof's corners and edges by a few pixels.
COVERAGE_TOLERANCE_PCT = 3.0
# Dim light at 60% exposure: still readable, but a fixed brightness threshold tuned
# for full sun would miss the coating.
DIM_LIGHT = 0.6
NIGHT_LIGHT = 0.15


def save(tmp_path: Path, name: str, image: np.ndarray) -> Path:
    path = tmp_path / f"{name}.png"
    write_png(path, image)
    return path


def test_fully_coated_roof(tmp_path: Path) -> None:
    report = analyze_coverage(save(tmp_path, "full", fully_coated_roof()))

    assert report["coverage_pct"] == pytest.approx(100.0, abs=COVERAGE_TOLERANCE_PCT)
    assert report["confidence"] == 1.0
    assert report["suggested_status"] is None


def test_half_coated_roof(tmp_path: Path) -> None:
    report = analyze_coverage(save(tmp_path, "half", half_coated_roof()))

    assert report["coverage_pct"] == pytest.approx(50.0, abs=COVERAGE_TOLERANCE_PCT)
    assert report["quality_issues"] == []


def test_uncoated_roof(tmp_path: Path) -> None:
    report = analyze_coverage(save(tmp_path, "none", uncoated_roof()))

    assert report["coverage_pct"] == pytest.approx(0.0, abs=COVERAGE_TOLERANCE_PCT)


def test_adaptive_threshold_survives_dim_light(tmp_path: Path) -> None:
    report = analyze_coverage(save(tmp_path, "dim", half_coated_roof(DIM_LIGHT)))

    assert report["coverage_pct"] == pytest.approx(50.0, abs=COVERAGE_TOLERANCE_PCT)


def test_overlay_png_is_written(tmp_path: Path) -> None:
    image_path = save(tmp_path, "half", half_coated_roof())

    report = analyze_coverage(image_path, output_dir=tmp_path / "out")

    overlay = cv2.imread(report["mask_path"])
    assert Path(report["mask_path"]) == tmp_path / "out" / "half_coverage.png"
    assert overlay.shape == (IMAGE_SIZE_PX, IMAGE_SIZE_PX, 3)


def test_given_roof_mask_is_used(tmp_path: Path) -> None:
    mask_path = save(tmp_path, "mask", coated_half_mask())

    report = analyze_coverage(save(tmp_path, "half", half_coated_roof()), roof_mask=mask_path)

    assert report["coverage_pct"] == pytest.approx(100.0, abs=COVERAGE_TOLERANCE_PCT)


def test_mask_as_array(tmp_path: Path) -> None:
    report = analyze_coverage(save(tmp_path, "half", half_coated_roof()), roof_square_mask())

    assert report["coverage_pct"] == pytest.approx(50.0, abs=COVERAGE_TOLERANCE_PCT)


def test_dark_photo_suggests_insufficient_data(tmp_path: Path) -> None:
    report = analyze_coverage(save(tmp_path, "night", half_coated_roof(NIGHT_LIGHT)))

    assert "too_dark" in report["quality_issues"]
    assert report["confidence"] < 1.0
    assert report["suggested_status"] == INSUFFICIENT_DATA


def test_flat_photo_has_low_contrast(tmp_path: Path) -> None:
    report = analyze_coverage(save(tmp_path, "flat", flat_grey_photo()))

    assert "low_contrast" in report["quality_issues"]
    assert report["suggested_status"] == INSUFFICIENT_DATA


def test_fragmented_coating_lowers_confidence(tmp_path: Path) -> None:
    report = analyze_coverage(save(tmp_path, "specks", speckled_roof()))

    assert "fragmented" in report["quality_issues"]
    assert report["suggested_status"] == INSUFFICIENT_DATA


def test_missing_image_raises(tmp_path: Path) -> None:
    with pytest.raises(CoverageInputError):
        analyze_coverage(tmp_path / "missing.png")


def test_mismatched_mask_raises(tmp_path: Path) -> None:
    wrong_size = np.ones((10, 10), dtype=np.uint8)

    with pytest.raises(CoverageInputError):
        analyze_coverage(save(tmp_path, "half", half_coated_roof()), roof_mask=wrong_size)


def test_empty_mask_raises(tmp_path: Path) -> None:
    empty = np.zeros((IMAGE_SIZE_PX, IMAGE_SIZE_PX), dtype=np.uint8)

    with pytest.raises(CoverageInputError):
        analyze_coverage(save(tmp_path, "half", half_coated_roof()), roof_mask=empty)
