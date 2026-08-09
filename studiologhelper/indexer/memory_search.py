# -*- coding: utf-8 -*-
"""Быстрый поиск в RAM по уже загруженным чатам — ripgrep-like."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Tuple

from ..core.models import ChatLog


@dataclass
class MemoryHit:
    chat_path: str
    chat_title: str
    model: str
    msg_num: int
    role: str
    is_thought: bool
    snippet: str
    score: int  # lower is better? or count


def _plain_snippet(text: str, q: str, limit: int = 220) -> str:
    one = re.sub(r"\s+", " ", text).strip()
    if not one:
        return ""
    pos = one.lower().find(q.lower())
    if pos < 0:
        return one[:limit] + ("…" if len(one) > limit else "")
    a = max(0, pos - 70)
    b = min(len(one), pos + len(q) + 140)
    return ("…" if a else "") + one[a:b] + ("…" if b < len(one) else "")


def _search_one_chat(args) -> List[MemoryHit]:
    chat, q_lower, q_original, scope = args
    hits: List[MemoryHit] = []
    for num, msg in enumerate(chat.messages, 1):
        # scope filter
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
            if q_lower in text.lower():
                hits.append(
                    MemoryHit(
                        chat_path=chat.path,
                        chat_title=chat.title,
                        model=chat.model,
                        msg_num=num,
                        role=role,
                        is_thought=is_thought,
                        snippet=_plain_snippet(text, q_original),
                        score=text.lower().count(q_lower),
                    )
                )
                break  # one hit per message
    return hits


def fast_search_chats(chats: List[ChatLog], query: str, scope: str = "all", max_workers: int = 4, limit: int = 300) -> List[MemoryHit]:
    """Параллельный поиск по загруженным чатам."""
    if not query.strip():
        return []
    q_lower = query.lower()
    q_original = query

    # Если чатов мало, не используем потоки
    if len(chats) <= 4 or max_workers <= 1:
        all_hits: List[MemoryHit] = []
        for chat in chats:
            all_hits.extend(_search_one_chat((chat, q_lower, q_original, scope)))
            if len(all_hits) >= limit:
                break
        # sort by score desc
        all_hits.sort(key=lambda h: h.score, reverse=True)
        return all_hits[:limit]

    # Parallel
    all_hits = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_search_one_chat, (chat, q_lower, q_original, scope)) for chat in chats]
        for fut in futures:
            try:
                hits = fut.result()
                all_hits.extend(hits)
                if len(all_hits) >= limit * 2:  # early stop a bit over
                    break
            except Exception:
                continue

    all_hits.sort(key=lambda h: h.score, reverse=True)
    return all_hits[:limit]


# Optional: regex search with Aho-Corasick if many queries
def regex_search_chats(chats: List[ChatLog], pattern: str, scope: str = "all") -> List[MemoryHit]:
    try:
        reg = re.compile(pattern, re.IGNORECASE)
    except re.error:
        # fallback to plain
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
                    hits.append(MemoryHit(chat_path=chat.path, chat_title=chat.title, model=chat.model, msg_num=num, role=role, is_thought=is_thought, snippet=snippet, score=1))
                    break
    return hits
