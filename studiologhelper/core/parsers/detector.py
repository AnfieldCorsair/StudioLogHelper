# -*- coding: utf-8 -*-
"""Быстрая детекция логов."""

from __future__ import annotations

import re
from pathlib import Path

# Предкомпилированные regex — ускоряет сканирование больших папок
_RE_ARENA = re.compile(r"(?im)^\s*(Arena\s+Side-by-Side\s+Chat|User\s*:|Right\s+(AI|model)\s*:|Model(Name)?\s*:)")
_RE_ARENA_BARE = re.compile(r"(?im)^\s*(User|Right\s+(AI|model)|Model(Name)?|Assistant)\s*$")
_RE_EXPORT_HEADER = re.compile(r"(?im)^\s*---\s*#?\d+\s+(.{0,40}?)(USER|ПОЛЬЗОВАТЕЛЬ|MODEL|МОДЕЛЬ|Assistant|AI|Ответ)")
_RE_NUMBERED = re.compile(r"(?m)^\s*#\d+\s*:")

BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".zip", ".exe", ".pdf",
    ".mp4", ".mp3", ".docx", ".xlsx", ".pptx", ".dll", ".so",
    ".bin", ".dat", ".parquet", ".db", ".sqlite", ".wav", ".avi",
    ".mov", ".mkv", ".iso", ".dmg"
}


def _looks_like_text_log_head(head: str) -> bool:
    if _RE_ARENA.search(head):
        return True
    if len(_RE_ARENA_BARE.findall(head)) >= 2:
        return True
    if _RE_EXPORT_HEADER.search(head):
        return True
    return len(_RE_NUMBERED.findall(head)) >= 2


def looks_like_log(path) -> bool:
    """Быстрая эвристика без загрузки всего файла. Оптимизирована для 10k+ файлов."""
    p = Path(path)
    if not p.is_file():
        return False
    suffix = p.suffix.lower()
    if suffix in BINARY_EXTS:
        return False

    # tiny files (<10 bytes) skip
    try:
        if p.stat().st_size < 10:
            return False
        if p.stat().st_size > 100 * 1024 * 1024:  # >100MB skip as log candidate (checked elsewhere)
            # still check header, but limit
            pass
    except OSError:
        return False

    try:
        with p.open("rb") as fh:
            head_bytes = fh.read(8192)  # 8KB достаточно для детекции, раньше было 4KB
            if not head_bytes:
                return False
            # quick binary check — если много нулевых байтов, это бинарник
            if b"\x00" in head_bytes[:1024]:
                return False
            head = head_bytes.decode("utf-8", errors="ignore").lstrip()
    except OSError:
        return False

    if head.startswith("{") and ('"chunkedPrompt"' in head or '"runSettings"' in head or '"chunks"' in head):
        return True
    # Также ищем в чуть большем окне если JSON не в самом начале (BOM/пробелы)
    if '"chunkedPrompt"' in head[:4096] or '"runSettings"' in head[:2048]:
        return True
    return _looks_like_text_log_head(head)
