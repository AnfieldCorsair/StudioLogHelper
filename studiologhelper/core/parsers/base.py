# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class TextParseOptions:
    """Настройки разбора plain-text логов."""

    user_headers: list[str] = field(default_factory=list)
    model_headers: list[str] = field(default_factory=list)
    numbered_mode: str = "model"  # model|user|alternating
