import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://coolroof:coolroof@localhost:5432/coolroof"
)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
DEVICE_PRIVATE_KEY = os.getenv("DEVICE_PRIVATE_KEY", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
PHOTO_DIR = Path(os.getenv("PHOTO_DIR", str(REPO_ROOT / "data" / "photos")))
PHOTO_URL_PREFIX = "/media/photos"
DATA_DIR = REPO_ROOT / "data"
METRICS_PATH = DATA_DIR / "metrics.json"
SATELLITE_EVIDENCE_PATH = DATA_DIR / "satellite_evidence.json"
CLIMATE_COMPARISON_PATH = DATA_DIR / "climate_comparison.json"
# Committed copies of the generated reports, served when data/ has no fresh output (for
# example when Earth Engine is unavailable and the pipeline cannot be rerun).
SNAPSHOT_DIR = DATA_DIR / "snapshots"
# Database snapshots: every roof, and only the weather the demo needs (the rest can be
# fetched again from Open-Meteo). seed.py loads them into an empty database.
ROOFS_SNAPSHOT_PATH = SNAPSHOT_DIR / "roofs.csv"
WEATHER_SNAPSHOT_PATH = SNAPSHOT_DIR / "weather_demo.csv"
# No after-coating albedo is measured; this is the typical solar reflectance of the
# white elastomeric coatings the programme funds.
ASSUMED_COATED_ALBEDO = float(os.getenv("ASSUMED_COATED_ALBEDO", "0.75"))
# Installed price of the coating per square metre; estimated_cost_eur is area x this.
COST_PER_M2_EUR = float(os.getenv("COST_PER_M2_EUR", "12"))
# The deployed escrow and the parties scripts/setup-demo.ts creates every demo project
# with. Empty until the contract is deployed, so the API reports them as null.
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS") or None
CONTRACT_SPONSOR = os.getenv("CONTRACT_SPONSOR") or None
CONTRACT_CONTRACTOR = os.getenv("CONTRACT_CONTRACTOR") or None
# setup-demo.ts locks 0.001 native token (10**15 wei) per demo project.
CONTRACT_DEPOSIT_WEI = int(os.getenv("CONTRACT_DEPOSIT_WEI", str(10**15)))


THRESHOLDS_PATH = REPO_ROOT / "schema" / "thresholds.json"


@dataclass(frozen=True)
class Thresholds:
    min_normalized_delta_c: float
    min_coverage_pct: float
    force_majeure_gust_ms: float
    force_majeure_precip_mm: float
    durability_check_days: int
    # Climates with a real heating season ask for the reflective roof's winter cost to be
    # weighed before payout (see /evidence/climate-comparison).
    winter_penalty_check: bool
    # Why the city's requirement has its value (scripts/threshold_rationale.py derives it);
    # a city without its own entry has none.
    rationale: str | None = None


def load_threshold_config(path: Path = THRESHOLDS_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


THRESHOLD_CONFIG = load_threshold_config()


def thresholds_for(city: str | None, config: dict | None = None) -> Thresholds:
    """City overrides are merged over the defaults; an unknown or missing city gets the
    defaults, so a new pilot city works before it has its own tuning."""
    config = THRESHOLD_CONFIG if config is None else config
    overrides = config["by_city"].get((city or "").lower(), {})
    return Thresholds(**{**config["default"], **overrides})


DEFAULT_THRESHOLDS = thresholds_for(None)
