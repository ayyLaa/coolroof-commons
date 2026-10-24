"""CoolRoof Commons - writes the roofs and the demo weather to data/snapshots/ as CSV.

The roofs come from hours of Earth Engine work and live only in the database; the
committed CSVs let scripts/import_roofs.py (and seed.py) rebuild them without it. Only
the demo roofs' weather is kept: the rest is fetched again from Open-Meteo.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import ROOFS_SNAPSHOT_PATH, WEATHER_SNAPSHOT_PATH  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.services import snapshots  # noqa: E402
from app.services.demo_seed import DEMO_ROOF_IDS  # noqa: E402

# The London roof the demo shows next to the three Athens scenarios.
DEMO_LONDON_ROOF_ID = "LON-2064"
DEMO_WEATHER_ROOF_IDS = (*DEMO_ROOF_IDS, DEMO_LONDON_ROOF_ID)


def main() -> None:
    with SessionLocal() as session:
        roofs = snapshots.export_roofs(session, ROOFS_SNAPSHOT_PATH)
        weather = snapshots.export_weather(session, WEATHER_SNAPSHOT_PATH, DEMO_WEATHER_ROOF_IDS)
    for path, count in ((ROOFS_SNAPSHOT_PATH, roofs), (WEATHER_SNAPSHOT_PATH, weather)):
        print(f"{path.relative_to(REPO_ROOT)}: {count} rows, {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
