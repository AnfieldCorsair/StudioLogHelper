# -*- coding: utf-8 -*-
"""ParseWorker — фоновый парсинг логов в отдельном потоке."""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

from PyQt6.QtCore import QThread, pyqtSignal

from ...core.exceptions import ParseError
from ...core.parsers.base import TextParseOptions
from ...core.parsers.parser import parse_file
from ...utils.logger import get_logger

logger = get_logger()


class ParseWorker(QThread):
    fileDone = pyqtSignal(object)  # ChatLog
    fileError = pyqtSignal(str, str)  # path, error
    allDone = pyqtSignal()
    progress = pyqtSignal(int, int, str)  # done, total, path

    def __init__(self, paths: Sequence[str | Path], text_opts: TextParseOptions | None = None):
        super().__init__()
        self.paths = [str(p) for p in paths]
        self.text_opts = text_opts or TextParseOptions()
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        total = len(self.paths)
        for i, p in enumerate(self.paths):
            if self._abort:
                break
            self.progress.emit(i, total, str(p))
            try:
                chat = parse_file(p, self.text_opts)
                self.fileDone.emit(chat)
            except (ParseError, OSError, ValueError, Exception) as ex:
                logger.warning("ParseWorker failed on %s: %s", p, ex)
                self.fileError.emit(p, str(ex))
        self.progress.emit(total, total, "")
        self.allDone.emit()
