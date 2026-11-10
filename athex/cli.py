"""Γραμμή εντολών.

  athex_to_metastock.py 06/11/2026                     μία ημέρα
  athex_to_metastock.py --from 20/10/2026 --to 06/11/2026
  athex_to_metastock.py --update                       ό,τι λείπει (για Χρονοπρογραμματιστή Windows)
  επιλογές: --out ΦΑΚΕΛΟΣ   --overwrite
"""

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import __version__, batch, core, settings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="athex_to_metastock",
        description="Λήψη τιμών κλεισίματος ΧΑ και αποθήκευση σε MetaStock txt.",
    )
    p.add_argument("date", nargs="?", help="ημερομηνία ΗΗ/ΜΜ/ΕΕΕΕ")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--from", dest="date_from", metavar="ΗΗ/ΜΜ/ΕΕΕΕ", help="αρχή εύρους")
    p.add_argument("--to", dest="date_to", metavar="ΗΗ/ΜΜ/ΕΕΕΕ", help="τέλος εύρους (προεπιλογή: σήμερα)")
    p.add_argument("--update", "--catch-up", dest="update", action="store_true",
                   help=f"κατέβασε ό,τι λείπει από τις τελευταίες {batch.WINDOW_DAYS} ημέρες")
    p.add_argument("--out", metavar="ΦΑΚΕΛΟΣ", help="φάκελος εξόδου (προεπιλογή: από τις ρυθμίσεις)")
    p.add_argument("--overwrite", action="store_true", help="ξαναγράψε όσα αρχεία υπάρχουν ήδη")
    return p


def _say(line: str) -> None:
    if sys.stdout is not None:
        print(line, flush=True)
    try:
        log = settings.log_path()
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {line}\n")
    except OSError:
        pass


def format_result(r: batch.DayResult) -> str:
    text = f"{r.day:%d/%m/%Y}  {r.label}"
    if r.rows:
        text += f"  ({r.rows} μετοχές)"
    if r.notes:
        text += "  · " + " · ".join(r.notes)
    return text


def main(argv=None, today: date | None = None) -> int:
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    today = today or date.today()
    out = Path(args.out) if args.out else settings.output_dir()

    try:
        if args.update:
            days = batch.pending_days(out, today)
        elif args.date_from or args.date_to:
            start = core.parse_date(args.date_from or args.date_to)
            end = core.parse_date(args.date_to) if args.date_to else today
            if start > end:
                parser.error("η αρχή του εύρους είναι μετά το τέλος")
            days = batch.weekdays(start, end)
        elif args.date:
            day = core.parse_date(args.date)
            if day.weekday() >= 5:
                _say(f"{day:%d/%m/%Y} είναι Σαββατοκύριακο — δεν υπάρχει συνεδρίαση.")
                return 0
            days = [day]
        else:
            parser.error("δώσε ημερομηνία, --from/--to ή --update")
    except ValueError as e:
        parser.error(str(e))

    if not days:
        _say(f"Όλα ενημερωμένα στον φάκελο {out}")
        return 0
    if min(days) < today - timedelta(days=batch.WINDOW_DAYS):
        _say("Σημείωση: το ΧΑ κρατά μόνο τις τελευταίες ~3 εβδομάδες· παλαιότερες ημέρες δεν θα βρεθούν.")

    _say(f"Φάκελος: {out}  ·  {len(days)} ημέρες")
    results = batch.run_days(days, out, today=today, overwrite=args.overwrite,
                             progress=lambda i, n, r: _say(format_result(r)))
    return 1 if any(r.status == batch.ERROR for r in results) else 0
