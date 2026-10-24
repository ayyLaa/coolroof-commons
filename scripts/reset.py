"""CoolRoof Commons - empties every table and refills the database with the demo seed.

This deletes the satellite-measured roofs and the real Open-Meteo weather, which take
hours of Earth Engine and API calls to rebuild, so it refuses to run unless --force is
given and the operator types RESET after seeing exactly what will be deleted.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    ContractEvent,
    ContractState,
    Measurement,
    Roof,
    Verification,
    WeatherRecord,
)

import seed  # noqa: E402

CONFIRMATION_WORD = "RESET"
# Children before parents, so foreign keys never block a delete.
TABLES_IN_DELETE_ORDER = (
    ContractEvent,
    ContractState,
    Verification,
    Measurement,
    WeatherRecord,
    Roof,
)
# Tables whose rows carry a provenance label; the breakdown shows how much real data goes.
LABELLED_TABLES = (Roof, WeatherRecord, Measurement)


def count_rows(session: Session) -> dict[str, int]:
    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model))
        for model in TABLES_IN_DELETE_ORDER
    }


def count_by_source(session: Session) -> dict[str, dict[str, int]]:
    return {
        model.__tablename__: {
            source: count
            for source, count in session.execute(
                select(model.data_source, func.count()).group_by(model.data_source)
            )
        }
        for model in LABELLED_TABLES
    }


def print_deletion_plan(counts: dict[str, int], by_source: dict[str, dict[str, int]]) -> None:
    print("This will DELETE every row in these tables:")
    for table, total in counts.items():
        sources = by_source.get(table, {})
        detail = ", ".join(f"{source}: {n}" for source, n in sorted(sources.items()))
        print(f"  {table:<16} {total:>7}" + (f"  ({detail})" if detail else ""))
    print(f"  {'total':<16} {sum(counts.values()):>7}")
    print("seed.py reloads only what data/snapshots/ holds: the roofs as last exported and the")
    print("demo roofs' weather. Newer roofs and the other third_party weather need")
    print("fetch_buildings.py, fetch_satellite.py and fetch_weather.py to rebuild.")


def confirmed_by_operator() -> bool:
    try:
        answer = input(f"Type {CONFIRMATION_WORD} to continue: ")
    except EOFError:
        return False
    return answer.strip() == CONFIRMATION_WORD


def clear_database(session: Session) -> None:
    for model in TABLES_IN_DELETE_ORDER:
        session.query(model).delete()
    session.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Empty the database and load the demo seed.")
    parser.add_argument(
        "--force", action="store_true", help="Required: acknowledges that real data is deleted."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        print_deletion_plan(count_rows(session), count_by_source(session))
        if not args.force:
            raise SystemExit("Refusing to reset without --force. Nothing was deleted.")
        if not confirmed_by_operator():
            raise SystemExit("Confirmation not given. Nothing was deleted.")
        clear_database(session)
    print("Database cleared.")
    seed.main()


if __name__ == "__main__":
    main()
