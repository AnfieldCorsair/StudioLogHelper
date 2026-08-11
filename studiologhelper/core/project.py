# -*- coding: utf-8 -*-
"""Project .slh.json manager — атомарное сохранение, версионирование, относительные пути, закладки и маркеры-цитаты."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SCHEMA = "studiologhelper.project.v2"

# Цвета маркеров (Highlighters)
HIGHLIGHT_COLORS = {
    "yellow": {"name": "Жёлтый", "hex": "#fff176", "text": "#333333"},
    "green": {"name": "Зелёный", "hex": "#a5d6a7", "text": "#1b5e20"},
    "pink": {"name": "Розовый", "hex": "#f48fb1", "text": "#880e4f"},
    "blue": {"name": "Голубой", "hex": "#90caf9", "text": "#0d47a1"},
}


def compute_text_hash(text: str) -> str:
    """Вычисляет короткий sha256-хэш исходного текста для валидации актуальности цитат."""
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


@dataclass(slots=True)
class Highlight:
    """Выделенная маркером цитата с точными границами, хэшем источника и стабильным UUID."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    block_num: int = 1
    start: int = 0
    end: int = 0
    quote: str = ""
    color: str = "yellow"
    note: str = ""
    source_text_hash: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "block_num": self.block_num,
            "start": self.start,
            "end": self.end,
            "quote": self.quote,
            "color": self.color,
            "note": self.note,
            "source_text_hash": self.source_text_hash,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Highlight":
        return cls(
            id=str(d.get("id") or uuid.uuid4()),
            block_num=int(d.get("block_num", 1)),
            start=int(d.get("start", 0)),
            end=int(d.get("end", 0)),
            quote=str(d.get("quote", "")),
            color=str(d.get("color", "yellow")),
            note=str(d.get("note", "")),
            source_text_hash=str(d.get("source_text_hash", "")),
            created_at=str(d.get("created_at") or datetime.now().isoformat(timespec="seconds")),
        )


