from datetime import date
from pathlib import Path

import pytest

from athex import core

FIX = Path(__file__).parent / "fixtures"
XLSX = FIX / "athex_20261106.xlsx"
EXPECTED = FIX / "athex_20261106_expected.txt"            # ελληνικά σύμβολα
REFERENCE = FIX / "athex_20261106_reference_latin.txt"    # το αρχικό αρχείο του χρήστη


def converted_bytes():
    return core.to_txt_bytes(core.convert(XLSX.read_bytes()))


def test_output_is_byte_identical_to_expected():
    assert converted_bytes() == EXPECTED.read_bytes()


def test_only_tickers_differ_from_users_reference_file():
    new_lines = converted_bytes().split(b"\r\n")
    ref_lines = REFERENCE.read_bytes().split(b"\r\n")
    assert len(new_lines) == len(ref_lines)
    for new, ref in zip(new_lines, ref_lines):
        assert new.partition(b",")[2] == ref.partition(b",")[2]


def test_format_details():
    data = converted_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")                     # χωρίς BOM
    assert data.count(b"\r\n") == data.count(b"\n")                 # μόνο CRLF
    lines = data.decode("utf-8").splitlines()
    assert lines[0] == "<TICKER>,<DATE>,<CLOSE>,<VOL>,<HIGH>,<LOW>,<OPEN>,<PER>"
    assert lines[-1] == "ΧΑΙΔΕ,11/06/2026,1.17,318,1.21,0.99,0.99,D"


def test_write_and_read_roundtrip(tmp_path):
    df = core.convert(XLSX.read_bytes())
    path = tmp_path / core.output_name(date(2026, 11, 6))
    core.write_txt(df, path)
    assert path.name == "athex_20261106.txt"
    assert path.read_bytes() == EXPECTED.read_bytes()
    assert len(core.read_txt(path)) == 137


@pytest.mark.parametrize("text, expected", [
    ("06/11/2026", date(2026, 11, 6)),
    ("6/11/2026", date(2026, 11, 6)),
    (" 06/11/2026 ", date(2026, 11, 6)),
])
def test_parse_date(text, expected):
    assert core.parse_date(text) == expected


@pytest.mark.parametrize("text", ["2026-11-06", "32/01/2026", "", "06/13/2026"])
def test_parse_date_rejects(text):
    with pytest.raises(ValueError):
        core.parse_date(text)
