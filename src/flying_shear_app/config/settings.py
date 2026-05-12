"""Persistent JSON settings for the Flying Shear setup app."""

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SETTINGS_FILE = PROJECT_ROOT / "setup_settings.json"


def load_settings():
    """Load settings from the project JSON file."""
    if SETTINGS_FILE.exists():
        try:
            with SETTINGS_FILE.open("r", encoding="utf-8") as f:
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
