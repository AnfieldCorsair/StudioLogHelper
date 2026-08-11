# -*- coding: utf-8 -*-
"""ProjectController — надёжное управление проектами .slh.json с debounce-автосохранением, UUID-закладками и маркерами."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
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
            self._callback = None
        def setSingleShot(self, val):
            pass
        def start(self, ms=0):
            if self._callback:
                self._callback()
        def stop(self):
            pass
        @property
        def timeout(self):
            class _Timeout:
                def __init__(self, outer):
                    self.outer = outer
                def connect(self, cb):
                    self.outer._callback = cb
            return _Timeout(self)

from ...core.models import ChatLog
from ...core.project import (
    HIGHLIGHT_COLORS,
    Highlight,
    Project,
    ProjectBookmark,
    ProjectFile,
    compute_text_hash,
    matches_hierarchical_category,
)
from ...utils.logger import get_logger
from ..undo import Command, UndoManager

logger = get_logger()
AUTOSAVE_DEBOUNCE_MS = 500


class ProjectController(QObject):
    """Контроллер проектов, иерархических категорий, тегов, закладок, цитат-маркеров и debounce-автосохранения."""

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
        self.is_loading: bool = False
        self.is_initializing: bool = False
        self.dirty: bool = False

        self._cached_chats_ref: List[ChatLog] = []
        self._last_saved_file_count: int = 0

        # Debounce Timer для неблокирующего автосохранения
        self._autosave_timer = QTimer()
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._do_debounced_autosave)

        self.chat_categories: Dict[str, str] = self._load_json("org/chat_categories", {})
        self.chat_notes: Dict[str, str] = self._load_json("org/chat_notes", {})
        self.chat_tags: Dict[str, List[str]] = self._load_json("org/chat_tags", {})
        self.chat_derived: Dict[str, str] = self._load_json("org/chat_derived", {})
        self.chat_bookmarks: Dict[str, List[Dict[str, Any]]] = self._load_json("org/chat_bookmarks", {})
        self.chat_highlights: Dict[str, List[Dict[str, Any]]] = self._load_json("org/chat_highlights", {})
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
        self._save_json("org/chat_highlights", self.chat_highlights)
        self._save_json("org/recent_projects", self.recent_projects)

    def set_active_chats_ref(self, chats: List[ChatLog]):
        self._cached_chats_ref = chats

    # ---- Autosave с Debounce и защитой целостности данных ----
    def trigger_autosave(self):
        """Планирует отложенное автосохранение с debounce, защищая от фризов и перезаписи пустым списком."""
        if not self.auto_save_enabled:
            return
        if self.is_loading or self.is_initializing:
            return
        self.dirty = True
        self._autosave_timer.start(AUTOSAVE_DEBOUNCE_MS)

    def _do_debounced_autosave(self):
        if not self.dirty:
            return
        self.save_all_to_settings()

        if self.current_project_path and Path(self.current_project_path).exists():
            # Защита: не сохраняем проект пустым, если он содержал файлы ранее
            if not self._cached_chats_ref and self._last_saved_file_count > 0:
                logger.warning("Autosave skipped: chat list is temporarily empty during transition")
                return
            try:
                self.save_project(self.current_project_path, self._cached_chats_ref, self.current_project_name)
                self.dirty = False
                self.autoSaved.emit(self.current_project_path)
            except Exception as ex:
                logger.warning("Debounced autosave failed: %s", ex)

    # ---- Hierarchical Categories ----
    def get_hierarchical_categories(self) -> List[Tuple[str, int, str]]:
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

    # ---- Bookmarks (Изолированные от цитат с уникальным UUID) ----
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
        callback: Optional[Callable] = None,
    ) -> str:
        if not path:
            return ""
        bms = self.get_bookmarks(path)
        for b in bms:
            if b.get("block_num") == block_num:
                b["note"] = note
                b["role"] = role or b.get("role", "")
                b["snippet"] = snippet or b.get("snippet", "")
                self._save_json("org/chat_bookmarks", self.chat_bookmarks)
                self.bookmarksChanged.emit(path)
                self.trigger_autosave()
                if callback:
                    callback()
                return b.get("id", "")

        bm_id = str(uuid.uuid4())
        new_bm = {
            "id": bm_id,
            "block_num": block_num,
            "role": role,
            "title": title,
            "note": note,
            "snippet": snippet[:200] if snippet else "",
        }
        bms.append(new_bm)
        self.chat_bookmarks[path] = bms
        self._save_json("org/chat_bookmarks", self.chat_bookmarks)
        self.bookmarksChanged.emit(path)
        self.trigger_autosave()
        if callback:
            callback()
        return bm_id

    def update_bookmark_note(self, path: str, bm_id: str, note: str):
        """Обновляет заметку конкретной закладки по UUID без создания дубликатов."""
        if not path or path not in self.chat_bookmarks:
            return
        for b in self.chat_bookmarks[path]:
            if b.get("id") == bm_id:
                b["note"] = note
                self._save_json("org/chat_bookmarks", self.chat_bookmarks)
                self.bookmarksChanged.emit(path)
                self.trigger_autosave()
                return

    def remove_bookmark_by_id(self, path: str, bm_id: str, callback: Optional[Callable] = None):
        if not path or path not in self.chat_bookmarks:
            return
        bms = [b for b in self.chat_bookmarks[path] if b.get("id") != bm_id]
        if bms:
            self.chat_bookmarks[path] = bms
        else:
            self.chat_bookmarks.pop(path, None)
        self._save_json("org/chat_bookmarks", self.chat_bookmarks)
        self.bookmarksChanged.emit(path)
        self.trigger_autosave()
        if callback:
            callback()

    def remove_bookmark(self, path: str, block_num: int, callback: Optional[Callable] = None):
        """Удаляет закладку на блок. НЕ удаляет маркеры/цитаты этого же блока!"""
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

    # ---- Highlights / Маркеры цитат (Изолированные с точными позициями и UUID) ----
    def get_highlights(self, path_or_chat: str | ChatLog) -> List[Dict[str, Any]]:
        p = path_or_chat.path if isinstance(path_or_chat, ChatLog) else path_or_chat
        return list(self.chat_highlights.get(p or "", []))

    def add_highlight(
        self,
        path: str,
        block_num: int,
        quote: str,
        color: str = "yellow",
        start: int = 0,
        end: int = 0,
        role: str = "",
        title: str = "",
        note: str = "",
        source_text: str = "",
    ) -> str:
        if not path or not quote:
            return ""
        hls = self.get_highlights(path)
        hl_id = str(uuid.uuid4())
        text_hash = compute_text_hash(source_text)

        new_hl = {
            "id": hl_id,
            "block_num": block_num,
            "start": start,
            "end": end,
            "quote": quote,
            "color": color or "yellow",
            "role": role,
            "title": title,
            "note": note,
            "source_text_hash": text_hash,
        }
        hls.append(new_hl)
        self.chat_highlights[path] = hls
        self._save_json("org/chat_highlights", self.chat_highlights)
        self.bookmarksChanged.emit(path)
        self.trigger_autosave()
        return hl_id

    def update_highlight_note(self, path: str, hl_id: str, note: str):
        """Обновляет заметку конкретной цитаты по UUID без создания дубликатов."""
        if not path or path not in self.chat_highlights:
            return
        for h in self.chat_highlights[path]:
            if h.get("id") == hl_id:
                h["note"] = note
                self._save_json("org/chat_highlights", self.chat_highlights)
                self.bookmarksChanged.emit(path)
                self.trigger_autosave()
                return

    def remove_highlight_by_id(self, path: str, hl_id: str):
        if not path or path not in self.chat_highlights:
            return
        hls = [h for h in self.chat_highlights[path] if h.get("id") != hl_id]
        if hls:
            self.chat_highlights[path] = hls
        else:
            self.chat_highlights.pop(path, None)
        self._save_json("org/chat_highlights", self.chat_highlights)
        self.bookmarksChanged.emit(path)
        self.trigger_autosave()

    def remove_highlight_by_quote(self, path: str, block_num: int, quote: str):
        if not path or path not in self.chat_highlights:
            return
        hls = [h for h in self.chat_highlights[path] if not (h.get("block_num") == block_num and h.get("quote") == quote)]
        if hls:
            self.chat_highlights[path] = hls
        else:
            self.chat_highlights.pop(path, None)
        self._save_json("org/chat_highlights", self.chat_highlights)
        self.bookmarksChanged.emit(path)
        self.trigger_autosave()

    def get_all_bookmarks_and_highlights(self) -> List[Dict[str, Any]]:
        out = []
        for path, bms in self.chat_bookmarks.items():
            for b in bms:
                out.append({"path": path, "is_highlight": False, **b})
        for path, hls in self.chat_highlights.items():
            for h in hls:
                out.append({"path": path, "is_highlight": True, **h})
        return out

    # ---- Project Persistence (.slh.json) с созданием снимков ----
    def create_project_snapshot(self, name: str = "", path: str = "") -> Project:
        """Создает изолированный снимок проекта для безопасного сохранения."""
        files_meta: List[ProjectFile] = []
        for chat in self._cached_chats_ref:
            bms = [
                ProjectBookmark(
                    id=str(b.get("id") or uuid.uuid4()),
                    block_num=b.get("block_num", 1),
                    role=b.get("role", ""),
                    title=b.get("title", ""),
                    note=b.get("note", ""),
                    snippet=b.get("snippet", ""),
                )
                for b in self.get_bookmarks(chat.path)
            ]
            hls = [
                Highlight(
                    id=str(h.get("id") or uuid.uuid4()),
                    block_num=h.get("block_num", 1),
                    start=h.get("start", 0),
                    end=h.get("end", 0),
                    quote=h.get("quote", ""),
                    color=h.get("color", "yellow"),
                    note=h.get("note", ""),
                    source_text_hash=h.get("source_text_hash", ""),
                )
                for h in self.get_highlights(chat.path)
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
                    highlights=hls,
                )
            )

        return Project(
            name=name or self.current_project_name,
            path=path or self.current_project_path,
            categories=sorted(self.categories),
            files=files_meta,
        )

    def save_project(self, file_path: str | Path, chats: List[ChatLog], name: str = ""):
        p_path = Path(file_path).resolve()
        name = name or p_path.stem
        self._cached_chats_ref = list(chats)
        self._last_saved_file_count = len(chats)

        proj = self.create_project_snapshot(name=name, path=str(p_path))
        proj.save(p_path, create_backup=True)

        self.current_project_path = str(p_path)
        self.current_project_name = name
        self._add_recent(str(p_path))
        self.projectChanged.emit()
        logger.info("Project saved atomically: %s (%d files)", p_path, len(proj.files))

    def load_project(self, file_path: str | Path) -> Tuple[Project, List[str]]:
        self.is_loading = True
        try:
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
                    if pf.highlights:
                        self.chat_highlights[pf.path] = [h.to_dict() for h in pf.highlights]

            self._last_saved_file_count = len(file_paths)
            self.save_all_to_settings()
            self._add_recent(str(file_path))
            self.projectChanged.emit()
            self.categoriesChanged.emit()
            return proj, file_paths
        finally:
            self.is_loading = False

    def _add_recent(self, p: str):
        if p in self.recent_projects:
            self.recent_projects.remove(p)
        self.recent_projects.insert(0, p)
        self.recent_projects = self.recent_projects[:10]
        self._save_json("org/recent_projects", self.recent_projects)
