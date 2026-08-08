# -*- coding: utf-8 -*-
"""Top-level parse_file с оптимизациями."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..exceptions import ParseError
from .base import TextParseOptions
from .detector import _looks_like_text_log_head
from .json_parser import _json_loads, parse_data
from .text_parser import parse_text_log
from ...utils.encoding import detect_encoding_and_decode


def parse_file(path, text_options: Optional[TextParseOptions] = None):
    """Читает и парсит файл, оптимизированный путь для TXT vs JSON."""
    p = Path(path)
    try:
        data_bytes = p.read_bytes()
    except OSError as e:
        raise ParseError(f"Cannot read file: {e}") from e

    suffix = p.suffix.lower()
    text_candidates: list[str] = []

    # Одно декодирование, а не 4
    try:
        decoded_once = detect_encoding_and_decode(data_bytes)
        text_candidates.append(decoded_once)
    except Exception:
        # fallback: try raw bytes decode via json loader
        pass

    # Fast path для явных текстовых файлов / не-JSON
    for decoded_text in text_candidates:
        stripped = decoded_text.lstrip("\ufeff\x00\n\r\t ")
        if not stripped:
            continue
        looks_jsonish = stripped.startswith("{") or stripped.startswith("[")
        if (suffix in {".txt", ".md", ".log", ".text"} or not looks_jsonish):
            if _looks_like_text_log_head(decoded_text[:20000]):
                return parse_text_log(decoded_text, str(p), text_options)
            if not looks_jsonish:
                # обычный текст, но не диалоговый лог — не падать в JSON парсер
                # Если suffix явно txt и текст большой — бросаем ошибку текста
                if suffix in {".txt", ".md"}:
                    # попытаться как текст лог все равно
                    try:
                        return parse_text_log(decoded_text, str(p), text_options)
                    except ParseError:
                        pass
                # Если это не JSON — не пробуем JSON
                if not looks_jsonish:
                    break

    # JSON путь
    data = None
    last_err = None
    for decoded in text_candidates:
        stripped = decoded.lstrip("\ufeff\x00\n\r\t ")
        if not (stripped.startswith("{") or stripped.startswith("[")):
            continue
        try:
            data = _json_loads(decoded)
            break
        except Exception as e:
            last_err = e

    if data is not None:
        return parse_data(data, str(p))

    # Запасной текстовый путь
    for decoded_text in text_candidates:
        if _looks_like_text_log_head(decoded_text):
            return parse_text_log(decoded_text, str(p), text_options)

    raise ParseError(f"Failed to read JSON: {last_err}")
