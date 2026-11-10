from datetime import date
from pathlib import Path

from athex import batch, core

FIX = Path(__file__).parent / "fixtures"
XLSX = (FIX / "athex_20261106.xlsx").read_bytes()
TODAY = date(2026, 11, 10)          # Τρίτη


def fake_fetch(available, calls=None):
    """available: σύνολο ημερών για τις οποίες «υπάρχει» xlsx· οι υπόλοιπες → 404."""
    def fetch(day, session=None):
        if calls is not None:
            calls.append(day)
        if day in available:
            return XLSX
        raise core.NotAvailable(day)
    return fetch


def run(days, out, available, **kw):
    calls = []
    results = batch.run_days(days, out, today=TODAY, fetch=fake_fetch(available, calls),
                             delay=0, **kw)
    return results, calls


def test_weekdays_skip_weekends():
    days = batch.weekdays(date(2026, 11, 6), date(2026, 11, 10))
    assert days == [date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10)]


def test_last_weekday():
    assert batch.last_weekday(date(2026, 11, 8)) == date(2026, 11, 6)   # Κυριακή -> Παρασκευή
    assert batch.last_weekday(TODAY) == TODAY


def test_downloads_writes_txt_and_raw(tmp_path):
    results, _ = run([date(2026, 11, 6)], tmp_path, {date(2026, 11, 6)})
    r = results[0]
    assert r.status == batch.OK and r.rows == 137
    assert (tmp_path / "athex_20261106.txt").read_bytes() == (FIX / "athex_20261106_expected.txt").read_bytes()
    assert (tmp_path / "_raw" / "athex_20261106.xlsx").read_bytes() == XLSX


def test_existing_file_is_skipped_without_request(tmp_path):
    run([date(2026, 11, 6)], tmp_path, {date(2026, 11, 6)})
    results, calls = run([date(2026, 11, 6)], tmp_path, {date(2026, 11, 6)})
    assert results[0].status == batch.EXISTS and results[0].rows == 137
    assert calls == []


def test_overwrite_refetches(tmp_path):
    run([date(2026, 11, 6)], tmp_path, {date(2026, 11, 6)})
    results, calls = run([date(2026, 11, 6)], tmp_path, {date(2026, 11, 6)}, overwrite=True)
    assert results[0].status == batch.OK and calls == [date(2026, 11, 6)]


def test_404_classification(tmp_path):
    days = [date(2026, 10, 1), date(2026, 10, 28), TODAY]
    results, _ = run(days, tmp_path, set())
    status = {r.day: r.status for r in results}
    assert status[date(2026, 10, 1)] == batch.UNAVAILABLE      # παλαιότερη από το παράθυρο
    assert status[date(2026, 10, 28)] == batch.NO_SESSION      # αργία μέσα στο παράθυρο
    assert status[TODAY] == batch.NOT_PUBLISHED
    assert batch.known_no_session(tmp_path) == {date(2026, 10, 28)}


def test_pending_days_skips_existing_and_holidays(tmp_path):
    run([date(2026, 10, 28)], tmp_path, set())                 # καταγράφεται ως αργία
    run([date(2026, 11, 6)], tmp_path, {date(2026, 11, 6)})
    pending = batch.pending_days(tmp_path, TODAY)
    assert pending[0] == date(2026, 10, 21)                    # 20 ημέρες πίσω
    assert pending[-1] == TODAY
    assert date(2026, 10, 28) not in pending
    assert date(2026, 11, 6) not in pending
    assert all(d.weekday() < 5 for d in pending)


def test_weekends_are_never_requested(tmp_path):
    results, calls = run([date(2026, 11, 7), date(2026, 11, 8)], tmp_path, set())
    assert results == [] and calls == []


def test_cancel_stops(tmp_path):
    class Cancel:
        def is_set(self):
            return True
    results, calls = run([date(2026, 11, 6)], tmp_path, {date(2026, 11, 6)}, cancel=Cancel())
    assert results == [] and calls == []


def test_sanity_notes_compare_with_previous_day():
    df = core.convert(XLSX)
    prev = df.copy()
    prev.loc[len(prev)] = ["ΠΑΛΙΑ", "", "1", "1", "1", "1", "1", "D"]
    cur = df[df["<TICKER>"] != "ΧΑΙΔΕ"].copy()
    notes = batch.sanity_notes(cur, prev)
    assert "Λείπουν: ΠΑΛΙΑ, ΧΑΙΔΕ" in notes
    # Πραγματικά δεδομένα 6/11: ΑΑΑΚ, ΜΟΥΖΚ, ΜΠΛΕΚΕΔΡΟΣ, ΦΛΕΞΟ κλείνουν εκτός εύρους ημέρας
    assert "4 με κλείσιμο εκτός εύρους ημέρας" in batch.sanity_notes(df)


def test_progress_callback(tmp_path):
    seen = []
    batch.run_days([date(2026, 11, 6), TODAY], tmp_path, today=TODAY,
                   fetch=fake_fetch({date(2026, 11, 6)}), delay=0,
                   progress=lambda i, n, r: seen.append((i, n, r.status)))
    assert seen == [(1, 2, batch.OK), (2, 2, batch.NOT_PUBLISHED)]
