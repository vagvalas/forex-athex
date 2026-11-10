"""Λήψη πολλών ημερών: εύρος ημερομηνιών, «Ενημέρωση» (ό,τι λείπει), αρχείο raw, έλεγχοι.

Το ΧΑ κρατά μόνο τις τελευταίες ~3 εβδομάδες. 404 για μια πρόσφατη ημέρα
σημαίνει «χωρίς συνεδρίαση» (αργία) και καταγράφεται, ώστε να μη ζητηθεί ξανά.
"""

import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import requests

from . import core

WINDOW_DAYS = 20            # πόσες ημέρες πίσω κρατά με σιγουριά το ΧΑ
REQUEST_DELAY = 0.7         # δευτερόλεπτα ανάμεσα σε αιτήματα
RAW_DIRNAME = "_raw"        # αντίγραφα των xlsx του ΧΑ + καταγραφή αργιών
NO_SESSION_FILE = "no_session.txt"

OK = "ok"
EXISTS = "exists"
NO_SESSION = "no_session"
NOT_PUBLISHED = "not_published"
UNAVAILABLE = "unavailable"
ERROR = "error"

STATUS_LABELS = {
    OK: "✓ Αποθηκεύτηκε",
    EXISTS: "Υπάρχει ήδη",
    NO_SESSION: "Χωρίς συνεδρίαση (αργία)",
    NOT_PUBLISHED: "Δεν έχει δημοσιευτεί ακόμα",
    UNAVAILABLE: "Μη διαθέσιμη (αργία ή παλαιότερη των ~3 εβδομάδων)",
    ERROR: "Σφάλμα",
}

_FILE_RE = re.compile(r"^athex_(\d{8})\.txt$")


@dataclass
class DayResult:
    day: date
    status: str
    rows: int = 0
    path: Path | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return STATUS_LABELS[self.status]


# --- ημερομηνίες / αρχεία ------------------------------------------------------

