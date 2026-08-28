"""Standalone entry point for the Profile CAMBOX Generator."""

import os
from pathlib import Path
import shutil
import sys
import zipfile


def _configure_frozen_flet_client() -> None:
    if not getattr(sys, "frozen", False):
        return
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    archive_path = bundle_root / "flet_desktop" / "app" / "flet-windows.zip"
    if not archive_path.exists():
        return
    client_root = bundle_root / "profile_cambox_flet_client"
    flet_view_path = client_root / "flet"
    flet_exe_path = flet_view_path / "flet.exe"
    if not flet_exe_path.exists():
        if client_root.exists():
            shutil.rmtree(client_root, ignore_errors=True)
        client_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, "r") as archive:
            for member in archive.infolist():
                target = client_root / member.filename
                if not target.resolve().is_relative_to(client_root.resolve()):
                    raise RuntimeError(f"Unsafe Flet archive member: {member.filename}")
            archive.extractall(client_root)
    if flet_exe_path.exists():
        os.environ["FLET_VIEW_PATH"] = str(flet_view_path)


_configure_frozen_flet_client()

import flet as ft

from src.profile_cambox_app.app import main


if __name__ == "__main__":
    ft.run(main)
