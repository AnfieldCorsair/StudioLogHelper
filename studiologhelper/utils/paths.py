# -*- coding: utf-8 -*-
"""Кроссплатформенные пути для конфигов, индексов, логов."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PyQt6.QtCore import QStandardPaths
    HAS_QT = True
except ImportError:
    try:
        from PySide6.QtCore import QStandardPaths
        HAS_QT = True
    except ImportError:
        HAS_QT = False


def get_app_data_dir(app_name: str = "StudioLogHelper") -> Path:
    """Возвращает кросс-платформенный путь для данных приложения.

    Windows: %APPDATA%/StudioLogHelper
    Linux: ~/.local/share/StudioLogHelper или XDG_DATA_HOME
    macOS: ~/Library/Application Support/StudioLogHelper
    """
    if HAS_QT:
        try:
            base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
            if base:
                p = Path(base)
                # Qt gives .../StudioLogHelper on all platforms already
                p.mkdir(parents=True, exist_ok=True)
                return p
        except Exception:
            pass

    # Fallback без Qt
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Roaming" / app_name
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / app_name
    else:
        # XDG
        import os
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            base = Path(xdg) / app_name
        else:
            base = Path.home() / ".local" / "share" / app_name
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_index_db_path(app_name: str = "StudioLogHelper") -> Path:
    return get_app_data_dir(app_name) / "index.db"


def get_config_dir(app_name: str = "StudioLogHelper") -> Path:
    if HAS_QT:
        try:
            base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
            if base:
                p = Path(base)
                p.mkdir(parents=True, exist_ok=True)
                return p
        except Exception:
            pass
    # fallback same as data dir for simplicity
    return get_app_data_dir(app_name)


def reveal_in_file_manager(path: Path | str) -> bool:
    """Кроссплатформенное 'Показать в проводнике'. Возвращает успеха."""
    import subprocess
    import sys

    p = Path(path)
    if not p.exists():
        p = p.parent
    if not p.exists():
        return False

    try:
        if sys.platform == "win32":
            # explorer /select, for file, or open dir
            if p.is_file():
                # Use explorer /select,"path" — Note: path with comma needs quoting
                subprocess.Popen(["explorer", f"/select,{str(p)}"])
            else:
                subprocess.Popen(["explorer", str(p)])
            return True
        elif sys.platform == "darwin":
            if p.is_file():
                subprocess.Popen(["open", "-R", str(p)])
            else:
                subprocess.Popen(["open", str(p)])
            return True
        else:
            # Linux: try xdg-open, then fallback to Qt if available
            if p.is_file():
                target = str(p.parent)
            else:
                target = str(p)
            try:
                subprocess.Popen(["xdg-open", target])
                return True
            except FileNotFoundError:
                pass
            # fallback: try gio, nautilus
            try:
                # Qt fallback will be handled in UI layer
                return False
            except Exception:
                return False
    except Exception:
        return False
