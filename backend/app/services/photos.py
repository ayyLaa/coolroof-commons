import shutil
from dataclasses import dataclass
from pathlib import Path

from ml.coverage import CoverageInputError
from app.infrastructure.coverage_files import analyze_coverage

from app.core.config import PHOTO_DIR, PHOTO_URL_PREFIX, PUBLIC_BASE_URL, REPO_ROOT
from app.core.exceptions import InvalidPhotoError
from app.repositories.records import MeasurementData

ALLOWED_PHOTO_SUFFIXES = (".jpg", ".jpeg", ".png")
FULL_CONFIDENCE = 1.0


@dataclass(frozen=True)
class CoverageOutcome:
    """reliable is False when there is no usable photo evidence, or when ml/coverage
    reported low confidence and suggested insufficient_data."""

    coverage_pct: float
    confidence: float
    reliable: bool
    quality_issues: tuple[str, ...]
    photo_bytes: bytes


NO_PHOTO = CoverageOutcome(0.0, 0.0, False, ("no_photo",), b"")


def photo_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_PHOTO_SUFFIXES:
        raise InvalidPhotoError(
            f"Unsupported photo type '{suffix}', use one of {ALLOWED_PHOTO_SUFFIXES}."
        )
    return suffix


def save_photo(measurement_id: str, filename: str, content: bytes) -> Path:
    """Stored under the measurement id instead of the client filename, so uploads can
    never overwrite each other or escape the photo directory."""
    path = PHOTO_DIR / measurement_id / f"photo{photo_suffix(filename)}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def delete_measurement_photos(measurement_id: str) -> int:
    """Removes the upload and its overlay together; returns how many files went."""
    directory = PHOTO_DIR / measurement_id
    if not directory.is_dir():
        return 0
    files = [path for path in directory.rglob("*") if path.is_file()]
    shutil.rmtree(directory)
    return len(files)


def to_stored_path(path: Path) -> str:
    """Relative to the repository when possible, matching the seed's data/photos/... paths."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def resolve_photo(measurement: MeasurementData) -> Path | None:
    if not measurement.photo_path:
        return None
    path = Path(measurement.photo_path)
    path = path if path.is_absolute() else REPO_ROOT / path
    return path if path.is_file() else None


def run_coverage(photo_path: Path) -> dict:
    try:
        return dict(analyze_coverage(photo_path))
    except CoverageInputError as error:
        raise InvalidPhotoError(str(error)) from error


def mask_preview_url(mask_path: str) -> str:
    relative = Path(mask_path).resolve().relative_to(PHOTO_DIR.resolve()).as_posix()
    return f"{PUBLIC_BASE_URL}{PHOTO_URL_PREFIX}/{relative}"


def evaluate_coverage(measurement: MeasurementData) -> CoverageOutcome:
    """Only simulated records that never referenced a photo may use seed coverage.
    Losing an uploaded file must never upgrade its quality to full confidence."""
    photo = resolve_photo(measurement)
    if photo is not None:
        report = run_coverage(photo)
        return CoverageOutcome(
            coverage_pct=report["coverage_pct"],
            confidence=report["confidence"],
            reliable=report["suggested_status"] is None,
            quality_issues=tuple(report["quality_issues"]),
            photo_bytes=photo.read_bytes(),
        )
    if measurement.data_source == "simulated" and not measurement.photo_path and measurement.coverage_pct is not None:
        return CoverageOutcome(measurement.coverage_pct, FULL_CONFIDENCE, True, (), b"")
    return NO_PHOTO
