from datetime import date
from pathlib import Path

import pytest

from athex import cli, core, settings

FIX = Path(__file__).parent / "fixtures"
XLSX = (FIX / "athex_20261106.xlsx").read_bytes()
TODAY = date(2026, 11, 10)


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    calls = []

    def fetch(day, session=None):
        calls.append(day)
        if day == date(2026, 11, 6):
            return XLSX
        raise core.NotAvailable(day)

    monkeypatch.setattr(core, "fetch_xlsx", fetch)
    monkeypatch.setattr(settings, "config_dir", lambda: tmp_path / "cfg")
    monkeypatch.setattr("athex.batch.REQUEST_DELAY", 0)
    return calls


def test_single_date(tmp_path, capsys):
    out = tmp_path / "out"
    assert cli.main(["06/11/2026", "--out", str(out)], today=TODAY) == 0
    assert (out / "athex_20261106.txt").read_bytes() == (FIX / "athex_20261106_expected.txt").read_bytes()
    assert "137 μετοχές" in capsys.readouterr().out
    assert "137 μετοχές" in (tmp_path / "cfg" / "athex.log").read_text(encoding="utf-8")


def test_weekend_date_does_nothing(tmp_path, isolate):
    assert cli.main(["08/11/2026", "--out", str(tmp_path)], today=TODAY) == 0
    assert isolate == []


def test_range(tmp_path, isolate):
    out = tmp_path / "out"
    assert cli.main(["--from", "05/11/2026", "--to", "09/11/2026", "--out", str(out)], today=TODAY) == 0
    assert isolate == [date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 9)]
    assert [p.name for p in out.glob("athex_*.txt")] == ["athex_20261106.txt"]


def test_update_then_nothing_left_except_unpublished(tmp_path, isolate):
    out = tmp_path / "out"
    cli.main(["--update", "--out", str(out)], today=TODAY)
    first = len(isolate)
    isolate.clear()
    cli.main(["--update", "--out", str(out)], today=TODAY)
    assert first == 15                         # εργάσιμες 21/10 .. 10/11
    assert isolate == [TODAY]                  # οι υπόλοιπες: αρχείο ή γνωστή αργία


def test_bad_date_exits_with_error(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["2026-11-06", "--out", str(tmp_path)], today=TODAY)
