import pytest

from ml.config import ThresholdConfigurationError, load_ml_thresholds


def test_shared_thresholds_load() -> None:
    assert load_ml_thresholds("anomaly")["min_reading_count"] == 10
    assert load_ml_thresholds("coverage")["min_contrast_std"] > 0


def test_unknown_section_is_rejected() -> None:
    with pytest.raises(ThresholdConfigurationError):
        load_ml_thresholds("not-a-section")
