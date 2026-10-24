"""CoolRoof Commons - loads the roof snapshot, then restores the three demo roofs.

The demo roofs are the same work as POST /demo/reset; their scenarios live in
backend/app/services/demo_seed.py. data/snapshots/roofs.csv, when present, brings the
measured roofs into an empty database first, so a fresh stack has every roof. Only the
demo roofs' rows are replaced; real roofs and third-party weather are kept.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import ROOFS_SNAPSHOT_PATH  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.services import demo  # noqa: E402

import import_roofs  # noqa: E402


def main() -> None:
    with SessionLocal() as session:
        if ROOFS_SNAPSHOT_PATH.exists():
            import_roofs.import_snapshots(session)
        result = demo.reset_demo(session)
    print(f"Seed done: {', '.join(result.roof_ids)}.")
    print(f"  deleted:  {result.deleted.model_dump()}")
    print(f"  restored: {result.restored.model_dump()}")


if __name__ == "__main__":
    main()
