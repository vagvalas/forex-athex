"""Λήψη του xlsx τιμών κλεισίματος του ΧΑ και μετατροπή σε MetaStock ASCII.

Η μορφή εξόδου είναι κλειδωμένη από το tests/test_core.py (byte προς byte):
  <TICKER>,<DATE>,<CLOSE>,<VOL>,<HIGH>,<LOW>,<OPEN>,<PER>
  ημερομηνία ΜΜ/ΗΗ/ΕΕΕΕ, CRLF, UTF-8 χωρίς BOM, σύμβολα όπως τα δίνει το ΧΑ.
"""

import unicodedata
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

URL_TEMPLATE = (
    "https://www.athexgroup.gr/el/market-data/statistics/"
    "eod-closing-prices/regulated/stocks/0/{date_code}/xlsx"
)
OUTPUT_NAME = "athex_{date_code}.txt"
OUTPUT_ENCODING = "utf-8"
LINE_TERMINATOR = "\r\n"
DATE_FORMAT = "%m/%d/%Y"       # 11/06/2026 = 6 Νοε 2026 (όπως το αρχείο αναφοράς)
REQUEST_TIMEOUT = 30

# Στήλες του xlsx του ΧΑ -> στήλες MetaStock (με αυτή τη σειρά)
COLUMN_MAP = {
    "Σύμβολο": "<TICKER>",
    "Ημερομηνία": "<DATE>",
    "Τιμή": "<CLOSE>",
    "Όγκος": "<VOL>",
    "Ανώτερη": "<HIGH>",
    "Κατώτερη": "<LOW>",
    "Άνοιγμα": "<OPEN>",
}


class NotAvailable(Exception):
    """Το ΧΑ δεν έχει αρχείο για την ημέρα (αργία, δεν δημοσιεύτηκε ακόμα ή πολύ παλιά)."""


class FetchError(Exception):
    """Πρόβλημα δικτύου ή απρόσμενη απάντηση."""


def _nfc(text):
    return unicodedata.normalize("NFC", str(text)).strip()


def parse_date(text):
    """ΗΗ/ΜΜ/ΕΕΕΕ (δέχεται και 6/11/2026) -> date."""
    try:
        return datetime.strptime(text.strip(), "%d/%m/%Y").date()
    except ValueError:
        raise ValueError(f"Μη έγκυρη ημερομηνία «{text}». Μορφή: ΗΗ/ΜΜ/ΕΕΕΕ.") from None


def output_name(day: date) -> str:
    return OUTPUT_NAME.format(date_code=day.strftime("%Y%m%d"))


def fetch_xlsx(day: date, session=None) -> bytes:
    url = URL_TEMPLATE.format(date_code=day.strftime("%Y%m%d"))
    getter = session.get if session is not None else requests.get
    try:
        response = getter(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        raise FetchError(f"Αποτυχία σύνδεσης με το ΧΑ: {e}") from None
    content_type = response.headers.get("Content-Type", "")
    if response.status_code == 404:
        raise NotAvailable(day)
    if response.status_code != 200 or "html" in content_type:
        raise FetchError(f"Απρόσμενη απάντηση από το ΧΑ (HTTP {response.status_code}).")
    return response.content


def convert(xlsx_bytes: bytes) -> pd.DataFrame:
    """xlsx του ΧΑ -> DataFrame σε μορφή MetaStock (όλες οι τιμές ως κείμενο)."""
    df = pd.read_excel(BytesIO(xlsx_bytes), sheet_name=0, dtype=str)
    df.columns = [_nfc(c) for c in df.columns]

    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise ValueError(
            "Το αρχείο του ΧΑ άλλαξε μορφή. Λείπουν οι στήλες: "
            + ", ".join(missing)
            + "\nΣτήλες αρχείου: " + ", ".join(df.columns)
        )

    df = df[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)
    df = df.dropna(subset=["<TICKER>"])
    df["<TICKER>"] = df["<TICKER>"].map(_nfc)
    df["<DATE>"] = pd.to_datetime(df["<DATE>"], errors="coerce").dt.strftime(DATE_FORMAT)
    df["<PER>"] = "D"
    return df.reset_index(drop=True)


def to_txt_bytes(df: pd.DataFrame) -> bytes:
    text = df.to_csv(index=False, lineterminator=LINE_TERMINATOR)
    return text.encode(OUTPUT_ENCODING)


def write_txt(df: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(to_txt_bytes(df))
    tmp.replace(path)


def read_txt(path: Path) -> pd.DataFrame:
    """Διαβάζει ένα αρχείο εξόδου (για προεπισκόπηση / σύγκριση)."""
    return pd.read_csv(path, dtype=str, encoding=OUTPUT_ENCODING, keep_default_na=False)
