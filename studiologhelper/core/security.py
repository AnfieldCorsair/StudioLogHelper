# -*- coding: utf-8 -*-
"""security.py — Санитизация HTML, валидация URL и безопасность плагинов."""

from __future__ import annotations

import html as _html
import re
from typing import Set

# Разрешённые безопасные URI-схемы
ALLOWED_URL_SCHEMES: Set[str] = {"http", "https", "mailto", "drive"}

# Опасные теги, которые полностью удаляются или обезвреживаются
DANGEROUS_TAGS_PATTERN = re.compile(
    r"<\s*(script|iframe|object|embed|applet|form|input|button|select|textarea|style|link|meta|base)\b[^>]*>.*?</\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
SELF_CLOSING_DANGEROUS_TAGS = re.compile(
    r"<\s*(script|iframe|object|embed|applet|form|input|meta|link|base)\b[^>]*\/?>",
    re.IGNORECASE,
)

# Опасные inline-события JavaScript (onclick, onerror, onload, onmouseover и т.д.)
DANGEROUS_ATTRIBUTES_PATTERN = re.compile(
    r"""\s+(on[a-zA-Z]+\s*=\s*(?:'[^']*'|"[^"]*"|[^\s>]+))""",
    re.IGNORECASE,
)

# Опасные псевдо-протоколы в ссылках (javascript:, data:text/html, vbscript:)
DANGEROUS_SCHEMES_PATTERN = re.compile(
    r"""href\s*=\s*(?:['"]\s*(?:javascript|vbscript|data\s*:\s*text\/html):[^'"]*['"]|javascript:[^\s>]+)""",
    re.IGNORECASE,
)


def is_safe_url(url: str) -> bool:
    """Проверяет, является ли URL безопасным (http, https, mailto, drive)."""
    if not url:
        return False
    u = url.strip().lower()
    # Защита от javascript: и vbscript:
    if any(u.startswith(proto) for proto in ("javascript:", "vbscript:", "data:text/html", "file:")):
        return False
    # Проверка схемы
    match = re.match(r"^([a-zA-Z0-9+-.]+):", u)
    if match:
        scheme = match.group(1)
        return scheme in ALLOWED_URL_SCHEMES
    # Относительные ссылки внутри документа (#anchor)
    if u.startswith("#"):
        return True
    return False


def sanitize_url(url: str) -> str:
    """Обезвреживает потенциально опасный URL."""
    if is_safe_url(url):
        return url
    return "#"


def sanitize_html(html_str: str) -> str:
    """
    Санитизирует HTML-строку:
    1. Удаляет исполняемые теги (<script>, <iframe>, <object>, <embed>, <form> и др.).
    2. Вычищает опасные атрибуты событий (onload, onerror, onclick и т.д.).
    3. Блокирует псевдо-протоколы javascript: и vbscript: в ссылках.
    4. Добавляет rel="noopener noreferrer" ко всем внешним ссылкам.
    """
    if not html_str:
        return ""

    # 1. Удаление парных опасных тегов
    cleaned = DANGEROUS_TAGS_PATTERN.sub("", html_str)
    # 2. Удаление одиночных опасных тегов
    cleaned = SELF_CLOSING_DANGEROUS_TAGS.sub("", cleaned)
    # 3. Удаление inline JavaScript обработчиков
    cleaned = DANGEROUS_ATTRIBUTES_PATTERN.sub("", cleaned)
    # 4. Блокировка javascript: ссылок
    cleaned = DANGEROUS_SCHEMES_PATTERN.sub('href="#"', cleaned)

    # 5. Добавление rel="noopener noreferrer" ко всем <a href="http...">
    def add_rel(m: re.Match) -> str:
        tag = m.group(0)
        if "rel=" not in tag.lower():
            return tag[:-1] + ' rel="noopener noreferrer">'
        return tag

    cleaned = re.sub(r'<a\s+[^>]*href=["\']https?://[^"\']*["\'][^>]*>', add_rel, cleaned, flags=re.IGNORECASE)

    return cleaned
