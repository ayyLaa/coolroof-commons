from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models import SIMULATED
from app.services import demo, demo_seed, photos
from app.services.contracts import TRANCHE_PERCENTS


def scenario(roof_id: str) -> demo_seed.DemoRoofRows:
    return next(rows for rows in demo_seed.build_demo_data() if rows.roof.id == roof_id)


def test_demo_data_covers_the_three_scenarios() -> None:
    rows = demo_seed.build_demo_data()

    assert [r.roof.id for r in rows] == list(demo_seed.DEMO_ROOF_IDS)
    statuses = [[v.status for v in r.verifications] for r in rows]
    assert statuses == [["approved"], ["flagged"], ["approved", "insufficient_data"]]
    assert all(r.data_source == SIMULATED for r in rows[0].weather_records)


def test_tranches_use_the_escrow_split() -> None:
    for rows in demo_seed.build_demo_data():
        assert {s.tranche_name: s.pct for s in rows.contract_states} == {
            name.value: pct for name, pct in TRANCHE_PERCENTS.items()
        }


def test_seed_leaves_every_tranche_pending_and_off_chain() -> None:
    """Only relayed escrow events may move a tranche, so no fabricated hash can appear."""
    for rows in demo_seed.build_demo_data():
        assert {s.status for s in rows.contract_states} == {"pending"}
        assert all(s.tx_hash is None and s.released_at is None for s in rows.contract_states)


def test_demo_data_is_deterministic() -> None:
    first, second = scenario("ATH-0142"), scenario("ATH-0142")

    assert [m.id for m in first.measurements] == [m.id for m in second.measurements]
    assert first.verifications[0].evidence_hash == second.verifications[0].evidence_hash


def test_reset_rewrites_demo_rows_and_reports_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    written = {}
    monkeypatch.setattr("app.repositories.demo.current_round", lambda _db: 2)
    measurement_id = uuid4()
    monkeypatch.setattr(
        "app.repositories.demo.list_measurement_ids", lambda _db, _ids: [measurement_id]
    )
    monkeypatch.setattr(
        "app.repositories.demo.delete_demo_rows",
        lambda _db, _ids: {
            "verifications": 5,
            "measurements": 8,
            "weather_records": 7,
        },
    )
    monkeypatch.setattr(
        "app.repositories.demo.write_demo_rows",
        lambda _db, roofs, rows: written.update(roofs=roofs, rows=rows),
    )
    monkeypatch.setattr(
        "app.repositories.demo.add_missing_tranches",
        lambda _db, states: written.update(tranches=states) or 4,
    )
    monkeypatch.setattr(photos, "delete_measurement_photos", lambda mid: 2)
    db = MagicMock()

    result = demo.reset_demo(db)

    assert result.roof_ids == list(demo_seed.DEMO_ROOF_IDS)
    assert result.round == 2
    assert (result.deleted.contract_events, result.deleted.contract_states) == (0, 0)
    assert (result.deleted.measurements, result.deleted.photo_files) == (8, 2)
    assert (result.restored.roofs, result.restored.measurements) == (3, 7)
    assert result.restored.contract_states == 4
    assert len(written["rows"]) == 7 + 4 + 7
    assert len(written["tranches"]) == 9
    db.commit.assert_called_once()


def test_new_round_clears_the_chain_mirror_and_counts_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rounds = [4]
    monkeypatch.setattr("app.repositories.demo.current_round", lambda _db: rounds[-1])
    monkeypatch.setattr("app.repositories.demo.add_round", lambda _db, n: rounds.append(n))
    cleared = MagicMock(return_value={"contract_events": 6, "contract_states": 9})
    monkeypatch.setattr("app.repositories.demo.delete_chain_mirror", cleared)
    monkeypatch.setattr("app.repositories.demo.list_measurement_ids", lambda _db, _ids: [])
    monkeypatch.setattr(
        "app.repositories.demo.delete_demo_rows",
        lambda _db, _ids: {"verifications": 0, "measurements": 0, "weather_records": 0},
    )
    monkeypatch.setattr("app.repositories.demo.write_demo_rows", lambda _db, _roofs, _rows: None)
    monkeypatch.setattr("app.repositories.demo.add_missing_tranches", lambda _db, states: 9)

    result = demo.start_round(MagicMock())

    assert result.round == 5
    assert rounds == [4, 5]
    assert cleared.call_args.args[1] == list(demo_seed.DEMO_ROOF_IDS)
    assert (result.deleted.contract_events, result.deleted.contract_states) == (6, 9)
    assert result.restored.contract_states == 9


def test_failed_round_start_records_no_round(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.repositories.demo.current_round", lambda _db: 1)
    monkeypatch.setattr(
        "app.repositories.demo.delete_chain_mirror", MagicMock(side_effect=RuntimeError)
    )
    add_round = MagicMock()
    monkeypatch.setattr("app.repositories.demo.add_round", add_round)
    db = MagicMock()

    with pytest.raises(RuntimeError):
        demo.start_round(db)

    add_round.assert_not_called()
    db.commit.assert_not_called()


def test_failed_reset_keeps_photos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.repositories.demo.list_measurement_ids", lambda _db, _ids: [uuid4()])
    failing_delete = MagicMock(side_effect=RuntimeError)
    monkeypatch.setattr("app.repositories.demo.delete_demo_rows", failing_delete)
    removed = MagicMock()
    monkeypatch.setattr(photos, "delete_measurement_photos", removed)

    with pytest.raises(RuntimeError):
        demo.reset_demo(MagicMock())

    removed.assert_not_called()


def test_delete_measurement_photos_counts_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(photos, "PHOTO_DIR", tmp_path)
    upload = tmp_path / "abc"
    upload.mkdir()
    (upload / "photo.jpg").write_bytes(b"x")
    (upload / "mask.png").write_bytes(b"y")

    assert photos.delete_measurement_photos("abc") == 2
    assert not upload.exists()
    assert photos.delete_measurement_photos("missing") == 0
