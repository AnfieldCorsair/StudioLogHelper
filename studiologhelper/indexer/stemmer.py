# -*- coding: utf-8 -*-
"""stemmer.py — Легковесный морфологический стеммер и поиск по смыслу/словоформам (RU + EN).

Не требует внешних тяжёлых библиотек (NLTK, PyMorphy).
Реализует алгоритм Портера (Snowball Stemmer) для русского и английского языков
с дополнительной обработкой диминутивов и префиксов, позволяя находить:
«сковородка» -> «сковорода», «сковородку», «сковородой», «сковороде».
"""

from __future__ import annotations

import re
from typing import List, Set, Tuple

# ---- Русский стеммер Портера ----
_RU_PERFECTIVE_GERUND = re.compile(
    r"((ив|ивши|ившись|ыв|ывши|ывшись)|((?<=[ая])(в|вши|вшись)))$"
)
_RU_ADJECTIVE = re.compile(
    r"(ее|ие|ые|ое|ими|ыми|ей|ий|ый|ой|ем|им|ым|ом|его|ого|ему|ому|их|ых|ую|юю|ая|яя|ою|ею)$"
)
_RU_PARTICIPLE = re.compile(
    r"(((ивш|ывш)|((?<=[ая])(ем|нн|вш|ющ|щ)))(?=ее|ие|ые|ое|ими|ыми|ей|ий|ый|ой|ем|им|ым|ом|его|ого|ему|ому|их|ых|ую|юю|ая|яя|ою|ею))"
)
_RU_REFLEXIVE = re.compile(r"(ся|сь)$")
_RU_VERB = re.compile(
    r"((ила|ыла|ена|ейте|уйте|ите|или|ыли|ей|уй|ил|ыл|им|ым|ен|ило|ыло|ено|ят|ует|уют|ит|ыт|ены|ить|ыть|ишь|ую|ю)|((?<=[ая])(ла|на|ете|йте|ли|й|л|ем|н|ло|но|ет|ют|ны|ть|ешь|нно)))$"
)
_RU_NOUN = re.compile(
    r"(а|ев|ов|ие|ье|е|иями|ями|ами|еи|ии|и|ией|ей|ой|ий|й|иям|ям|ием|ем|ам|ом|о|у|ах|иях|ях|ы|ь|ию|ью|ю|ия|ья|я)$"
)
_RU_SUPERLATIVE = re.compile(r"(ейш|ейше)$")
_RU_DERIVATIONAL = re.compile(r"[^аеиоуыэюя]+(ост|ость)$")


def stem_ru(word: str) -> str:
    """Стемминг русского слова по Портеру + нормализация."""
    w = word.lower().replace("ё", "е")
    # Диминутивные суффиксы (сковородка -> сковород, книжка -> книж)
    if len(w) > 5 and w.endswith(("ка", "ку", "ке", "ки", "кой", "ком", "кам", "ками", "ках")):
        w = re.sub(r"к[а-я]{1,3}$", "", w)

    m = re.search(r"[аеиоуыэюя]", w)
    if not m:
        return w
    rv_pos = m.end()
    head = w[:rv_pos]
    rv = w[rv_pos:]

    # Шаг 1: Герундий / Прилагательное / Глагол / Существительное
    m1 = _RU_PERFECTIVE_GERUND.sub("", rv, count=1)
    if m1 != rv:
        rv = m1
    else:
        rv = _RU_REFLEXIVE.sub("", rv, count=1)
        m2 = _RU_ADJECTIVE.sub("", rv, count=1)
        if m2 != rv:
            rv = m2
            rv = _RU_PARTICIPLE.sub("", rv, count=1)
        else:
            m3 = _RU_VERB.sub("", rv, count=1)
            if m3 != rv:
                rv = m3
            else:
                rv = _RU_NOUN.sub("", rv, count=1)

    # Шаг 2: удаление 'и' на конце
    rv = re.sub(r"и$", "", rv)
    # Шаг 3: деривативные суффиксы
    rv = _RU_DERIVATIONAL.sub("", rv)
    # Шаг 4: удаление мягкого знака, превосходной степени, нн -> н
    rv = re.sub(r"ь$", "", rv)
    rv = _RU_SUPERLATIVE.sub("", rv)
    rv = re.sub(r"нн$", "н", rv)

    return head + rv


