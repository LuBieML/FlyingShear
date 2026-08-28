"""Persistent settings for the standalone profile generator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .domain import ProfileConfig


def app_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


SETTINGS_FILE = app_directory() / "profile_cambox_settings.json"


def load_config() -> ProfileConfig:
    if not SETTINGS_FILE.exists():
        return ProfileConfig()
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        allowed = ProfileConfig.__dataclass_fields__
        return ProfileConfig(**{key: value for key, value in data.items() if key in allowed})
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return ProfileConfig()


def save_config(config: ProfileConfig) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Could not save settings: {exc}") from exc
