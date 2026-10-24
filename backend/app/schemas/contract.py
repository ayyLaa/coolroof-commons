from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.verification import EVIDENCE_HASH_PATTERN

WEI_PATTERN = r"^[0-9]+$"
ADDRESS_PATTERN = r"^0x[a-fA-F0-9]{40}$"


class TrancheStatus(str, Enum):
    PENDING = "pending"
    RELEASED = "released"
    HELD = "held"


class TrancheName(str, Enum):
    """The escrow's Tranche enum in contracts/contracts/CoolRoofEscrow.sol."""

    QUALITY = "QUALITY"
    DURABILITY = "DURABILITY"
    FORCE_MAJEURE_RESERVE = "FORCE_MAJEURE_RESERVE"


class ContractEventName(str, Enum):
    """The escrow events the oracle relays."""

    TRANCHE_RELEASED = "TrancheReleased"
    PAYMENT_HELD = "PaymentHeld"
    FORCE_MAJEURE_APPLIED = "ForceMajeureApplied"
    UNRELEASED_RECLAIMED = "UnreleasedReclaimed"


# Escrow events about the whole project rather than one tranche.
PROJECT_EVENTS = (ContractEventName.FORCE_MAJEURE_APPLIED, ContractEventName.UNRELEASED_RECLAIMED)
# Events that move funds, so the amount moved is part of the record.
AMOUNT_EVENTS = (ContractEventName.TRANCHE_RELEASED, ContractEventName.UNRELEASED_RECLAIMED)


class Tranche(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: TrancheName
    pct: float = Field(ge=0, le=100)
    amount_wei: str | None = Field(pattern=WEI_PATTERN)
    status: TrancheStatus
    tx_hash: str | None = None
    released_at: datetime | None = None


class ContractEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_name: ContractEventName
    tranche: TrancheName | None = None
    amount_wei: str | None = Field(default=None, pattern=WEI_PATTERN)
    tx_hash: str = Field(pattern=EVIDENCE_HASH_PATTERN)
    block_number: int = Field(ge=0)
    reason: str | None = None
    occurred_at: datetime
    # The demo round of the on-chain project ("ATH-0142#3" is round 3); the oracle strips
    # the suffix from the roof ID and sends the round here.
    round: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _tranche_events_name_their_tranche(self) -> "ContractEventCreate":
        """A release or hold changes one tranche's state, so it cannot be applied without
        knowing which; ForceMajeureApplied is followed by its own hold and release, and
        UnreleasedReclaimed returns every unpaid tranche at once."""
        if self.event_name not in PROJECT_EVENTS and self.tranche is None:
            raise ValueError(f"{self.event_name.value} requires a tranche.")
        if self.event_name in AMOUNT_EVENTS and self.amount_wei is None:
            raise ValueError(f"{self.event_name.value} requires amount_wei.")
        return self


class ContractEventRecord(ContractEventCreate):
    roof_id: str


class ContractThresholds(BaseModel):
    """The thresholds for the roof's city, as in schema/thresholds.json."""

    model_config = ConfigDict(extra="forbid")

    min_normalized_delta_c: float
    min_coverage_pct: float
    force_majeure_gust_ms: float
    force_majeure_precip_mm: float
    durability_check_days: int
    winter_penalty_check: bool
    rationale: str | None


class ContractStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roof_id: str
    contract_address: str | None = Field(pattern=ADDRESS_PATTERN)
    sponsor: str | None = Field(pattern=ADDRESS_PATTERN)
    contractor: str | None = Field(pattern=ADDRESS_PATTERN)
    total_amount_wei: str | None = Field(pattern=WEI_PATTERN)
    thresholds: ContractThresholds
    tranches: list[Tranche]
    events: list[ContractEventRecord]
