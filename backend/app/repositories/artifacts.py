"""Read access to JSON artifacts that scripts/ prepare under data/."""

import json
from pathlib import Path


def read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
