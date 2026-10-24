"""The guards run against a fake session: a real database must never be touched here."""

import sys
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

import reset


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    fake.scalar.return_value = 42
    fake.execute.return_value = [("measured", 42)]
    monkeypatch.setattr(reset, "SessionLocal", lambda: nullcontext(fake))
    monkeypatch.setattr(reset.seed, "main", MagicMock())
    return fake


def run(monkeypatch: pytest.MonkeyPatch, argv: list[str], answer: str | None = None) -> None:
    monkeypatch.setattr(sys, "argv", ["reset.py", *argv])

    def fake_input(_prompt: str) -> str:
        if answer is None:
            raise EOFError
        return answer

    monkeypatch.setattr("builtins.input", fake_input)
    reset.main()


def test_without_force_nothing_is_deleted(
    monkeypatch: pytest.MonkeyPatch, session: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit, match="--force"):
        run(monkeypatch, [], answer="RESET")

    session.commit.assert_not_called()
    reset.seed.main.assert_not_called()
    assert "roofs" in capsys.readouterr().out


@pytest.mark.parametrize("answer", ["reset", "yes", "", None])
def test_wrong_or_missing_confirmation_deletes_nothing(
    monkeypatch: pytest.MonkeyPatch, session: MagicMock, answer: str | None
) -> None:
    with pytest.raises(SystemExit, match="Nothing was deleted"):
        run(monkeypatch, ["--force"], answer=answer)

    session.commit.assert_not_called()
    reset.seed.main.assert_not_called()


def test_force_and_confirmation_reset_and_reseed(
    monkeypatch: pytest.MonkeyPatch, session: MagicMock
) -> None:
    run(monkeypatch, ["--force"], answer="RESET")

    session.commit.assert_called_once()
    reset.seed.main.assert_called_once()
