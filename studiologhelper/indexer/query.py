# -*- coding: utf-8 -*-
"""query.py — Санитизация FTS5-запросов (regex предкомпилированы)."""
import re

_RE_QUOTED = re.compile(r'"([^"]+)"')
_RE_QUOTED_REM = re.compile(r'"[^"]*"')
_RE_WORD = re.compile(r"[\w\d_]+", re.UNICODE)


def sanitize_query(q: str) -> str:
    """Безопасный FTS5 запрос: слова AND, последнее префикс, фразы в кавычках."""
    q = q.strip()
    if not q:
        return ""
    phrases = _RE_QUOTED.findall(q)
    rest = _RE_QUOTED_REM.sub(" ", q)
    words = _RE_WORD.findall(rest)
    parts = [f'"{p}"' for p in phrases]
    for i, w in enumerate(words):
        if i == len(words) - 1 and not phrases:
            parts.append(f'"{w}"*')
        else:
            parts.append(f'"{w}"')
    return " AND ".join(parts)
