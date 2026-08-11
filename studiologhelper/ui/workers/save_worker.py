# -*- coding: utf-8 -*-
"""save_worker.py — Асинхронный воркер атомарного сохранения проектов в фоновом потоке."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from PyQt6.QtCore import QThread, pyqtSignal
except ImportError:
    class QThread:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            self.run()
        def wait(self):
            pass
        def isRunning(self):
            return False

    class _Signal:
        def __init__(self, *args, **kwargs):
            self._handlers = []
        def connect(self, handler):
            self._handlers.append(handler)
        def emit(self, *args, **kwargs):
            for h in list(self._handlers):
                try:
                    h(*args, **kwargs)
                except TypeError:
                    try:
                        h()
                    except Exception:
                        pass

    def pyqtSignal(*args, **kwargs):  # type: ignore
        return _Signal()

from ...core.project import Project
from ...utils.logger import get_logger

logger = get_logger()


class SaveProjectWorker(QThread):
    """Фоновый воркер атомарной записи проекта на диск."""

    savedDone = pyqtSignal(str)  # file_path
    savedError = pyqtSignal(str, str)  # file_path, error

    def __init__(self, project_snapshot: Project, file_path: str | Path):
        super().__init__()
        self.snapshot = project_snapshot
        self.file_path = Path(file_path)

    def run(self):
        try:
            self.snapshot.save(self.file_path, create_backup=True)
            self.savedDone.emit(str(self.file_path))
        except Exception as ex:
            logger.error("SaveProjectWorker failed for %s: %s", self.file_path, ex)
            self.savedError.emit(str(self.file_path), str(ex))
