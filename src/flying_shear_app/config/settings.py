"""Persistent JSON settings for the Flying Shear setup app."""

import json
import sys
from pathlib import Path


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT = _project_root()
SETTINGS_FILE = PROJECT_ROOT / "setup_settings.json"


def _bundled_settings_file() -> Path | None:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if not bundle_root:
        return None
    candidate = Path(bundle_root) / "setup_settings.json"
    return candidate if candidate.exists() else None


def load_settings():
    """Load settings from the project JSON file."""
    for settings_file in (SETTINGS_FILE, _bundled_settings_file()):
        if settings_file is None or not settings_file.exists():
            continue
        try:
            with settings_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(settings):
    """Save settings to the project JSON file."""
    try:
        with SETTINGS_FILE.open("w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError as e:
        print(f"Warning: Could not save settings: {e}")
