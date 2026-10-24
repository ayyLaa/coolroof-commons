"""CoolRoof Commons - method metrics for the "why is AI needed" slide.

Everything reported here is SIMULATED: anomaly detection is scored on the demo seed
(itself simulated) plus synthetic sessions with injected anomalies, and the
normalisation table uses physical-model surface temperatures. Only the weather driving
the normalisation scenarios is real Open-Meteo data. The metrics live in
ml/evaluation.py; this script only gathers inputs and writes data/metrics.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))

from app.core.config import ASSUMED_COATED_ALBEDO  # noqa: E402
from app.core.timezones import to_local  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Measurement, WeatherRecord  # noqa: E402
from app.services.demo_seed import build_demo_data  # noqa: E402
from app.repositories import roofs as roof_repo  # noqa: E402
from app.repositories import weather as weather_repo  # noqa: E402
from app.services import analysis  # noqa: E402
from app.services.weather import nearest_record  # noqa: E402

from ml.conditions import Weather  # noqa: E402
from ml.evaluation import LabelledSession, evaluate_anomaly_detection, normalization_stability  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "data" / "metrics.json"
SIMULATED = "simulated"
# The storm-corrupted durability upload is the seed's one known anomaly.
KNOWN_ANOMALOUS_SEED = {("ATH-0355", "durability")}
DEFAULT_WEATHER_ROOF = "ATH-1000"
DEFAULT_START, DEFAULT_END = "2026-07-01", "2026-07-07"
# Daylight hours a technician could measure in, local time, with real sun on the roof.
MEASURABLE_HOURS = range(9, 18)
MIN_RADIATION_WM2 = 200.0
BEFORE_LOCAL_HOUR = 13


def seed_sessions() -> list[LabelledSession]:
    labelled = []
    for scenario in build_demo_data():
        before = next(m for m in scenario.measurements if m.phase == "before")
        for measurement in scenario.measurements:
            labelled.append(_seed_session(measurement, before, scenario.weather_records))
    return labelled


def _seed_session(
    measurement: Measurement, before: Measurement, weather_rows: list[WeatherRecord]
) -> LabelledSession:
    is_before = measurement is before
    delta = (
        None if is_before else analysis.plateau_temp(measurement) - analysis.plateau_temp(before)
    )
    record = nearest_record(weather_rows, measurement.measured_at)
    session = analysis.to_session(measurement, analysis.to_ml_weather(record), delta)
    key = (measurement.roof_id, measurement.phase)
    kind = "seed_storm_corrupted" if key in KNOWN_ANOMALOUS_SEED else "seed_normal"
    return LabelledSession(session, key in KNOWN_ANOMALOUS_SEED, kind)


def load_weather_conditions(
    roof_id: str, start: str, end: str
) -> tuple[float, list[tuple[datetime, Weather]]]:
    """Real hourly weather already stored by scripts/fetch_weather.py, in local time."""
    window_start = datetime.combine(datetime.fromisoformat(start), time.min, tzinfo=UTC)
    window_end = datetime.combine(datetime.fromisoformat(end), time.max, tzinfo=UTC)
    with SessionLocal() as db:
        located = roof_repo.get_roof(db, roof_id)
        if located is None:
            raise SystemExit(f"Roof {roof_id} not found; run scripts/fetch_buildings.py.")
        records = weather_repo.list_in_range(db, roof_id, window_start, window_end)
    zone = located.roof.timezone
    conditions = [(to_local(r.timestamp, zone), analysis.to_ml_weather(r)) for r in records]
    usable = [
        (moment, w)
        for moment, w in conditions
        if moment.hour in MEASURABLE_HOURS and w.radiation_wm2 >= MIN_RADIATION_WM2
    ]
    if not usable:
        raise SystemExit(f"No stored daytime weather for {roof_id}; run scripts/fetch_weather.py.")
    return located.roof.albedo, usable


def normalization_table(roof_id: str, start: str, end: str) -> dict:
    albedo_before, conditions = load_weather_conditions(roof_id, start, end)
    before = next((c for c in conditions if c[0].hour == BEFORE_LOCAL_HOUR), conditions[0])
    after_conditions = [c for c in conditions if c is not before]
    table = normalization_stability(before, after_conditions, albedo_before, ASSUMED_COATED_ALBEDO)
    return {
        **table,
        "weather_source": "open-meteo (real hourly weather)",
        "weather_roof_id": roof_id,
        "before_measured_at": before[0].isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute anomaly and normalisation metrics.")
    parser.add_argument("--weather-roof-id", default=DEFAULT_WEATHER_ROOF)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    metrics = {
        "data_source": SIMULATED,
        "generated_at": datetime.now(UTC).isoformat(),
        "anomaly_detection": evaluate_anomaly_detection(seed_sessions()),
        "normalization": normalization_table(args.weather_roof_id, args.start, args.end),
    }
    args.output.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    detection, norm = metrics["anomaly_detection"], metrics["normalization"]
    print(
        f"Rules recall {detection['rules']['recall']}, IsolationForest recall "
        f"{detection['isolation_forest']['recall']}, combined {detection['combined']['recall']}."
    )
    print(
        f"Raw delta range {norm['raw_delta']['range_c']} C vs normalised "
        f"{norm['normalized_delta']['range_c']} C over {len(norm['scenarios'])} weather hours."
    )
    print(f"Written to {args.output}.")


if __name__ == "__main__":
    main()
