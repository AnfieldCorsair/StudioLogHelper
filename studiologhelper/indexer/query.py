# -*- coding: utf-8 -*-
import re


def sanitize_query(q: str) -> str:
    """Безопасный FTS5 запрос: слова AND, последнее префикс, фразы в кавычках."""
    q = q.strip()
    if not q:
        return ""
    phrases = re.findall(r'"([^"]+)"', q)
    rest = re.sub(r'"[^"]*"', " ", q)
    words = re.findall(r"[\w\d_]+", rest, re.UNICODE)
    parts = [f'"{p}"' for p in phrases]
    for i, w in enumerate(words):
        if i == len(words) - 1 and not phrases:
            parts.append(f'"{w}"*')
        else:
            parts.append(f'"{w}"')
    return " AND ".join(parts)
