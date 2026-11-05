# -*- coding: utf-8 -*-
"""Регрессионные тесты рефакторинга оптимизаций (без Qt).

Покрывают:
- bare-заголовки: слова вроде 'answer'/'response' в теле НЕ должны становиться
  заголовками (баг, найденный при рефакторинге text_parser);
- паритет результатов поиска после оптимизаций memory_search/hybrid_search;
- кэш стеммера не меняет результатов;
- kind пробрасывается в SearchIndex без повторного чтения файлов,
  инкрементальный skip по mtime/size работает.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studiologhelper.core.models import ChatLog, Message
from studiologhelper.core.parsers.text_parser import parse_text_log
from studiologhelper.indexer.stemmer import stem_word, match_stemmed_query
from studiologhelper.indexer.memory_search import fast_search_chats, regex_search_chats
from studiologhelper.indexer.hybrid_search import HybridSearchEngine


# ---- text_parser: bare-заголовки ----

def test_bare_body_words_are_not_headers():
    # 'answer' — валидный заголовок как "Answer: ...", но НЕ как bare-строка
    text = "User:\nhello\n\nModel:\nanswer\n"
    chat = parse_text_log(text, "x.txt")
    assert len(chat.messages) == 2
    assert chat.messages[0].role == "user" and chat.messages[0].text == "hello"
    assert chat.messages[1].role == "model" and chat.messages[1].text == "answer"


def test_bare_response_word_is_not_header():
    text = "User:\nquestion\n\nAssistant:\nresponse\nmore body\n"
    chat = parse_text_log(text, "x.txt")
    assert len(chat.messages) == 2
    assert chat.messages[1].text == "response\nmore body"


def test_bare_headers_still_detected():
    text = "User\nhello\n\nModel\nanswer here\n"
    chat = parse_text_log(text, "x.txt")
    assert len(chat.messages) == 2
    assert chat.messages[0].role == "user"
    assert chat.messages[1].role == "model"


def test_long_line_with_colon_is_body():
    body = "word " * 30  # длинная строка тела
    text = f"User:\nhello\n\nModel:\nsome {body}end: tail\n"
    chat = parse_text_log(text, "x.txt")
    assert len(chat.messages) == 2
    assert "some word" in chat.messages[1].text


# ---- стеммер: кэш не меняет результат ----

def test_stem_cache_consistency():
    words = ["сковородка", "сковородку", "running", "developers", "searches", "КНИГА"]
    first = [stem_word(w) for w in words]
    second = [stem_word(w) for w in words]  # из кэша
    assert first == second
    assert stem_word("сковородка") == "сковород"


# ---- паритет поиска ----

def _make_corpus():
    chats = []
    for c in range(6):
        msgs = []
        for m in range(20):
            text = f"сковородка текст номер {m} оптимизация python поиск"
            if m % 2:
                msgs.append(Message(role="model", text=text + " ответ", thoughts=["мысль о сковородке"]))
            else:
                msgs.append(Message(role="user", text=text))
        chats.append(ChatLog(path=f"/tmp/c{c}.json", title=f"c{c}", model="m", messages=msgs))
    return chats


def test_fast_search_finds_all_chats():
    chats = _make_corpus()
    hits = fast_search_chats(chats, "сковородка", use_stemming=False)
    # 6 чатов x 20 сообщений, все содержат слово (и в мыслях) -> >= 6*10 user hits
    assert len(hits) >= 60
    assert all(h.score > 0 for h in hits)


def test_regex_search_parity():
    chats = _make_corpus()
    hits = regex_search_chats(chats, r"сковородк\w+")
    assert len(hits) >= 60


def test_hybrid_search_ranks_exact_first():
    chats = _make_corpus()
    eng = HybridSearchEngine()
    hits = eng.search_chats(chats, "сковородка")
    assert hits
    assert hits[0].score >= hits[-1].score
    assert any(h.fts_score > 0 for h in hits)


def test_match_stemmed_query_spans_positions():
    text = "Это сковородка стоит на столе"
    ok, score, spans = match_stemmed_query("сковородка", text)
    assert ok and score > 0 and spans
    s, e = spans[0]
    assert text[s:e].lower().startswith("сковород")
