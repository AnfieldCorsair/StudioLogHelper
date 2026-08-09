# -*- coding: utf-8 -*-
"""Typed settings via Pydantic — валидация и дефолты."""

from __future__ import annotations

from typing import List, Literal, Optional
from pathlib import Path

try:
    from pydantic import BaseModel, Field, field_validator
    HAS_PYDANTIC = True
except ImportError:
    # Fallback minimal dataclass-like if pydantic not installed
    HAS_PYDANTIC = False

    class BaseModel:  # type: ignore
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self):
            return self.__dict__

        @classmethod
        def model_validate(cls, data):
            return cls(**data)


if HAS_PYDANTIC:
    from pydantic import BaseModel, Field

    class TextParseSettings(BaseModel):
        user_headers: List[str] = Field(default_factory=list)
        model_headers: List[str] = Field(default_factory=list)
        numbered_mode: Literal["model", "user", "alternating"] = "model"

    class ExportSettings(BaseModel):
        fmt: Literal["txt", "html", "md", "json", "jsonl"] = "txt"
        content: Literal["all", "prompts", "answers", "thoughts"] = "all"
        thoughts: Literal["exclude", "include", "separate"] = "exclude"
        numbering: bool = True
        timestamps: bool = False
        metadata: bool = True
        attachments: bool = True
        system_instruction: bool = True
        render_markdown: bool = True
        user_label: str = "USER"
        model_label: str = "MODEL"
        auto_model_label: bool = True

    class UISettings(BaseModel):
        theme: Literal["dark", "light"] = "dark"
        lang: Literal["ru", "en"] = "ru"
        zoom: int = Field(default=100, ge=70, le=200)
        render_md: bool = True
        show_thoughts: bool = True
        show_extensions: bool = False
        show_diagnostics: bool = False
        auto_collapse_long: bool = True
        collapse_preview_chars: int = Field(default=5000, ge=800, le=50000)

    class IndexSettings(BaseModel):
        use_threads: bool = True
        batch_size: int = Field(default=50, ge=1, le=500)
        max_txt_size_mb: int = Field(default=50, ge=1, le=500)
        db_path: Optional[str] = None

    class CopySettings(BaseModel):
        include_service: bool = True
        separator: Literal["blank", "double", "long", "custom"] = "blank"
        custom_separator: str = "\n---\n"

    class AppConfig(BaseModel):
        version: int = 2
        ui: UISettings = Field(default_factory=UISettings)
        parser: TextParseSettings = Field(default_factory=TextParseSettings)
        export: ExportSettings = Field(default_factory=ExportSettings)
        copy: CopySettings = Field(default_factory=CopySettings)
        index: IndexSettings = Field(default_factory=IndexSettings)
        recent_projects: List[str] = Field(default_factory=list)
        project_name: str = ""
        project_path: str = ""

else:
    # Minimal fallback without validation
    class TextParseSettings(BaseModel):
        def __init__(self, user_headers=None, model_headers=None, numbered_mode="model"):
            self.user_headers = user_headers or []
            self.model_headers = model_headers or []
            self.numbered_mode = numbered_mode

    class ExportSettings(BaseModel):
        def __init__(self, **kw):
            self.fmt = kw.get("fmt", "txt")
            self.content = kw.get("content", "all")
            self.thoughts = kw.get("thoughts", "exclude")
            self.numbering = kw.get("numbering", True)
            self.timestamps = kw.get("timestamps", False)
            self.metadata = kw.get("metadata", True)
            self.attachments = kw.get("attachments", True)
            self.system_instruction = kw.get("system_instruction", True)
            self.render_markdown = kw.get("render_markdown", True)
            self.user_label = kw.get("user_label", "USER")
            self.model_label = kw.get("model_label", "MODEL")
            self.auto_model_label = kw.get("auto_model_label", True)

    class UISettings(BaseModel):
        def __init__(self, **kw):
            self.theme = kw.get("theme", "dark")
            self.lang = kw.get("lang", "ru")
            self.zoom = kw.get("zoom", 100)
            self.render_md = kw.get("render_md", True)
            self.show_thoughts = kw.get("show_thoughts", True)
            self.show_extensions = kw.get("show_extensions", False)
            self.show_diagnostics = kw.get("show_diagnostics", False)
            self.auto_collapse_long = kw.get("auto_collapse_long", True)
            self.collapse_preview_chars = kw.get("collapse_preview_chars", 5000)

    class IndexSettings(BaseModel):
        def __init__(self, **kw):
            self.use_threads = kw.get("use_threads", True)
            self.batch_size = kw.get("batch_size", 50)
            self.max_txt_size_mb = kw.get("max_txt_size_mb", 50)
            self.db_path = kw.get("db_path", None)

    class CopySettings(BaseModel):
        def __init__(self, **kw):
            self.include_service = kw.get("include_service", True)
            self.separator = kw.get("separator", "blank")
            self.custom_separator = kw.get("custom_separator", "\n---\n")

    class AppConfig(BaseModel):
        def __init__(self, **kw):
            self.version = 2
            self.ui = kw.get("ui") or UISettings()
            self.parser = kw.get("parser") or TextParseSettings()
            self.export = kw.get("export") or ExportSettings()
            self.copy = kw.get("copy") or CopySettings()
            self.index = kw.get("index") or IndexSettings()
            self.recent_projects = kw.get("recent_projects", [])
            self.project_name = kw.get("project_name", "")
            self.project_path = kw.get("project_path", "")

        def model_dump(self):
            return {
                "version": self.version,
                "ui": self.ui.__dict__ if hasattr(self.ui, '__dict__') else {},
                "parser": self.parser.__dict__,
                "export": self.export.__dict__,
                "copy": self.copy.__dict__,
                "index": self.index.__dict__,
                "recent_projects": self.recent_projects,
                "project_name": self.project_name,
                "project_path": self.project_path,
            }


def load_config_from_qsettings(qsettings) -> AppConfig:
    """Читает QSettings и валидирует через Pydantic."""
    import json

    def get_json(key, default):
        try:
            raw = qsettings.value(key, json.dumps(default, ensure_ascii=False))
            data = json.loads(raw)
            return data if isinstance(data, type(default)) else default
        except Exception:
            return default

    ui = UISettings(
        theme=qsettings.value("ui/theme", "dark"),
        lang=qsettings.value("ui/lang", "ru"),
        zoom=int(qsettings.value("ui/zoom", 100) or 100),
        render_md=qsettings.value("ui/render_md", "true") == "true",
        show_thoughts=qsettings.value("ui/show_thoughts", "true") == "true",
        show_extensions=qsettings.value("ui/show_extensions", "false") == "true",
        show_diagnostics=qsettings.value("ui/show_diagnostics", "false") == "true",
        auto_collapse_long=qsettings.value("ui/auto_collapse_long", "true") == "true",
        collapse_preview_chars=int(qsettings.value("ui/collapse_preview_chars", 5000) or 5000),
    )
    parser = TextParseSettings(
        user_headers=[x.strip() for x in str(qsettings.value("parse/user_headers", "") or "").splitlines() if x.strip()],
        model_headers=[x.strip() for x in str(qsettings.value("parse/model_headers", "") or "").splitlines() if x.strip()],
        numbered_mode=qsettings.value("parse/numbered_mode", "model"),
    )
    return AppConfig(ui=ui, parser=parser)
