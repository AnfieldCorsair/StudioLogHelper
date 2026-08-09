# -*- coding: utf-8 -*-
"""Воркер для экспорта с прогрессом."""

from PyQt6.QtCore import QThread, pyqtSignal
from pathlib import Path


class ExportWorker(QThread):
    progress = pyqtSignal(int, int, str)  # done, total, current file name
    fileDone = pyqtSignal(str, list)  # chat title, created paths
    error = pyqtSignal(str, str)  # chat title, error
    allDone = pyqtSignal(list, list)  # created all, errors

    def __init__(self, chats, opts, out_dir):
        super().__init__()
        self.chats = chats
        self.opts = opts
        self.out_dir = Path(out_dir)
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        from ...core.exporters.manager import export_to_files

        created_all = []
        errors = []
        total = len(self.chats)
        for i, chat in enumerate(self.chats):
            if self._abort:
                break
            self.progress.emit(i, total, chat.title)
            try:
                paths = export_to_files(chat, self.opts, self.out_dir)
                created_all.extend(paths)
                self.fileDone.emit(chat.title, paths)
            except Exception as ex:
                err = f"{chat.title}: {ex}"
                errors.append(err)
                self.error.emit(chat.title, str(ex))
        self.progress.emit(total, total, "")
        self.allDone.emit(created_all, errors)
