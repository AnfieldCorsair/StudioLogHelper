# -*- coding: utf-8 -*-
"""search_worker.py — Асинхронный воркер поиска в фоновом потоке с отменой устаревших запросов."""

from __future__ import annotations

import time
from typing import Any, List, Optional

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

from ...core.models import ChatLog
from ...indexer.hybrid_search import HybridHit, HybridSearchEngine
from ...indexer.index import SearchHit, SearchIndex
from ...utils.logger import get_logger

logger = get_logger()


class SearchWorker(QThread):
    """Фоновый воркер выполнения поиска с отменой устаревших запросов."""

    resultsReady = pyqtSignal(list)
    searchFinished = pyqtSignal(int, float)  # count, elapsed_ms
    searchError = pyqtSignal(str)

    def __init__(
        self,
        mode: str,
        query: str,
        chats: Optional[List[ChatLog]] = None,
        search_index: Optional[SearchIndex] = None,
        scope: str = "all",
        where: str = "loaded",
        hybrid_engine: Optional[HybridSearchEngine] = None,
    ):
        super().__init__()
        self.mode = mode
        self.query = query.strip()
        self.chats = list(chats or [])
        self.search_index = search_index
        self.scope = scope
        self.where = where
        self.hybrid_engine = hybrid_engine or HybridSearchEngine()
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        if not self.query:
            self.resultsReady.emit([])
            self.searchFinished.emit(0, 0.0)
            return

        t0 = time.perf_counter()

        try:
            if self.mode == "hybrid_chats":
                if self._abort:
                    return
                hits = self.hybrid_engine.search_chats(self.chats, self.query, scope=self.scope, limit=300)
                if self._abort:
                    return
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                self.resultsReady.emit(hits)
                self.searchFinished.emit(len(hits), elapsed_ms)

            elif self.mode == "index":
                if self._abort or not self.search_index:
                    return

                role, thoughts, kind = None, None, None
                if self.scope == "user":
                    role, thoughts = "user", False
                elif self.scope == "model":
                    role, thoughts = "model", False
                elif self.scope == "thoughts":
                    thoughts = True

                if self.where == "index_txt":
                    kind = "txt"
                elif self.where == "index_json":
                    kind = "log"

                hits = self.search_index.search(self.query, role=role, thoughts=thoughts, kind=kind, limit=300)
                if self._abort:
                    return

                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                self.resultsReady.emit(hits)
                self.searchFinished.emit(len(hits), elapsed_ms)

        except Exception as ex:
            if not self._abort:
                logger.error("SearchWorker error: %s", ex)
                self.searchError.emit(str(ex))
