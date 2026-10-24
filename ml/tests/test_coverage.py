import numpy as np
import pytest

from ml.coverage import CoverageInputError, compute_coverage
from ml.tests.coverage_images import fully_coated_roof, half_coated_roof, flat_grey_photo


def test_full_and_half_coverage() -> None:
    assert compute_coverage(fully_coated_roof()).coverage_pct == pytest.approx(100, abs=3)
    assert compute_coverage(half_coated_roof()).coverage_pct == pytest.approx(50, abs=3)


def test_flat_image_loses_confidence() -> None:
    report = compute_coverage(flat_grey_photo())
    assert report.confidence < 1
    assert "low_contrast" in report.quality_issues


def test_invalid_mask_is_rejected() -> None:
    with pytest.raises(CoverageInputError):
        compute_coverage(half_coated_roof(), np.ones((2, 2), dtype=bool))
