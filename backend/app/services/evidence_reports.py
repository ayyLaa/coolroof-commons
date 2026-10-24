import logging
from pathlib import Path

from app.core.config import (
    CLIMATE_COMPARISON_PATH,
    METRICS_PATH,
    SATELLITE_EVIDENCE_PATH,
    SNAPSHOT_DIR,
)
from app.core.exceptions import ArtifactNotGeneratedError
from app.repositories import artifacts
from app.schemas.evidence import ClimateComparison, MetricsReport, SatelliteEvidence

logger = logging.getLogger(__name__)


def _load(path: Path, script: str) -> dict:
    """A fresh script output wins; the committed snapshot keeps the demo working when the
    pipeline cannot be rerun. Serving it is logged so a stale report is never silent."""
    data = artifacts.read_json(path)
    if data is not None:
        return data
    snapshot = SNAPSHOT_DIR / path.name
    data = artifacts.read_json(snapshot)
    if data is None:
        raise ArtifactNotGeneratedError(
            f"{path.name} has not been generated and has no snapshot; run {script}."
        )
    logger.warning("%s not found, serving snapshot %s.", path, snapshot)
    return data


def get_metrics() -> MetricsReport:
    return MetricsReport.model_validate(_load(METRICS_PATH, "scripts/metrics.py"))


def get_satellite_evidence() -> SatelliteEvidence:
    data = _load(SATELLITE_EVIDENCE_PATH, "scripts/satellite_evidence.py")
    return SatelliteEvidence.model_validate(data)


def get_climate_comparison() -> ClimateComparison:
    data = _load(CLIMATE_COMPARISON_PATH, "scripts/climate_comparison.py")
    return ClimateComparison.model_validate(data)
