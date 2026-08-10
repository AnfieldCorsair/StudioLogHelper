# -*- coding: utf-8 -*-
"""Быстрый поиск в RAM по уже загруженным чатам — ripgrep-like + стемминг/морфология."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Tuple

from ..core.models import ChatLog
from .stemmer import match_stemmed_query


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


def _plain_snippet(text: str, q: str, limit: int = 220, match_spans: List[Tuple[int, int]] | None = None) -> str:
    one = re.sub(r"\s+", " ", text).strip()
    if not one:
        return ""
    if match_spans and len(match_spans) > 0:
        pos, end = match_spans[0]
        a = max(0, pos - 70)
        b = min(len(text), end + 140)
        frag = text[a:b].replace("\n", " ").strip()
        return ("…" if a > 0 else "") + frag + ("…" if b < len(text) else "")

    pos = one.lower().find(q.lower())
    if pos < 0:
        return one[:limit] + ("…" if len(one) > limit else "")
    a = max(0, pos - 70)
    b = min(len(one), pos + len(q) + 140)
    return ("…" if a else "") + one[a:b] + ("…" if b < len(one) else "")


def _search_one_chat(args) -> List[MemoryHit]:
    chat, q_original, scope, use_stemming = args
    hits: List[MemoryHit] = []
    q_lower = q_original.lower()

    for num, msg in enumerate(chat.messages, 1):
        candidates = []
        if scope in ("all", "user") and msg.is_user and msg.text:
            candidates.append((msg.text, "user", False))
        if scope in ("all", "model") and not msg.is_user and msg.text:
            candidates.append((msg.text, "model", False))
        if scope in ("all", "thoughts") and msg.has_thoughts:
            for t in msg.thoughts:
                candidates.append((t, "model", True))
        elif scope == "thoughts" and msg.has_thoughts:
            for t in msg.thoughts:
                candidates.append((t, "model", True))

        for text, role, is_thought in candidates:
            # 1. Прямой быстрый поиск
            if q_lower in text.lower():
                score = text.lower().count(q_lower) * 5
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
            # 2. Если прямой не найден и включён стемминг/морфология
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
        for fut in futures:
            try:
                hits = fut.result()
                all_hits.extend(hits)
                if len(all_hits) >= limit * 2:
                    break
            except Exception:
                continue

    all_hits.sort(key=lambda h: h.score, reverse=True)
    return all_hits[:limit]


def regex_search_chats(chats: List[ChatLog], pattern: str, scope: str = "all") -> List[MemoryHit]:
    try:
        reg = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return fast_search_chats(chats, pattern, scope)

    hits: List[MemoryHit] = []
    for chat in chats:
        for num, msg in enumerate(chat.messages, 1):
            candidates = []
            if scope in ("all", "user") and msg.is_user and msg.text:
                candidates.append((msg.text, "user", False))
            if scope in ("all", "model") and not msg.is_user and msg.text:
                candidates.append((msg.text, "model", False))
            if scope in ("all", "thoughts") and msg.has_thoughts:
                for t in msg.thoughts:
                    candidates.append((t, "model", True))
            for text, role, is_thought in candidates:
                if reg.search(text):
                    m = reg.search(text)
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
