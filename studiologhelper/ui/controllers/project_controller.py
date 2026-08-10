# -*- coding: utf-8 -*-
"""ProjectController — управление проектами .slh.json, иерархическими категориями, тегами, заметками, закладками, цитатами и автосохранением."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    from PyQt6.QtCore import QObject, QSettings, QTimer, pyqtSignal
except ImportError:
    class QObject:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

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

    class QSettings:  # type: ignore
        pass

    class QTimer:  # type: ignore
        def __init__(self, parent=None):
            pass
        def setSingleShot(self, val):
            pass
        def start(self, ms=0):
            pass
        def stop(self):
            pass

from ...core.models import ChatLog
from ...core.project import (
    HIGHLIGHT_COLORS,
    Project,
    ProjectBookmark,
    ProjectFile,
    matches_hierarchical_category,
)
from ...utils.logger import get_logger
from ..undo import Command, UndoManager

logger = get_logger()


class ProjectController(QObject):
    """Контроллер проектов, иерархических категорий, тегов, закладок, цитат-маркеров и автосохранения."""

    projectChanged = pyqtSignal()
    metadataChanged = pyqtSignal(str)  # chat_path
    categoriesChanged = pyqtSignal()
    bookmarksChanged = pyqtSignal(str)  # chat_path
    autoSaved = pyqtSignal(str)  # project_path

    def __init__(self, settings: Any, undo_manager: UndoManager | None = None):
        super().__init__()
        self.settings = settings
        self.undo_manager = undo_manager or UndoManager()

        self.current_project_path: str = ""
        self.current_project_name: str = ""
        self.auto_save_enabled: bool = True
        self._cached_chats_ref: List[ChatLog] = []

        self.chat_categories: Dict[str, str] = self._load_json("org/chat_categories", {})
        self.chat_notes: Dict[str, str] = self._load_json("org/chat_notes", {})
        self.chat_tags: Dict[str, List[str]] = self._load_json("org/chat_tags", {})
        self.chat_derived: Dict[str, str] = self._load_json("org/chat_derived", {})
        self.chat_bookmarks: Dict[str, List[Dict[str, Any]]] = self._load_json("org/chat_bookmarks", {})
        self.categories: Set[str] = set(v for v in self.chat_categories.values() if v)

        self.recent_projects: List[str] = [
            x for x in self._load_json("org/recent_projects", []) if isinstance(x, str)
        ]

    def _load_json(self, key: str, default: Any) -> Any:
        try:
            val = self.settings.value(key, None)
            if val is None:
                return default
            if isinstance(val, (dict, list)):
                return val
            return json.loads(str(val))
        except Exception:
            return default

    def _save_json(self, key: str, val: Any):
        if hasattr(self.settings, "setValue"):
            self.settings.setValue(key, json.dumps(val, ensure_ascii=False))

    def save_all_to_settings(self):
        self._save_json("org/chat_categories", self.chat_categories)
        self._save_json("org/chat_notes", self.chat_notes)
        self._save_json("org/chat_tags", self.chat_tags)
        self._save_json("org/chat_derived", self.chat_derived)
        self._save_json("org/chat_bookmarks", self.chat_bookmarks)
        self._save_json("org/recent_projects", self.recent_projects)

    def trigger_autosave(self):
        """Автоматическое сохранение проекта при изменениях."""
        if not self.auto_save_enabled:
            return
        self.save_all_to_settings()
        if self.current_project_path and Path(self.current_project_path).exists():
            try:
                self.save_project(self.current_project_path, self._cached_chats_ref, self.current_project_name)
                self.autoSaved.emit(self.current_project_path)
            except Exception as ex:
                logger.warning("Autosave failed: %s", ex)

    def set_active_chats_ref(self, chats: List[ChatLog]):
        self._cached_chats_ref = chats

    # ---- Hierarchical Categories ----
    def get_hierarchical_categories(self) -> List[Tuple[str, int, str]]:
        """
        Возвращает упорядоченный список категорий с иерархией:
        [(full_path, depth, display_label), ...]
        Например: [("Work", 0, "📁 Work"), ("Work/Research", 1, "  └ 📁 Research"), ...]
        """
        all_cats = sorted(self.categories)
        result: List[Tuple[str, int, str]] = []
        for cat in all_cats:
            parts = [p.strip() for p in cat.split("/") if p.strip()]
            depth = max(0, len(parts) - 1)
            prefix = "  " * depth + ("└ " if depth > 0 else "")
            display_name = f"{prefix}📁 {parts[-1]}" if parts else cat
            result.append((cat, depth, display_name))
        return result

    def get_category(self, path_or_chat: str | ChatLog) -> str:
        p = path_or_chat.path if isinstance(path_or_chat, ChatLog) else path_or_chat
        return self.chat_categories.get(p or "", "")

    def create_category(self, name: str, callback: Optional[Callable] = None):
        name = name.strip().strip("/")
        if not name or name in self.categories:
            return
        old_cats = set(self.categories)

        def do():
            self.categories.add(name)
            # Автоматически добавляем родительские категории если есть /
            parts = name.split("/")
            for i in range(1, len(parts)):
                parent = "/".join(parts[:i])
                if parent:
                    self.categories.add(parent)
            self.categoriesChanged.emit()
            self.trigger_autosave()
            if callback:
                callback()

        def undo():
            self.categories = set(old_cats)
            self.categoriesChanged.emit()
            self.trigger_autosave()
            if callback:
                callback()

        self.undo_manager.execute(Command(f"Create category '{name}'", do, undo))

    def assign_category(self, path: str, name: str, callback: Optional[Callable] = None):
        name = name.strip().strip("/")
        old_cat = self.chat_categories.get(path, "")

        def do():
            if name:
                self.categories.add(name)
                self.chat_categories[path] = name
            else:
                self.chat_categories.pop(path, None)
            self._save_json("org/chat_categories", self.chat_categories)
            self.categoriesChanged.emit()
            self.metadataChanged.emit(path)
            self.trigger_autosave()
            if callback:
                callback()

        def undo():
            if old_cat:
                self.chat_categories[path] = old_cat
            else:
                self.chat_categories.pop(path, None)
            self._save_json("org/chat_categories", self.chat_categories)
            self.categoriesChanged.emit()
            self.metadataChanged.emit(path)
            self.trigger_autosave()
            if callback:
                callback()

        self.undo_manager.execute(Command(f"Assign category '{name}'", do, undo))

    # ---- Tags ----
    def get_tags(self, path_or_chat: str | ChatLog) -> List[str]:
        p = path_or_chat.path if isinstance(path_or_chat, ChatLog) else path_or_chat
        val = self.chat_tags.get(p or "", [])
        return list(val) if isinstance(val, list) else []

    def set_tags(self, path: str, tags: List[str], callback: Optional[Callable] = None):
        old_tags = self.get_tags(path)
        clean_tags = [t.strip().lstrip("#") for t in tags if t.strip()]

        def do():
            if clean_tags:
                self.chat_tags[path] = clean_tags
            else:
                self.chat_tags.pop(path, None)
            self._save_json("org/chat_tags", self.chat_tags)
            self.metadataChanged.emit(path)
            self.trigger_autosave()
            if callback:
                callback()

        def undo():
            if old_tags:
                self.chat_tags[path] = old_tags
            else:
                self.chat_tags.pop(path, None)
            self._save_json("org/chat_tags", self.chat_tags)
            self.metadataChanged.emit(path)
            self.trigger_autosave()
            if callback:
                callback()

        self.undo_manager.execute(Command("Set tags", do, undo))

    # ---- Notes ----
    def get_note(self, path_or_chat: str | ChatLog) -> str:
        p = path_or_chat.path if isinstance(path_or_chat, ChatLog) else path_or_chat
        return self.chat_notes.get(p or "", "")

    def set_note(self, path: str, note: str, callback: Optional[Callable] = None):
        old_note = self.get_note(path)
        clean_note = note.strip()

        def do():
            if clean_note:
                self.chat_notes[path] = clean_note
            else:
                self.chat_notes.pop(path, None)
            self._save_json("org/chat_notes", self.chat_notes)
            self.metadataChanged.emit(path)
            self.trigger_autosave()
            if callback:
                callback()

        def undo():
            if old_note:
                self.chat_notes[path] = old_note
            else:
                self.chat_notes.pop(path, None)
            self._save_json("org/chat_notes", self.chat_notes)
            self.metadataChanged.emit(path)
            self.trigger_autosave()
            if callback:
                callback()

        self.undo_manager.execute(Command("Set note", do, undo))

    # ---- Bookmarks & Highlighter Quotes ----
    def get_bookmarks(self, path_or_chat: str | ChatLog) -> List[Dict[str, Any]]:
        p = path_or_chat.path if isinstance(path_or_chat, ChatLog) else path_or_chat
        return list(self.chat_bookmarks.get(p or "", []))

    def is_bookmarked(self, path: str, block_num: int) -> bool:
        bms = self.get_bookmarks(path)
        return any(b.get("block_num") == block_num for b in bms)

    def add_bookmark(
        self,
        path: str,
        block_num: int,
        role: str = "",
        title: str = "",
        note: str = "",
        snippet: str = "",
        quote: str = "",
        color: str = "",
        callback: Optional[Callable] = None,
    ):
        if not path:
            return
        bms = self.get_bookmarks(path)
        # Если это закладка без цитаты — обновляем существующую
        if not quote:
            for b in bms:
                if b.get("block_num") == block_num and not b.get("quote"):
                    b["note"] = note
                    b["role"] = role or b.get("role", "")
                    b["snippet"] = snippet or b.get("snippet", "")
                    b["color"] = color or b.get("color", "")
                    self._save_json("org/chat_bookmarks", self.chat_bookmarks)
                    self.bookmarksChanged.emit(path)
                    self.trigger_autosave()
                    if callback:
                        callback()
                    return

        new_bm = {
            "block_num": block_num,
            "role": role,
            "title": title,
            "note": note,
            "snippet": snippet[:200] if snippet else "",
            "quote": quote.strip(),
            "color": color or "yellow",
            "created_at": "",
        }
        bms.append(new_bm)
        self.chat_bookmarks[path] = bms
        self._save_json("org/chat_bookmarks", self.chat_bookmarks)
        self.bookmarksChanged.emit(path)
        self.trigger_autosave()
        if callback:
            callback()

    def add_highlight(
        self,
        path: str,
        block_num: int,
        quote: str,
        color: str = "yellow",
        role: str = "",
        title: str = "",
        note: str = "",
    ):
        """Добавляет маркер/выделенную цитату."""
        self.add_bookmark(
            path=path,
            block_num=block_num,
            role=role,
            title=title,
            note=note,
            snippet=quote[:200],
            quote=quote,
            color=color,
        )

    def remove_bookmark(self, path: str, block_num: int, callback: Optional[Callable] = None):
        if not path or path not in self.chat_bookmarks:
            return
        bms = [b for b in self.chat_bookmarks[path] if b.get("block_num") != block_num]
        if bms:
            self.chat_bookmarks[path] = bms
        else:
            self.chat_bookmarks.pop(path, None)
        self._save_json("org/chat_bookmarks", self.chat_bookmarks)
        self.bookmarksChanged.emit(path)
        self.trigger_autosave()
        if callback:
            callback()

    def remove_highlight(self, path: str, block_num: int, quote: str):
        if not path or path not in self.chat_bookmarks:
            return
        bms = [
            b for b in self.chat_bookmarks[path]
            if not (b.get("block_num") == block_num and b.get("quote") == quote)
        ]
        if bms:
            self.chat_bookmarks[path] = bms
        else:
            self.chat_bookmarks.pop(path, None)
        self._save_json("org/chat_bookmarks", self.chat_bookmarks)
        self.bookmarksChanged.emit(path)
        self.trigger_autosave()

    def toggle_bookmark(
        self,
        path: str,
        block_num: int,
        role: str = "",
        title: str = "",
        note: str = "",
        snippet: str = "",
        callback: Optional[Callable] = None,
    ) -> bool:
        if self.is_bookmarked(path, block_num):
            self.remove_bookmark(path, block_num, callback)
            return False
        else:
            self.add_bookmark(path, block_num, role, title, note, snippet, callback=callback)
            return True

    def get_all_bookmarks(self) -> List[Dict[str, Any]]:
        out = []
        for path, bms in self.chat_bookmarks.items():
            for b in bms:
                out.append({"path": path, **b})
        return out

    # ---- Project Persistence (.slh.json) ----
    def save_project(self, file_path: str | Path, chats: List[ChatLog], name: str = ""):
        p_path = Path(file_path)
        name = name or p_path.stem
        self._cached_chats_ref = chats

        files_meta = []
        for chat in chats:
            bms = [
                ProjectBookmark(
                    block_num=b.get("block_num", 1),
                    role=b.get("role", ""),
                    title=b.get("title", ""),
                    note=b.get("note", ""),
                    snippet=b.get("snippet", ""),
                    quote=b.get("quote", ""),
                    color=b.get("color", ""),
                )
                for b in self.get_bookmarks(chat.path)
            ]
            files_meta.append(
                ProjectFile(
                    path=chat.path,
                    category=self.get_category(chat.path),
                    note=self.get_note(chat.path),
                    tags=self.get_tags(chat.path),
                    derived_from=self.chat_derived.get(chat.path, ""),
                    title=chat.title,
                    model=chat.model,
                    source_format=chat.source_format,
                    messages=len(chat.messages),
                    bookmarks=bms,
                )
            )

        proj = Project(
            name=name,
            path=str(p_path),
            categories=sorted(self.categories),
            files=files_meta,
        )
        proj.save(p_path)
        self.current_project_path = str(p_path)
        self.current_project_name = name
        self._add_recent(str(p_path))
        self.projectChanged.emit()
        logger.info("Project saved: %s (%d files)", p_path, len(files_meta))

    def load_project(self, file_path: str | Path) -> Tuple[Project, List[str]]:
        proj = Project.load(file_path)
        self.current_project_path = str(file_path)
        self.current_project_name = proj.name

        for c in proj.categories:
            self.categories.add(c)

        file_paths = []
        for pf in proj.files:
            if pf.path:
                file_paths.append(pf.path)
                if pf.category:
                    self.chat_categories[pf.path] = pf.category
                if pf.note:
                    self.chat_notes[pf.path] = pf.note
                if pf.tags:
                    self.chat_tags[pf.path] = pf.tags
                if pf.derived_from:
                    self.chat_derived[pf.path] = pf.derived_from
                if pf.bookmarks:
                    self.chat_bookmarks[pf.path] = [b.to_dict() for b in pf.bookmarks]

        self.save_all_to_settings()
        self._add_recent(str(file_path))
        self.projectChanged.emit()
        self.categoriesChanged.emit()
        return proj, file_paths

    def _add_recent(self, p: str):
        if p in self.recent_projects:
            self.recent_projects.remove(p)
        self.recent_projects.insert(0, p)
        self.recent_projects = self.recent_projects[:10]
        self._save_json("org/recent_projects", self.recent_projects)
