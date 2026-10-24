import json
from pathlib import Path

THRESHOLDS_PATH = Path(__file__).resolve().parents[1] / "schema" / "thresholds.json"


class ThresholdConfigurationError(ValueError):
    pass


def load_ml_thresholds(section: str, path: Path = THRESHOLDS_PATH) -> dict[str, int | float]:
    try:
        values = json.loads(path.read_text(encoding="utf-8"))["ml"][section]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ThresholdConfigurationError(f"Cannot load ML thresholds for {section}.") from error
    if not isinstance(values, dict) or not values:
        raise ThresholdConfigurationError(f"ML threshold section {section} must be an object.")
    if any(type(value) not in (int, float) for value in values.values()):
        raise ThresholdConfigurationError(f"ML thresholds for {section} must be numeric.")
    return values
