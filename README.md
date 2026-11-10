# ATHEX → MetaStock

Downloads the Athens Stock Exchange end-of-day closing prices (xlsx) and saves one MetaStock ASCII
file per day: `athex_YYYYMMDD.txt`, UTF-8, Greek tickers exactly as ATHEX publishes them.

```
<TICKER>,<DATE>,<CLOSE>,<VOL>,<HIGH>,<LOW>,<OPEN>,<PER>
ΑΛΦΑ,11/06/2026,4.53,7506537,4.678,4.53,4.572,D
```

Dates are `MM/DD/YYYY`, line endings CRLF, no BOM. `tests/test_core.py` locks this format byte-for-byte
against a reference file.

> ATHEX only keeps the **last ~3 weeks**. Run **Ενημέρωση** (Update) at least every 3 weeks, or older
> days are lost for good.

## Windows app

Download the `ATHEX-windows` artifact from the latest **Build Windows exe** run under *Actions*, unzip
it, and run `ATHEX.exe`. Keep the whole folder together. Windows SmartScreen will warn once
("More info → Run anyway") because the exe isn't signed.

- **Ενημέρωση**: downloads every missing day from the last ~3 weeks. Holidays are detected and remembered.
- **Συγκεκριμένες ημέρες**: From/To date range, with an optional overwrite.
- **Προεπισκόπηση**: preview any saved day, with search and sorting.
- The output folder defaults to `Documents\ATHEX`. The original xlsx files are kept in `_raw\`.

Command line (also usable from Windows Task Scheduler; output is logged to `%APPDATA%\athex_metastock\athex.log`):

```
ATHEX.exe 06/11/2026
ATHEX.exe --from 20/10/2026 --to 06/11/2026
ATHEX.exe --update [--out FOLDER] [--overwrite]
```

## Development

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-build.txt
.venv/bin/python -m pytest -q
.venv/bin/python athex_to_metastock.py          # window
```

| File | Purpose |
|---|---|
| `athex/core.py` | download + convert (format locked by tests) |
| `athex/batch.py` | date ranges, update, holidays, raw archive, data checks |
| `athex/cli.py`, `athex/gui.py` | command line, ttkbootstrap window |
| `.github/workflows/build-windows.yml` | tests + PyInstaller build on Windows |
| `build_windows.bat` | same build on a local Windows PC |
