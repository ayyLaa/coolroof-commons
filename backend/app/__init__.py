import sys
from pathlib import Path

# ml/ is a standalone library at the repository root, not an installed package; the
# backend runs from backend/, so the root must be importable for `import ml`.
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)
