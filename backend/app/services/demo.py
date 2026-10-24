from app.repositories.transactions import RepositoryContext, commit

from app.repositories import demo as demo_repo
from app.schemas.demo import (
    DemoDeletedRows,
    DemoResetResponse,
    DemoRestoredRows,
    DemoRoundStatus,
)
from app.services import demo_seed, photos


def start_round(db: RepositoryContext) -> DemoResetResponse:
    """A tranche pays once per on-chain project, so a rerun needs fresh projects
    (scripts/demo-round.sh funds them). The previous round's chain mirror goes, and the
    seed rows and pending tranches come back as in reset_demo."""
    round_number = demo_repo.current_round(db) + 1
    cleared = demo_repo.delete_chain_mirror(db, list(demo_seed.DEMO_ROOF_IDS))
    demo_repo.add_round(db, round_number)
    result = reset_demo(db)
    deleted = result.deleted.model_copy(update=cleared)
    return result.model_copy(update={"round": round_number, "deleted": deleted})


def get_round(db: RepositoryContext) -> DemoRoundStatus:
    return DemoRoundStatus(round=demo_repo.current_round(db))


def reset_demo(db: RepositoryContext) -> DemoResetResponse:
    """Touches only the three demo roofs: scripts/reset.py would also delete the measured
    roofs and real weather, which take hours of Earth Engine and API calls to rebuild.
    Tranche states and contract events are kept, since they mirror the chain."""
    scenarios = demo_seed.build_demo_data()
    roof_ids = [rows.roof.id for rows in scenarios]
    measurement_ids = demo_repo.list_measurement_ids(db, roof_ids)
    deleted = demo_repo.delete_demo_rows(db, roof_ids)
    owned_rows = [
        row
        for rows in scenarios
        for row in (*rows.measurements, *rows.verifications, *rows.weather_records)
    ]
    demo_repo.write_demo_rows(db, [rows.roof for rows in scenarios], owned_rows)
    added_tranches = demo_repo.add_missing_tranches(
        db, [state for rows in scenarios for state in rows.contract_states]
    )
    commit(db)
    # Files go only after the commit, so a failed reset never loses a photo whose row
    # is still there.
    photo_files = sum(photos.delete_measurement_photos(str(mid)) for mid in measurement_ids)
    return DemoResetResponse(
        round=demo_repo.current_round(db),
        roof_ids=roof_ids,
        deleted=DemoDeletedRows(
            **deleted, contract_events=0, contract_states=0, photo_files=photo_files
        ),
        restored=DemoRestoredRows(
            roofs=len(scenarios),
            measurements=sum(len(rows.measurements) for rows in scenarios),
            verifications=sum(len(rows.verifications) for rows in scenarios),
            weather_records=sum(len(rows.weather_records) for rows in scenarios),
            contract_states=added_tranches,
        ),
    )