def weekdays(start: date, end: date) -> list[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def last_weekday(today: date) -> date:
    d = today
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def existing_files(out_dir: Path) -> dict[date, Path]:
    found = {}
    if Path(out_dir).is_dir():
        for p in Path(out_dir).iterdir():
            m = _FILE_RE.match(p.name)
            if m:
                y, mo, d = m.group(1)[:4], m.group(1)[4:6], m.group(1)[6:]
                found[date(int(y), int(mo), int(d))] = p
    return found


def _raw_dir(out_dir: Path) -> Path:
    return Path(out_dir) / RAW_DIRNAME


def known_no_session(out_dir: Path) -> set[date]:
    f = _raw_dir(out_dir) / NO_SESSION_FILE
    if not f.exists():
        return set()
    days = set()
    for line in f.read_text(encoding="utf-8").split():
        try:
            days.add(date(int(line[:4]), int(line[4:6]), int(line[6:8])))
        except ValueError:
            pass
    return days


def _record_no_session(out_dir: Path, day: date) -> None:
    if day in known_no_session(out_dir):
        return
    raw = _raw_dir(out_dir)
    raw.mkdir(parents=True, exist_ok=True)
    with open(raw / NO_SESSION_FILE, "a", encoding="utf-8") as f:
        f.write(day.strftime("%Y%m%d") + "\n")


def pending_days(out_dir: Path, today: date) -> list[date]:
    """Εργάσιμες των τελευταίων WINDOW_DAYS ημερών που δεν έχουμε ακόμα (μαζί με σήμερα)."""
    have = existing_files(out_dir)
    skip = known_no_session(out_dir)
    start = today - timedelta(days=WINDOW_DAYS)
    return [d for d in weekdays(start, today) if d not in have and d not in skip]


# --- έλεγχοι ---------------------------------------------------------------------

def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sanity_notes(df, prev_df=None) -> list[str]:
    """Σύντομες παρατηρήσεις για ύποπτα δεδομένα (δεν σταματούν τη λήψη)."""
    notes = []
    empty_close = int((df["<CLOSE>"].fillna("").astype(str).str.strip() == "").sum())
    if empty_close:
        notes.append(f"{empty_close} χωρίς τιμή κλεισίματος")

    outside = 0
    for close, high, low, vol in zip(df["<CLOSE>"], df["<HIGH>"], df["<LOW>"], df["<VOL>"]):
        c, h, lo, v = map(_to_float, (close, high, low, vol))
        if None not in (c, h, lo, v) and v > 0 and not (lo <= c <= h):
            outside += 1
    if outside:
        notes.append(f"{outside} με κλείσιμο εκτός εύρους ημέρας")

    if prev_df is not None:
        n, p = len(df), len(prev_df)
        if abs(n - p) > max(5, p * 0.1):
            notes.append(f"⚠ {n} μετοχές (προηγούμενη ημέρα: {p})")
        cur, prev = set(df["<TICKER>"]), set(prev_df["<TICKER>"])
        gone, new = sorted(prev - cur), sorted(cur - prev)
        if gone:
            notes.append("Λείπουν: " + _short_list(gone))
        if new:
            notes.append("Νέες: " + _short_list(new))
    return notes


def _short_list(items, limit=5):
    text = ", ".join(items[:limit])
    return text + (f" (+{len(items) - limit})" if len(items) > limit else "")


def _previous_df(out_dir: Path, day: date):
    earlier = [d for d in existing_files(out_dir) if d < day]
    if not earlier:
        return None
    try:
        return core.read_txt(existing_files(out_dir)[max(earlier)])
    except Exception:
        return None


# --- εκτέλεση ----------------------------------------------------------------------

def run_days(days, out_dir: Path, *, today: date, overwrite=False,
             progress=None, cancel=None, fetch=None,
             delay=None, sleep=time.sleep) -> list[DayResult]:
    """Κατεβάζει/μετατρέπει τις ημέρες με χρονολογική σειρά.

    progress(i, total, DayResult) καλείται μετά από κάθε ημέρα.
    cancel: αντικείμενο με is_set() (π.χ. threading.Event) για διακοπή.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fetch = fetch or core.fetch_xlsx
    delay = REQUEST_DELAY if delay is None else delay
    days = sorted(set(d for d in days if d.weekday() < 5))
    results, session, requested = [], requests.Session(), False

    for i, day in enumerate(days, 1):
        if cancel is not None and cancel.is_set():
            break
        path = out_dir / core.output_name(day)

        if path.exists() and not overwrite:
            result = DayResult(day, EXISTS, rows=_count_rows(path), path=path)
        else:
            if requested and delay:
                sleep(delay)
            requested = True
            result = _fetch_one(day, path, out_dir, today, fetch, session)

        results.append(result)
        if progress:
            progress(i, len(days), result)
    return results


def _fetch_one(day, path, out_dir, today, fetch, session) -> DayResult:
    try:
        xlsx = fetch(day, session)
    except core.NotAvailable:
        age = (today - day).days
        if age <= 0:
            return DayResult(day, NOT_PUBLISHED)
        if age <= WINDOW_DAYS:
            _record_no_session(out_dir, day)
            return DayResult(day, NO_SESSION)
        return DayResult(day, UNAVAILABLE)
    except core.FetchError as e:
        return DayResult(day, ERROR, notes=[str(e)])

    try:
        df = core.convert(xlsx)
    except Exception as e:
        return DayResult(day, ERROR, notes=[f"Μετατροπή: {e}"])

    raw = _raw_dir(out_dir)
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"athex_{day:%Y%m%d}.xlsx").write_bytes(xlsx)

    notes = sanity_notes(df, _previous_df(out_dir, day))
    core.write_txt(df, path)
    return DayResult(day, OK, rows=len(df), path=path, notes=notes)


def _count_rows(path: Path) -> int:
    with open(path, "rb") as f:
        return max(sum(1 for _ in f) - 1, 0)
