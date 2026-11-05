# -*- coding: utf-8 -*-
"""Быстрая детекция логов.

Оптимизации (рефакторинг 2026):
- Один stat() на файл (было два).
- Подсчёт повторов с ранним выходом (findall со списком -> finditer со счётчиком).
"""

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

_MAX_DETECTOR_SIZE = 100 * 1024 * 1024  # >100MB — ограничиваем чтение шапки


def _count_matches(pattern: re.Pattern, text: str, minimum: int) -> bool:
    """True, если pattern встречается >= minimum раз (ранний выход, без списка)."""
    n = 0
    for _ in pattern.finditer(text):
        n += 1
        if n >= minimum:
            return True
    return False


def _looks_like_text_log_head(head: str) -> bool:
    if _RE_ARENA.search(head):
        return True
    if _count_matches(_RE_ARENA_BARE, head, 2):
        return True
    if _RE_EXPORT_HEADER.search(head):
        return True
    return _count_matches(_RE_NUMBERED, head, 2)


def looks_like_log(path) -> bool:
    """Быстрая эвристика без загрузки всего файла. Оптимизирована для 10k+ файлов."""
    p = Path(path)
    if not p.is_file():
        return False
    suffix = p.suffix.lower()
    if suffix in BINARY_EXTS:
        return False

    try:
        size = p.stat().st_size  # один stat вместо двух
        if size < 10:
            return False
    except OSError:
        return False

    try:
        with p.open("rb") as fh:
            head_bytes = fh.read(8192)  # 8KB достаточно для детекции
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