# ---- Английский стеммер Портера ----
def stem_en(word: str) -> str:
    w = word.lower()
    if len(w) <= 3:
        return w
    if w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("ies"):
        w = w[:-2]
    elif w.endswith(("ches", "shes", "xes", "zes")):
        w = w[:-2]
    elif w.endswith("ss"):
        pass
    elif w.endswith("s"):
        w = w[:-1]

    if w.endswith("eed"):
        if len(w) > 4:
            w = w[:-1]
    elif w.endswith("ed") and len(w) > 3:
        w = w[:-2]
    elif w.endswith("ing") and len(w) > 4:
        w = w[:-3]

    if w.endswith("ational"):
        w = w[:-7] + "ate"
    elif w.endswith("tional"):
        w = w[:-6] + "tion"
    elif w.endswith("izer"):
        w = w[:-4] + "ize"
    elif w.endswith("ly") and len(w) > 4:
        w = w[:-2]
    elif w.endswith("ful") and len(w) > 4:
        w = w[:-3]
    return w


def stem_word(word: str) -> str:
    """Универсальный стемминг слова (автоопределение RU/EN)."""
    cleaned = re.sub(r"[^\wА-Яа-яЁёa-zA-Z0-9_-]", "", word).strip().lower()
    if not cleaned:
        return ""
    if re.search(r"[а-яё]", cleaned):
        return stem_ru(cleaned)
    elif re.search(r"[a-z]", cleaned):
        return stem_en(cleaned)
    return cleaned


def tokenize_words(text: str) -> List[Tuple[str, int, int]]:
    """Разбивает текст на слова с их начальными и конечными позициями."""
    tokens: List[Tuple[str, int, int]] = []
    for m in re.finditer(r"[A-Za-zА-Яа-яЁё0-9_]+", text):
        tokens.append((m.group(0), m.start(), m.end()))
    return tokens


def get_stems_set(text: str) -> Set[str]:
    """Возвращает множество стеммов всех слов текста."""
    tokens = tokenize_words(text)
    return {stem_word(w) for w, _, _ in tokens if len(w) >= 2}


def match_stemmed_query(query: str, text: str) -> Tuple[bool, int, List[Tuple[int, int]]]:
    """
    Интеллектуальный поиск запроса в тексте:
    - Точные фразы в кавычках: "точная фраза"
    - Стемминг слов (морфология: сковородка -> сковорода/сковороду)
    - Префиксный поиск (слов*)
    """
    if not query.strip() or not text.strip():
        return False, 0, []

    q_clean = query.strip()
    text_lower = text.lower()
    spans: List[Tuple[int, int]] = []
    score = 0

    # 1. Поиск точных фраз в кавычках: "some phrase"
    exact_phrases = re.findall(r'"([^"]+)"', q_clean)
    remaining_query = re.sub(r'"[^"]+"', "", q_clean).strip()

    for phrase in exact_phrases:
        p_low = phrase.lower().strip()
        if not p_low:
            continue
        start = 0
        found_any = False
        while True:
            pos = text_lower.find(p_low, start)
            if pos < 0:
                break
            spans.append((pos, pos + len(p_low)))
            score += 10
            found_any = True
            start = pos + len(p_low)
        if not found_any:
            return False, 0, []

    # 2. Поиск отдельных термов запроса
    raw_terms = [t for t in re.split(r"\s+", remaining_query) if t.strip()]
    if not raw_terms and exact_phrases:
        return True, score, spans

    text_tokens = tokenize_words(text)
    token_stems = [(tok, start, end, stem_word(tok)) for tok, start, end in text_tokens]

    all_terms_matched = True
    for term in raw_terms:
        term_clean = term.strip().lower()
        if not term_clean:
            continue

        is_prefix = term_clean.endswith("*")
        pure_term = term_clean.rstrip("*")
        term_stem = stem_word(pure_term)

        term_matched = False
        for tok_str, start, end, tok_stem in token_stems:
            tok_low = tok_str.lower()

            if tok_low == pure_term:
                spans.append((start, end))
                score += 5
                term_matched = True
            elif is_prefix and tok_low.startswith(pure_term):
                spans.append((start, end))
                score += 3
                term_matched = True
            elif len(term_stem) >= 3 and len(tok_stem) >= 3:
                if tok_stem == term_stem or tok_stem.startswith(term_stem) or term_stem.startswith(tok_stem):
                    spans.append((start, end))
                    score += 4
                    term_matched = True

        if not term_matched:
            all_terms_matched = False

    merged_spans: List[Tuple[int, int]] = []
    if spans:
        spans.sort(key=lambda s: s[0])
        cur_start, cur_end = spans[0]
        for s, e in spans[1:]:
            if s <= cur_end:
                cur_end = max(cur_end, e)
            else:
                merged_spans.append((cur_start, cur_end))
                cur_start, cur_end = s, e
        merged_spans.append((cur_start, cur_end))

    matched = all_terms_matched and (len(merged_spans) > 0 or len(exact_phrases) > 0)
    return matched, score, merged_spans
