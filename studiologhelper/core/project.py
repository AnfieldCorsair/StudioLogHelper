# -*- coding: utf-8 -*-
"""Project .slh.json manager с валидацией и поддержкой закладок/метаданных."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

SCHEMA = "studiologhelper.project.v2"


@dataclass(slots=True)
class ProjectBookmark:
    block_num: int = 1
    line: int = 0
    role: str = ""
    title: str = ""
    note: str = ""
    snippet: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "block_num": self.block_num,
            "line": self.line,
            "role": self.role,
            "title": self.title,
            "note": self.note,
            "snippet": self.snippet,
            "created_at": self.created_at or datetime.now().isoformat(timespec="seconds"),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectBookmark":
        return cls(
            block_num=int(d.get("block_num", 1)),
            line=int(d.get("line", 0)),
            role=str(d.get("role", "")),
            title=str(d.get("title", "")),
            note=str(d.get("note", "")),
            snippet=str(d.get("snippet", "")),
            created_at=str(d.get("created_at", "")),
        )


@dataclass(slots=True)
class ProjectFile:
    path: str
    category: str = ""
    note: str = ""
    tags: list[str] = field(default_factory=list)
    derived_from: str = ""
    title: str = ""
    model: str = ""
    source_format: str = ""
    messages: int = 0
    bookmarks: list[ProjectBookmark] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "category": self.category,
            "note": self.note,
            "tags": self.tags,
            "derived_from": self.derived_from,
            "title": self.title,
            "model": self.model,
            "source_format": self.source_format,
            "messages": self.messages,
            "bookmarks": [b.to_dict() for b in self.bookmarks],
        }

    @classmethod
    def from_dict(cls, item: dict) -> "ProjectFile":
        bms_raw = item.get("bookmarks") or []
        bookmarks = []
        if isinstance(bms_raw, list):
            for b in bms_raw:
                if isinstance(b, dict):
                    bookmarks.append(ProjectBookmark.from_dict(b))

        return cls(
            path=item.get("path", ""),
            category=item.get("category", ""),
            note=item.get("note", ""),
            tags=item.get("tags", []) if isinstance(item.get("tags"), list) else [],
            derived_from=item.get("derived_from", ""),
            title=item.get("title", ""),
            model=item.get("model", ""),
            source_format=item.get("source_format", ""),
            messages=int(item.get("messages", 0)),
            bookmarks=bookmarks,
        )


@dataclass(slots=True)
class Project:
    name: str = ""
    path: str = ""
    categories: list[str] = field(default_factory=list)
    files: list[ProjectFile] = field(default_factory=list)
    parser_options: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "app": "StudioLogHelper",
            "schema": SCHEMA,
            "created_or_saved_at": datetime.now().isoformat(timespec="seconds"),
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
        files = []
        for item in files_raw:
            if not isinstance(item, dict):
                continue
            p = item.get("path", "")
            if not p:
                continue
            files.append(ProjectFile.from_dict(item))

        return cls(
            name=proj_meta.get("name", ""),
            path=file_path or proj_meta.get("path", ""),
            categories=[c for c in categories if isinstance(c, str)],
            files=files,
            parser_options=data.get("parser") or {},
        )

    def save(self, path: Path | str):
        p = Path(path)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> "Project":
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid project file")
        return cls.from_dict(data, str(p))
