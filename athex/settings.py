"""Ρυθμίσεις χρήστη (φάκελος εξόδου) — %APPDATA%\\athex_metastock\\settings.json στα Windows."""

import json
import os
import sys
from pathlib import Path

APP_DIRNAME = "athex_metastock"


def config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_DIRNAME


def log_path() -> Path:
    return config_dir() / "athex.log"


def default_output_dir() -> Path:
    return Path.home() / "Documents" / "ATHEX"


def _file() -> Path:
    return config_dir() / "settings.json"


def load() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(data: dict) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def output_dir() -> Path:
    value = load().get("output_dir")
    return Path(value) if value else default_output_dir()


def set_output_dir(path) -> None:
    data = load()
    data["output_dir"] = str(Path(path))
    save(data)
