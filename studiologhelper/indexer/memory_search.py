# -*- coding: utf-8 -*-
"""Быстрый поиск в RAM по уже загруженным чатам — ripgrep-like + стемминг/морфология.

Оптимизации (рефакторинг 2026):
- text_lower вычисляется один раз на кандидата (раньше 2-3 раза).
- regex-поиск использует один reg.search (раньше два на каждый текст).
- Предкомпилированный whitespace-regex для сниппетов.
- Пул потоков: as_completed + отмена незапущенных фьючерсов при раннем выходе.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..core.models import ChatLog
from .stemmer import match_stemmed_query

_RE_WS = re.compile(r"\s+")


@dataclass
class MemoryHit:
    chat_path: str
    chat_title: str
    model: str
    msg_num: int
    role: str
    is_thought: bool
    snippet: str
    score: int


def _plain_snippet(text: str, q: str, limit: int = 220, match_spans: Optional[List[Tuple[int, int]]] = None) -> str:
    """Точный сниппет без смещения позиций при форматировании пробелов."""
    if not text:
        return ""
    if match_spans and len(match_spans) > 0:
        pos, end = match_spans[0]
        a = max(0, pos - 70)
        b = min(len(text), end + 140)
        raw_slice = text[a:b]
        frag = _RE_WS.sub(" ", raw_slice).strip()
        return ("…" if a > 0 else "") + frag + ("…" if b < len(text) else "")

    pos = text.lower().find(q.lower())
    if pos < 0:
        cleaned = _RE_WS.sub(" ", text).strip()
        return cleaned[:limit] + ("…" if len(cleaned) > limit else "")
    a = max(0, pos - 70)
    b = min(len(text), pos + len(q) + 140)
    raw_slice = text[a:b]
    frag = _RE_WS.sub(" ", raw_slice).strip()
    return ("…" if a > 0 else "") + frag + ("…" if b < len(text) else "")


def _iter_candidates(chat: ChatLog, scope: str):
    """Генератор (text, role, is_thought) с учётом scope — без лишних аллокаций."""
    for num, msg in enumerate(chat.messages, 1):
        candidates = []
        if scope in ("all", "user") and msg.is_user and msg.text:
            candidates.append((msg.text, "user", False))
        if scope in ("all", "model") and not msg.is_user and msg.text:
            candidates.append((msg.text, "model", False))
        if msg.has_thoughts and scope in ("all", "thoughts"):
            for t in msg.thoughts:
                candidates.append((t, "model", True))
        if candidates:
            yield num, candidates


def _search_one_chat(args) -> List[MemoryHit]:
    chat, q_original, scope, use_stemming = args
    hits: List[MemoryHit] = []
    q_lower = q_original.lower()

    for num, candidates in _iter_candidates(chat, scope):
        for text, role, is_thought in candidates:
            text_lower = text.lower()  # один раз на кандидата
            if q_lower in text_lower:
                score = text_lower.count(q_lower) * 5
                hits.append(
                    MemoryHit(
                        chat_path=chat.path,
                        chat_title=chat.title,
                        model=chat.model,
                        msg_num=num,
                        role=role,
                        is_thought=is_thought,
                        snippet=_plain_snippet(text, q_original),
                        score=score,
                    )
                )
                break
            elif use_stemming:
                matched, score, spans = match_stemmed_query(q_original, text)
                if matched:
                    hits.append(
                        MemoryHit(
                            chat_path=chat.path,
                            chat_title=chat.title,
                            model=chat.model,
                            msg_num=num,
                            role=role,
                            is_thought=is_thought,
                            snippet=_plain_snippet(text, q_original, match_spans=spans),
                            score=score,
                        )
                    )
                    break

    return hits


def fast_search_chats(
    chats: List[ChatLog],
    query: str,
    scope: str = "all",
    max_workers: int = 4,
    limit: int = 300,
    use_stemming: bool = True,
) -> List[MemoryHit]:
    """Параллельный поиск по загруженным чатам с поддержкой стемминга и словоформ."""
    if not query.strip():
        return []
    q_original = query.strip()

    if len(chats) <= 4 or max_workers <= 1:
        all_hits: List[MemoryHit] = []
        for chat in chats:
            all_hits.extend(_search_one_chat((chat, q_original, scope, use_stemming)))
            if len(all_hits) >= limit:
                break
        all_hits.sort(key=lambda h: h.score, reverse=True)
        return all_hits[:limit]

    all_hits = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [
            ex.submit(_search_one_chat, (chat, q_original, scope, use_stemming))
            for chat in chats
        ]
        try:
            for fut in as_completed(futures):
                try:
                    hits = fut.result()
                except Exception:
                    continue
                all_hits.extend(hits)
                if len(all_hits) >= limit * 2:
                    break
        finally:
            # Отменяем незапущенные задачи — пул не ждёт их при выходе
            for fut in futures:
                fut.cancel()

    all_hits.sort(key=lambda h: h.score, reverse=True)
    return all_hits[:limit]


def regex_search_chats(chats: List[ChatLog], pattern: str, scope: str = "all") -> List[MemoryHit]:
    try:
        reg = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return fast_search_chats(chats, pattern, scope)

    hits: List[MemoryHit] = []
    for chat in chats:
        for num, candidates in _iter_candidates(chat, scope):
            for text, role, is_thought in candidates:
                m = reg.search(text)  # один поиск вместо двух
                if m:
                    snippet = _plain_snippet(text, m.group(0) if m else text[:20])
                    hits.append(
                        MemoryHit(
                            chat_path=chat.path,
                            chat_title=chat.title,
                            model=chat.model,
                            msg_num=num,
                            role=role,
                            is_thought=is_thought,
                            snippet=snippet,
                            score=1,
                        )
                    )
                    break
    return hits
