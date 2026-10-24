"""CoolRoof Commons - loads data/snapshots/roofs.csv and weather_demo.csv into the database.

Needs no Earth Engine and works on an empty, migrated database. Rows already stored are
kept, so running it twice changes nothing.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import ROOFS_SNAPSHOT_PATH, WEATHER_SNAPSHOT_PATH  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.services import snapshots  # noqa: E402


def import_snapshots(session: Session) -> None:
    """Roofs first: every weather row references one."""
    added = snapshots.import_roofs(session, ROOFS_SNAPSHOT_PATH)
    print(f"Roofs: {added} added from {ROOFS_SNAPSHOT_PATH.name}.")
    if WEATHER_SNAPSHOT_PATH.exists():
        read = snapshots.import_weather(session, WEATHER_SNAPSHOT_PATH)
        print(f"Weather: {read} rows read from {WEATHER_SNAPSHOT_PATH.name}, missing hours added.")
    session.commit()


def main() -> None:
    if not ROOFS_SNAPSHOT_PATH.exists():
        raise SystemExit(f"{ROOFS_SNAPSHOT_PATH} not found; run scripts/export_roofs.py first.")
    with SessionLocal() as session:
        import_snapshots(session)


if __name__ == "__main__":
    main()
