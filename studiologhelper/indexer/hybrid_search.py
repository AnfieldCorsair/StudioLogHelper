# -*- coding: utf-8 -*-
"""hybrid_search.py — Гибридный поисковый движок (FTS5 + Стемминг + Локальные субсловные эмбеддинги).

Объединяет:
  1. Лексический поиск (Exact / FTS5 BM25)
  2. Морфологический стемминг (Словоформы, Портер RU/EN)
  3. Субсловные/n-граммные локальные эмбеддинги и косинусную близость (Semantic/Fuzzy)
  4. Взвешенный скоринг без смещения оффсетов сниппетов
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from ..core.models import ChatLog, Message
from .stemmer import match_stemmed_query, stem_word


@dataclass
class HybridHit:
    chat_path: str
    chat_title: str
    model: str
    msg_num: int
    role: str
    is_thought: bool
    snippet: str
    score: float
    fts_score: float = 0.0
    stem_score: float = 0.0
    semantic_score: float = 0.0
    match_highlights: List[Tuple[int, int]] = None  # type: ignore


def compute_subword_vector(text: str, n_range: Tuple[int, int] = (3, 4)) -> Dict[str, float]:
    """Строит нормализованный TF-вектор символьных n-грамм для локального семантического сопоставления."""
    cleaned = re.sub(r"\s+", " ", text.lower()).strip()
    if not cleaned:
        return {}

    grams: Counter[str] = Counter()
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9_]+", cleaned)

    for word in words:
        w_len = len(word)
        for n in range(n_range[0], min(n_range[1] + 1, w_len + 1)):
            for i in range(w_len - n + 1):
                grams[word[i : i + n]] += 1
        if w_len < n_range[0]:
            grams[word] += 2

    total_sq = sum(c * c for c in grams.values())
    if total_sq == 0:
        return {}
    norm = math.sqrt(total_sq)
    return {k: v / norm for k, v in grams.items()}


def cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    """Вычисляет косинусное сходство двух нормализованных векторов."""
    if not vec_a or not vec_b:
        return 0.0
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    return sum(val * vec_b.get(key, 0.0) for key, val in vec_a.items())


def build_snippet(text: str, spans: List[Tuple[int, int]], limit: int = 240) -> str:
    """Извлекает точный сниппет из оригинального текста с защитой от смещения позиций."""
    if not text:
        return ""
    if not spans:
        cleaned = re.sub(r"\s+", " ", text).strip()
        return cleaned[:limit] + ("…" if len(cleaned) > limit else "")

    first_start, first_end = spans[0]
    a = max(0, first_start - 70)
    b = min(len(text), first_end + 150)
    raw_slice = text[a:b]
    cleaned_slice = re.sub(r"\s+", " ", raw_slice).strip()

    prefix = "…" if a > 0 else ""
    suffix = "…" if b < len(text) else ""
    return prefix + cleaned_slice + suffix


class HybridSearchEngine:
    """Гибридный движок поиска по чатам в оперативной памяти и БД."""

    def __init__(self, alpha_exact: float = 0.4, beta_stem: float = 0.4, gamma_semantic: float = 0.2):
        self.alpha = alpha_exact
        self.beta = beta_stem
        self.gamma = gamma_semantic
        self._vector_cache: Dict[str, Dict[str, float]] = {}

    def _get_or_compute_vector(self, text: str) -> Dict[str, float]:
        key = hash(text)
        if key in self._vector_cache:
            return self._vector_cache[key]
        vec = compute_subword_vector(text)
        if len(self._vector_cache) > 2000:
            self._vector_cache.clear()
        self._vector_cache[key] = vec
        return vec

    def search_chats(
        self,
        chats: List[ChatLog],
        query: str,
        scope: str = "all",
        limit: int = 300,
    ) -> List[HybridHit]:
        if not query.strip() or not chats:
            return []

        q_clean = query.strip()
        q_lower = q_clean.lower()
        q_vec = compute_subword_vector(q_clean)

        hits: List[HybridHit] = []

        for chat in chats:
            for num, msg in enumerate(chat.messages, 1):
                candidates: List[Tuple[str, str, bool]] = []
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
                    text_lower = text.lower()

                    # 1. Точный лексический скор (Exact / Substring)
                    fts_score = 0.0
                    spans: List[Tuple[int, int]] = []
                    if q_lower in text_lower:
                        count = text_lower.count(q_lower)
                        fts_score = min(1.0, 0.5 + count * 0.15)
                        for m in re.finditer(re.escape(q_lower), text_lower):
                            spans.append((m.start(), m.end()))

                    # 2. Морфологический стемминг (Stemming)
                    stem_matched, stem_raw_score, stem_spans = match_stemmed_query(q_clean, text)
                    stem_score = 0.0
                    if stem_matched:
                        stem_score = min(1.0, stem_raw_score / 10.0)
                        for s in stem_spans:
                            if s not in spans:
                                spans.append(s)

                    # 3. Семантическая векторная близость (Subword Dense Vector)
                    doc_vec = self._get_or_compute_vector(text)
                    sem_score = cosine_similarity(q_vec, doc_vec)

                    # Комбинированный гибридный скор
                    total_score = (
                        self.alpha * fts_score
                        + self.beta * stem_score
                        + self.gamma * (sem_score if (fts_score > 0 or stem_score > 0 or sem_score > 0.35) else 0.0)
                    )

                    if total_score > 0.15 or fts_score > 0 or stem_matched:
                        spans.sort(key=lambda x: x[0])
                        snippet = build_snippet(text, spans)
                        hits.append(
                            HybridHit(
                                chat_path=chat.path,
                                chat_title=chat.title,
                                model=chat.model,
                                msg_num=num,
                                role=role,
                                is_thought=is_thought,
                                snippet=snippet,
                                score=round(total_score * 100, 2),
                                fts_score=round(fts_score, 3),
                                stem_score=round(stem_score, 3),
                                semantic_score=round(sem_score, 3),
                                match_highlights=spans,
                            )
                        )
                        break

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]
