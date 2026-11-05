# -*- coding: utf-8 -*-
"""security.py — Санитизация HTML, валидация URL и безопасность плагинов.

Оптимизации (рефакторинг 2026): все regex предкомпилированы, sanitize_html
имеет быстрый выход для строк без '<'.
"""

from __future__ import annotations

import html as _html
import re
import urllib.parse
from typing import Set

ALLOWED_URL_SCHEMES: Set[str] = {"http", "https", "mailto", "drive"}

DANGEROUS_TAGS_PATTERN = re.compile(
    r"<\s*(script|iframe|object|embed|applet|form|input|button|select|textarea|style|link|meta|base)\b[^>]*>.*?</\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
SELF_CLOSING_DANGEROUS_TAGS = re.compile(
    r"<\s*(script|iframe|object|embed|applet|form|input|meta|link|base)\b[^>]*\/?>",
    re.IGNORECASE,
)

DANGEROUS_ATTRIBUTES_PATTERN = re.compile(
    r"""\s+(on[a-zA-Z]+\s*=\s*(?:'[^']*'|"[^"]*"|[^\s>]+))""",
    re.IGNORECASE,
)

# Предкомпилированные паттерны для горячих путей
_RE_STRIP_CTL = re.compile(r"[\s\x00-\x1f\x7f]+")
_RE_SCHEME = re.compile(r"^([a-zA-Z0-9+-.]+):")
_RE_A_TAG = re.compile(r"<a\s+[^>]*href=[\"'][^\"']*[\"'][^>]*>", re.IGNORECASE)
_RE_HREF = re.compile(r'href\s*=\s*(["\'])(.*?)\1', re.IGNORECASE)
_RE_HREF_HTTP = re.compile(r'href\s*=\s*["\']https?://', re.IGNORECASE)


def _normalize_scheme_text(val: str) -> str:
    """Декодирует HTML entities и URL-encoding для выявления скрытых протоколов."""
    if not val:
        return ""
    # Разворачиваем HTML entities (напр. jav&#x61;script:)
    decoded = _html.unescape(val)
    # Разворачиваем URL-encoding (%6a%61%76%61...)
    try:
        decoded = urllib.parse.unquote(decoded)
    except Exception:
        pass
    # Удаляем управляющие и невидимые символы
    return _RE_STRIP_CTL.sub("", decoded).lower()


def is_safe_url(url: str) -> bool:
    """Проверяет, является ли URL безопасным (http, https, mailto, drive, #anchor)."""
    if not url:
        return False
    normalized = _normalize_scheme_text(url)

    # Защита от javascript:, vbscript:, data:text/html, file: в любых кодировках
    if any(normalized.startswith(proto) for proto in ("javascript:", "vbscript:", "data:text/html", "data:text/javascript", "file:")):
        return False

    match = _RE_SCHEME.match(normalized)
    if match:
        scheme = match.group(1)
        return scheme in ALLOWED_URL_SCHEMES

    if url.strip().startswith("#"):
        return True
    return False


def sanitize_url(url: str) -> str:
    """Обезвреживает потенциально опасный URL."""
    if is_safe_url(url):
        return url.strip()
    return "#"


def sanitize_html(html_str: str) -> str:
    """
    Санитизирует HTML-строку:
    1. Удаляет опасные теги (<script>, <iframe>, <object> и др.).
    2. Вычищает inline JavaScript обработчики событий.
    3. Блокирует скрытые и entity-encoded javascript: ссылки.
    4. Добавляет rel="noopener noreferrer" к внешним ссылкам.
    """
    if not html_str:
        return ""
    if "<" not in html_str:
        # Без тегов санитизировать нечего — быстрый выход
        return html_str

    cleaned = DANGEROUS_TAGS_PATTERN.sub("", html_str)
    cleaned = SELF_CLOSING_DANGEROUS_TAGS.sub("", cleaned)
    cleaned = DANGEROUS_ATTRIBUTES_PATTERN.sub("", cleaned)

    # Проверка и санитизация ссылок <a href="..."> с декодированием entities
    def clean_link_tag(m: re.Match) -> str:
        tag = m.group(0)
        href_match = _RE_HREF.search(tag)
        if href_match:
            raw_url = href_match.group(2)
            if not is_safe_url(raw_url):
                tag = tag[:href_match.start(2)] + "#" + tag[href_match.end(2):]
        if "rel=" not in tag.lower() and _RE_HREF_HTTP.search(tag):
            tag = tag[:-1] + ' rel="noopener noreferrer">'
        return tag

    cleaned = _RE_A_TAG.sub(clean_link_tag, cleaned)

    return cleaned
