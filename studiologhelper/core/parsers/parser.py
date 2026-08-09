# -*- coding: utf-8 -*-
"""Top-level parse_file с оптимизациями + плагины + streaming."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..exceptions import ParseError
from .base import TextParseOptions
from .detector import _looks_like_text_log_head
from .json_parser import _json_loads, parse_data
from .text_parser import parse_text_log
from ...utils.encoding import detect_encoding_and_decode
from ...utils.logger import get_logger

logger = get_logger()


def parse_file(path, text_options: Optional[TextParseOptions] = None, use_plugins: bool = True, use_streaming: bool = True):
    """Читает и парсит файл, оптимизированный путь для TXT vs JSON + плагины + streaming."""
    p = Path(path)
    try:
        # Если большой файл и ijson установлен — используем стриминг сразу, не читая весь файл в RAM
        if use_streaming:
            try:
                from .streaming_json_parser import should_use_streaming, parse_large_json_streaming

                if should_use_streaming(p):
                    logger.info(f"Using streaming parser for large file {p} ({p.stat().st_size / 1024 / 1024:.1f} MB)")
                    return parse_large_json_streaming(p)
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"Streaming parser failed for {p}, fallback to normal: {e}")

        data_bytes = p.read_bytes()
    except OSError as e:
        raise ParseError(f"Cannot read file: {e}") from e

    suffix = p.suffix.lower()
    text_candidates: list[str] = []

    try:
        decoded_once = detect_encoding_and_decode(data_bytes)
        text_candidates.append(decoded_once)
    except Exception:
        pass

    # Попытка через плагины (Claude, ChatGPT, etc.) — быстро по head
    if use_plugins and text_candidates:
        try:
            from ..plugins import get_global_registry

            head = text_candidates[0][:8192]
            registry = get_global_registry()
            # Сначала ищем плагин по head
            plugin_result = registry.parse_with_plugin(p, head, text_options)
            if plugin_result:
                logger.info(f"Parsed {p} with plugin")
                return plugin_result
        except Exception as e:
            logger.debug(f"Plugin parsing failed for {p}: {e}")

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
                if suffix in {".txt", ".md"}:
                    try:
                        return parse_text_log(decoded_text, str(p), text_options)
                    except ParseError:
                        pass
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
