import uuid

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db import Base

# Surface temperatures are either satellite-measured or physically simulated; the two
# must never be mixed, so every roof and measurement row carries one of these labels.
MEASURED = "measured"
SIMULATED = "simulated"
# Data from an outside provider (Open-Meteo weather): neither measured by us nor simulated.
THIRD_PARTY = "third_party"
SMALL_ROOF = "small"
LARGE_ROOF = "large"


class Roof(Base):
    __tablename__ = "roofs"

    id = Column(String, primary_key=True)
    city = Column(String, nullable=False)
    geom = Column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)
    area_m2 = Column(Float, nullable=False)
    albedo = Column(Float, nullable=False)
    surface_temp_c = Column(Float, nullable=False)
    priority_score = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    data_source = Column(String, nullable=False, server_default=SIMULATED, default=SIMULATED)
    # IANA name derived from the roof's location; timestamps stay UTC and are only
    # localised for normalisation.
    timezone = Column(String, nullable=False)
    # "small" residential or "large" industrial: whether a satellite thermal pixel can
    # resolve the roof at all depends on it.
    roof_class = Column(String, nullable=False, server_default=SMALL_ROOF, default=SMALL_ROOF)
    # Which instrument produced surface_temp_c, and its native ground resolution.
    surface_temp_instrument = Column(String, nullable=True)
    surface_temp_resolution_m = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Measurement(Base):
    __tablename__ = "measurements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    roof_id = Column(String, ForeignKey("roofs.id"), nullable=False)
    phase = Column(String, nullable=False)
    device_id = Column(String, nullable=False)
    raw_readings = Column(JSONB, nullable=False)
    measured_at = Column(DateTime(timezone=True), nullable=False)
    normalized_delta_c = Column(Float, nullable=True)
    anomaly_flags = Column(JSONB, nullable=False, default=list)
    photo_path = Column(String, nullable=True)
    coverage_pct = Column(Float, nullable=True)
    data_source = Column(String, nullable=False, server_default=SIMULATED, default=SIMULATED)


class Verification(Base):
    __tablename__ = "verifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    roof_id = Column(String, ForeignKey("roofs.id"), nullable=False)
    status = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    evidence_hash = Column(String, nullable=False)
    device_signature = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WeatherRecord(Base):
    __tablename__ = "weather_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    roof_id = Column(String, ForeignKey("roofs.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    ambient_c = Column(Float, nullable=False)
    radiation_wm2 = Column(Float, nullable=False)
    wind_ms = Column(Float, nullable=False)
    max_gust_ms = Column(Float, nullable=False)
    precipitation_mm = Column(Float, nullable=False)
    data_source = Column(String, nullable=False, server_default=THIRD_PARTY, default=THIRD_PARTY)


class ContractState(Base):
    __tablename__ = "contract_states"

    roof_id = Column(String, ForeignKey("roofs.id"), primary_key=True)
    tranche_name = Column(String, primary_key=True)
    pct = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    tx_hash = Column(String, nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)


class ContractEvent(Base):
    """On-chain escrow events relayed by the oracle; contract_states holds only each
    tranche's latest state, this table keeps the timeline that led to it."""

    __tablename__ = "contract_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    roof_id = Column(String, ForeignKey("roofs.id"), nullable=False, index=True)
    event_name = Column(String, nullable=False)
    tranche = Column(String, nullable=True)
    # uint256 wei amounts overflow every SQL integer type, so they are kept as digits.
    amount_wei = Column(String, nullable=True)
    tx_hash = Column(String, nullable=False)
    block_number = Column(BigInteger, nullable=False)
    reason = Column(String, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # The demo round whose on-chain project emitted the event (0: the unsuffixed original).
    round = Column(Integer, nullable=False, server_default="0", default=0)


class DemoRound(Base):
    """Each round funds fresh escrow projects, since a tranche pays once per project;
    the latest row is the round the backend currently mirrors."""

    __tablename__ = "demo_rounds"

    round = Column(Integer, primary_key=True, autoincrement=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
