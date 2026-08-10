# -*- coding: utf-8 -*-
"""FileListController — управление списком загруженных чатов, фильтрацией и выбором."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Set

from PyQt6.QtCore import QObject, pyqtSignal

from ...core.models import ChatLog
from ...utils.logger import get_logger
from .project_controller import ProjectController

logger = get_logger()


class FileListController(QObject):
    """Контроллер загруженных файлов логов, фильтрации и навигации."""

    chatsChanged = pyqtSignal()
    currentChanged = pyqtSignal(object)  # ChatLog | None
    filtersChanged = pyqtSignal()

    def __init__(self, project_controller: ProjectController):
        super().__init__()
        self.project_controller = project_controller
        self.chats: List[ChatLog] = []
        self.current: Optional[ChatLog] = None

        self.show_extensions: bool = False
        self.show_diagnostics: bool = False

        self.category_filter: str = ""
        self.tag_filter: str = ""
        self.text_filter: str = ""

    def add_chat(self, chat: ChatLog) -> bool:
        if not chat or any(c.path == chat.path for c in self.chats):
            return False
        self.chats.append(chat)
        self.chatsChanged.emit()
        return True

    def add_chats(self, new_chats: List[ChatLog]) -> int:
        added = 0
        existing = {c.path for c in self.chats}
        for c in new_chats:
            if c.path not in existing:
                self.chats.append(c)
                existing.add(c.path)
                added += 1
        if added:
            self.chatsChanged.emit()
        return added

    def remove_chat(self, path: str):
        self.chats = [c for c in self.chats if c.path != path]
        if self.current and self.current.path == path:
            self.current = self.chats[0] if self.chats else None
            self.currentChanged.emit(self.current)
        self.chatsChanged.emit()

    def clear(self):
        self.chats.clear()
        self.current = None
        self.chatsChanged.emit()
        self.currentChanged.emit(None)
        logger.info("FileListController cleared")

    def select_chat_by_path(self, path: str | None):
        if not path:
            if self.current is not None:
                self.current = None
                self.currentChanged.emit(None)
            return
        chat = next((c for c in self.chats if c.path == path), None)
        if chat != self.current:
            self.current = chat
            self.currentChanged.emit(self.current)

    def select_chat(self, chat: ChatLog | None):
        if chat != self.current:
            self.current = chat
            self.currentChanged.emit(self.current)

    def set_filters(self, category: str = "", tag: str = "", text: str = ""):
        self.category_filter = category
        self.tag_filter = tag
        self.text_filter = text
        self.filtersChanged.emit()

    def passes_filters(self, chat: ChatLog) -> bool:
        cat = self.project_controller.get_category(chat)
        tags = self.project_controller.get_tags(chat)

        if self.category_filter == "__none__" and cat:
            return False
        if self.category_filter and self.category_filter != "__none__" and cat != self.category_filter:
            return False
        if self.tag_filter and self.tag_filter not in tags:
            return False
        if self.text_filter:
            q = self.text_filter.strip().lower()
            haystack = f"{chat.title} {chat.path} {chat.model} {cat} {' '.join(tags)}".lower()
            if q not in haystack:
                return False
        return True

    def get_filtered_chats(self) -> List[ChatLog]:
        return [c for c in self.chats if self.passes_filters(c)]

    def format_badge(self, chat: ChatLog, tr_func: Optional[Callable] = None) -> str:
        p = Path(chat.path) if chat.path else Path("")
        no_ext = (tr_func("no_extension") if tr_func else "no ext")
        ext = p.suffix.lower().lstrip(".") or no_ext
        kind = "JSON" if chat.source_format == "json" else "TXT"
        return f"{kind} · {ext}"
