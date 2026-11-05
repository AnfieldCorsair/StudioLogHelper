# -*- coding: utf-8 -*-
"""Текстовый парсер Arena AI / очищенных экспортов.

Оптимизации (рефакторинг 2026):
- Наборы заголовков (user/model) собираются ОДИН раз на файл, а не на каждую строку.
- Bare-детекция заголовков выполняется только для коротких строк (заголовки
  не могут быть длинными) — раньше _norm_header с regex шёл по всему тексту строки.
- _RE_PLAIN_HEADER / export-заголовки проверяются только при наличии ':' /
  стартовых символов — быстрые C-проверки вместо regex на каждой строке.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional, Set

from ..exceptions import ParseError
from ..models import ChatLog, Message
from .base import TextParseOptions
from .detector import _looks_like_text_log_head

# --- compiled regex cache ---
_RE_ARENA_SIDE = re.compile(r"(?im)^\s*Arena\s+Side-by-Side\s+Chat\s*$")
_RE_NUMBERED = re.compile(r"^\s*#(?P<num>\d+)\s*:\s*(?P<rest>.*)$")
_RE_PLAIN_HEADER = re.compile(r"^\s*(?P<header>[\wА-Яа-яЁё][\wА-Яа-яЁё ._-]{0,60})\s*:\s*(?P<rest>.*)$")
_RE_EXPORT_DASH = re.compile(r"^-{3,}\s*#(?P<num>\d+)\s+(?P<label>.*?)\s*-{3,}\s*$")
_RE_EXPORT_MD = re.compile(r"^#{1,6}\s+#(?P<num>\d+)\s+(?P<label>.+?)\s*$")
_RE_TIME_BRACKETS = re.compile(r"\[[^\]]+\]")
_RE_SPACES = re.compile(r"\s+")

DEFAULT_USER_HEADERS = (
    "user", "пользователь", "human", "prompt", "request", "запрос",
)
DEFAULT_MODEL_HEADERS = (
    "right ai", "right model", "model", "modelname", "assistant", "ai",
    "answer", "response", "модель", "ассистент", "ответ",
)

# Заголовки в safe_bare гарантированно короткие — guard по длине строки
_BARE_MAX_LEN = 80


def _norm_header(s: str) -> str:
    s = s.strip().strip(":").strip()
    s = _RE_SPACES.sub(" ", s).lower()
    return s


def _merged_headers(extra: list, defaults: tuple) -> set[str]:
    vals = set(defaults)
    for x in extra or []:
        nx = _norm_header(str(x))
        if nx:
            vals.add(nx)
    return vals


class _RoleResolver:
    """Предвычисленные наборы заголовков — резолвинг ролей без пересборки сетов."""

    __slots__ = ("user_headers", "model_headers")

    def __init__(self, opts: TextParseOptions):
        self.user_headers = _merged_headers(opts.user_headers, DEFAULT_USER_HEADERS)
        self.model_headers = _merged_headers(opts.model_headers, DEFAULT_MODEL_HEADERS)

    def resolve(self, header: str) -> Optional[str]:
        h = _norm_header(header)
        if h in self.user_headers:
            return "user"
        if h in self.model_headers:
            return "model"
        if h.startswith("right ") or h.startswith("model "):
            return "model"
        return None

    def resolve_norm(self, norm: str) -> Optional[str]:
        """Резолвинг по уже нормализованному заголовку (для bare-строк)."""
        if norm in self.user_headers:
            return "user"
        if norm in self.model_headers:
            return "model"
        return None


def _role_from_header(header: str, opts: TextParseOptions) -> Optional[str]:
    """Совместимая обёртка (создаёт резолвер — используйте _RoleResolver в циклах)."""
    return _RoleResolver(opts).resolve(header)


def _role_for_number(num: int, opts: TextParseOptions) -> str:
    mode = (opts.numbered_mode or "model").lower()
    if mode == "model":
        return "model"
    if mode == "user":
        return "user"
    return "user" if num % 2 == 1 else "model"


def _flush(chat: ChatLog, role: Optional[str], buf: list):
    text = "\n".join(buf).strip("\n")
    if role and text.strip():
        chat.messages.append(Message(role=role, text=text))


def _parse_export_header(line: str):
    stripped = line.strip()
    if not stripped:
        return None
    m = _RE_EXPORT_DASH.match(stripped)
    if m:
        return int(m.group("num")), m.group("label").strip()
    m = _RE_EXPORT_MD.match(stripped)
    if m:
        return int(m.group("num")), m.group("label").strip()
    return None


def parse_text_log(text: str, path: str = "", options: Optional[TextParseOptions] = None) -> ChatLog:
    opts = options or TextParseOptions()
    chat = ChatLog(
        path=path,
        title=Path(path).stem if path else "Untitled",
        source_format="text",
        raw_text=text,
    )
    if _RE_ARENA_SIDE.search(text):
        chat.model = "Arena AI"

    resolver = _RoleResolver(opts)
    role: Optional[str] = None
    buf: list[str] = []
    saw_numbered = False

    # safe bare set for lines without colon (один раз на файл).
    # ВНИМАНИЕ: только ДОПОЛНИТЕЛЬНЫЕ заголовки из опций (не DEFAULT_*):
    # слова вроде "answer"/"response" валидны как "Answer: ..." (plain-заголовок),
    # но не как bare-строка (иначе тело текста ошибочно станет заголовком).
    safe_bare: Set[str] = {
        "user", "пользователь", "human",
        "right ai", "right model", "model", "modelname",
        "assistant", "ai", "модель", "ассистент",
    } | _merged_headers(opts.user_headers, ()) | _merged_headers(opts.model_headers, ())

    for line in text.splitlines():
        if _RE_ARENA_SIDE.match(line):
            continue

        # Bare-заголовок: нормализация только для коротких строк
        stripped_line = line.strip()
        if len(stripped_line) <= _BARE_MAX_LEN:
            bare_norm = _norm_header(stripped_line)
            if bare_norm in safe_bare:
                bare_role = resolver.resolve_norm(bare_norm)
                if bare_role:
                    _flush(chat, role, buf)
                    buf = []
                    role = bare_role
                    continue

        m = _RE_NUMBERED.match(line)
        if m:
            _flush(chat, role, buf)
            buf = []
            n = int(m.group("num"))
            saw_numbered = True
            role = _role_for_number(n, opts)
            rest = m.group("rest")
            if rest:
                buf.append(rest)
            continue

        # Export-заголовки: быстрый guard по стартовым символам
        if stripped_line[:1] in ("-", "#"):
            exported = _parse_export_header(line)
            if exported:
                n, label = exported
                label = _RE_TIME_BRACKETS.sub("", label).strip(" -—\t")
                detected = resolver.resolve(label) or _role_for_number(n, opts)
                _flush(chat, role, buf)
                buf = []
                saw_numbered = True
                role = detected
                continue

        # Plain-заголовок "Role: text" — только если в строке есть ':'
        if ":" in line:
            m = _RE_PLAIN_HEADER.match(line)
            if m:
                if role is None and line[:1].isspace():
                    continue
                detected = resolver.resolve(m.group("header"))
                if detected:
                    _flush(chat, role, buf)
                    buf = []
                    role = detected
                    rest = m.group("rest")
                    if rest:
                        buf.append(rest)
                    continue

        if role is not None:
            buf.append(line)

    _flush(chat, role, buf)

    if saw_numbered and (opts.numbered_mode or "model") == "alternating":
        chat.warnings.append("Numbered #1/#2 blocks were parsed as user/model alternation.")

    if not chat.messages:
        raise ParseError("Could not parse text log: no User/Model/#N blocks found.")
    return chat
