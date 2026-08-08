# -*- coding: utf-8 -*-
"""Быстрое определение кодировки с минимальными аллокациями."""

from __future__ import annotations

from pathlib import Path

# Порядок важен: самая частая UTF-8 первая
ENCODINGS = ("utf-8", "utf-8-sig", "utf-16", "cp1251")

# BOM для быстрого определения
BOMS = {
    b"\xef\xbb\xbf": "utf-8-sig",
    b"\xff\xfe": "utf-16",
    b"\xfe\xff": "utf-16-be",
}


def detect_encoding_and_decode(data: bytes) -> str:
    """Декодирует байты, проверяя BOM сперва, затем пробуя кодировки."""
    # Fast BOM check
    for bom, enc in BOMS.items():
        if data.startswith(bom):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                break
    # Most files are utf-8 — try it directly
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for enc in ENCODINGS[1:]:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    # Last resort
    return data.decode("utf-8", errors="replace")


def read_text_file(path: Path | str, max_size: int = 100 * 1024 * 1024) -> str:
    """Читает текстовый файл с лимитом размера."""
    p = Path(path)
    size = p.stat().st_size
    if size > max_size:
        raise ValueError(f"File too large: {size} > {max_size}")
    data = p.read_bytes()
    return detect_encoding_and_decode(data)
