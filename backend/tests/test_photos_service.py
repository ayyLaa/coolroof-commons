from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ml.coverage import CoverageInputError
from app.core.exceptions import InvalidPhotoError
from app.models import Measurement
from app.services import photos


def test_save_photo_ignores_client_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(photos, "PHOTO_DIR", Path("uploads"))
    mkdir = MagicMock()
    write = MagicMock()
    monkeypatch.setattr(Path, "mkdir", mkdir)
    monkeypatch.setattr(Path, "write_bytes", write)

    path = photos.save_photo("measurement-1", "../../outside/roof.png", b"image")

    assert path == Path("uploads/measurement-1/photo.png")
    write.assert_called_once_with(b"image")
    mkdir.assert_called_once_with(parents=True, exist_ok=True)


def test_save_photo_rejects_unsupported_file_before_writing(monkeypatch: pytest.MonkeyPatch) -> None:
    write = MagicMock()
    monkeypatch.setattr(Path, "write_bytes", write)
    with pytest.raises(InvalidPhotoError, match="Unsupported photo type"):
        photos.save_photo("measurement-1", "roof.exe", b"image")
    write.assert_not_called()


def test_evaluate_coverage_uses_photo_quality(monkeypatch: pytest.MonkeyPatch) -> None:
    path = Path("uploads/roof.png")
    monkeypatch.setattr(photos, "resolve_photo", lambda _: path)
    monkeypatch.setattr(Path, "read_bytes", lambda _: b"image")
    monkeypatch.setattr(photos, "run_coverage", lambda _: {
        "coverage_pct": 94.0, "confidence": 0.4, "suggested_status": "insufficient_data",
        "quality_issues": ["too_dark"],
    })

    result = photos.evaluate_coverage(Measurement(coverage_pct=100.0))

    assert result.coverage_pct == 94.0
    assert result.reliable is False
    assert result.quality_issues == ("too_dark",)
    assert result.photo_bytes == b"image"


def test_evaluate_coverage_without_evidence_is_unreliable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(photos, "resolve_photo", lambda _: None)
    assert photos.evaluate_coverage(Measurement()) == photos.NO_PHOTO


def test_coverage_failure_becomes_domain_error(monkeypatch: pytest.MonkeyPatch) -> None:
    analyze = MagicMock(side_effect=CoverageInputError("Not a readable image"))
    monkeypatch.setattr(photos, "analyze_coverage", analyze)
    with pytest.raises(InvalidPhotoError, match="Not a readable image"):
        photos.run_coverage(Path("roof.png"))


@pytest.mark.parametrize("source", ["measured", "third_party", "simulated"])
def test_missing_uploaded_photo_never_uses_cached_coverage(source: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(photos, "resolve_photo", lambda _: None)
    measurement = Measurement(data_source=source, photo_path="lost.png", coverage_pct=99)
    assert photos.evaluate_coverage(measurement).reliable is False


def test_real_measurement_without_a_photo_is_unreliable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(photos, "resolve_photo", lambda _: None)
    assert not photos.evaluate_coverage(Measurement(data_source="measured", coverage_pct=99)).reliable