@dataclass(slots=True)
class ProjectBookmark:
    """Закладка на сообщение/блок с уникальным ID."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    block_num: int = 1
    line: int = 0
    role: str = ""
    title: str = ""
    note: str = ""
    snippet: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "block_num": self.block_num,
            "line": self.line,
            "role": self.role,
            "title": self.title,
            "note": self.note,
            "snippet": self.snippet,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectBookmark":
        return cls(
            id=str(d.get("id") or uuid.uuid4()),
            block_num=int(d.get("block_num", 1)),
            line=int(d.get("line", 0)),
            role=str(d.get("role", "")),
            title=str(d.get("title", "")),
            note=str(d.get("note", "")),
            snippet=str(d.get("snippet", "")),
            created_at=str(d.get("created_at") or datetime.now().isoformat(timespec="seconds")),
        )


@dataclass(slots=True)
class ProjectFile:
    """Метаданные файла в проекте с поддержкой относительных путей для переносимости."""

    path: str
    rel_path: str = ""
    category: str = ""
    note: str = ""
    tags: list[str] = field(default_factory=list)
    derived_from: str = ""
    title: str = ""
    model: str = ""
    source_format: str = ""
    messages: int = 0
    bookmarks: list[ProjectBookmark] = field(default_factory=list)
    highlights: list[Highlight] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "rel_path": self.rel_path,
            "category": self.category,
            "note": self.note,
            "tags": self.tags,
            "derived_from": self.derived_from,
            "title": self.title,
            "model": self.model,
            "source_format": self.source_format,
            "messages": self.messages,
            "bookmarks": [b.to_dict() for b in self.bookmarks],
            "highlights": [h.to_dict() for h in self.highlights],
        }

    @classmethod
    def from_dict(cls, item: dict, base_dir: Optional[Path] = None) -> "ProjectFile":
        bms_raw = item.get("bookmarks") or []
        hls_raw = item.get("highlights") or []
        bookmarks: list[ProjectBookmark] = []
        highlights: list[Highlight] = []

        if isinstance(bms_raw, list):
            for b in bms_raw:
                if isinstance(b, dict):
                    if b.get("quote"):
                        highlights.append(
                            Highlight(
                                id=str(b.get("id") or uuid.uuid4()),
                                block_num=int(b.get("block_num", 1)),
                                start=int(b.get("start", 0)),
                                end=int(b.get("end", 0)),
                                quote=str(b.get("quote", "")),
                                color=str(b.get("color", "yellow")),
                                note=str(b.get("note", "")),
                                source_text_hash=str(b.get("source_text_hash", "")),
                                created_at=str(b.get("created_at") or ""),
                            )
                        )
                    else:
                        bookmarks.append(ProjectBookmark.from_dict(b))

        if isinstance(hls_raw, list):
            for h in hls_raw:
                if isinstance(h, dict):
                    highlights.append(Highlight.from_dict(h))

        raw_path = item.get("path", "")
        rel_path = item.get("rel_path", "")

        resolved_path = raw_path
        if base_dir and rel_path:
            candidate = (base_dir / rel_path).resolve()
            if candidate.exists() or not Path(raw_path).exists():
                resolved_path = str(candidate)

        return cls(
            path=resolved_path,
            rel_path=rel_path,
            category=item.get("category", ""),
            note=item.get("note", ""),
            tags=item.get("tags", []) if isinstance(item.get("tags"), list) else [],
            derived_from=item.get("derived_from", ""),
            title=item.get("title", ""),
            model=item.get("model", ""),
            source_format=item.get("source_format", ""),
            messages=int(item.get("messages", 0)),
            bookmarks=bookmarks,
            highlights=highlights,
        )


def matches_hierarchical_category(item_cat: str, filter_cat: str) -> bool:
    """Проверяет вхождение категории в иерархический фильтр."""
    if not filter_cat:
        return True
    if filter_cat == "__none__":
        return not bool(item_cat)
    if not item_cat:
        return False
    item_parts = [p.strip().lower() for p in item_cat.split("/") if p.strip()]
    filter_parts = [p.strip().lower() for p in filter_cat.split("/") if p.strip()]
    if len(item_parts) < len(filter_parts):
        return False
    return item_parts[: len(filter_parts)] == filter_parts


@dataclass(slots=True)
class Project:
    """Модель проекта StudioLogHelper с атомарной записью и разделением дат."""

    name: str = ""
    path: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    categories: list[str] = field(default_factory=list)
    files: list[ProjectFile] = field(default_factory=list)
    parser_options: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        now_str = datetime.now().isoformat(timespec="seconds")
        return {
            "app": "StudioLogHelper",
            "schema": SCHEMA,
            "created_at": self.created_at or now_str,
            "updated_at": now_str,
            "project": {"name": self.name, "path": self.path},
            "categories": sorted(set(self.categories)),
            "files": [f.to_dict() for f in self.files],
            "parser": self.parser_options,
        }

    @classmethod
    def from_dict(cls, data: dict, file_path: str = "") -> "Project":
        proj_meta = data.get("project") or {}
        categories = data.get("categories") or []
        files_raw = data.get("files") or []
        base_dir = Path(file_path).parent if file_path else None

        files = []
        for item in files_raw:
            if not isinstance(item, dict):
                continue
            p = item.get("path", "")
            if not p and not item.get("rel_path"):
                continue
            files.append(ProjectFile.from_dict(item, base_dir=base_dir))

        created_at = data.get("created_at") or data.get("created_or_saved_at") or datetime.now().isoformat(timespec="seconds")
        updated_at = data.get("updated_at") or data.get("created_or_saved_at") or datetime.now().isoformat(timespec="seconds")

        return cls(
            name=proj_meta.get("name", ""),
            path=file_path or proj_meta.get("path", ""),
            created_at=created_at,
            updated_at=updated_at,
            categories=[c for c in categories if isinstance(c, str)],
            files=files,
            parser_options=data.get("parser") or {},
        )

    def save(self, path: Path | str, create_backup: bool = True):
        """
        Атомарное сохранение проекта с уникальным временным файлом и fsync.
        """
        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(p)
        self.updated_at = datetime.now().isoformat(timespec="seconds")

        proj_dir = p.parent
        for f in self.files:
            try:
                f_path = Path(f.path).resolve()
                f.rel_path = str(f_path.relative_to(proj_dir))
            except (ValueError, Exception):
                f.rel_path = ""

        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        # Уникальный временный файл для защиты от гонок потоков
        tmp_path = p.with_suffix(p.suffix + f".tmp_{uuid.uuid4().hex[:8]}")
        bak_path = p.with_suffix(p.suffix + ".bak")

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())

            if p.exists() and create_backup:
                try:
                    shutil.copy2(p, bak_path)
                except Exception:
                    pass

            os.replace(tmp_path, p)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    @classmethod
    def load(cls, path: Path | str) -> "Project":
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Project file not found: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid project file: root is not a dict")
        return cls.from_dict(data, str(p))
