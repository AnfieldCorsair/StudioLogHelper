# -*- coding: utf-8 -*-
"""Project .slh.json manager с валидацией."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


SCHEMA = "studiologhelper.project.v2"


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
            "files": [
                {
                    "path": f.path,
                    "category": f.category,
                    "note": f.note,
                    "tags": f.tags,
                    "derived_from": f.derived_from,
                    "title": f.title,
                    "model": f.model,
                    "source_format": f.source_format,
                    "messages": f.messages,
                }
                for f in self.files
            ],
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
            files.append(
                ProjectFile(
                    path=p,
                    category=item.get("category", ""),
                    note=item.get("note", ""),
                    tags=item.get("tags", []) if isinstance(item.get("tags"), list) else [],
                    derived_from=item.get("derived_from", ""),
                    title=item.get("title", ""),
                    model=item.get("model", ""),
                    source_format=item.get("source_format", ""),
                    messages=item.get("messages", 0),
                )
            )
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
