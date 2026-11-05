# -*- coding: utf-8 -*-
"""Бенчмарк горячих путей StudioLogHelper: стеммер, поиск, парсеры, markdown.

Запуск: python bench/bench.py [метка]
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studiologhelper.indexer.stemmer import stem_word, match_stemmed_query, tokenize_words
from studiologhelper.indexer.memory_search import fast_search_chats, regex_search_chats
from studiologhelper.indexer.hybrid_search import HybridSearchEngine
from studiologhelper.core.parsers.text_parser import parse_text_log
from studiologhelper.core.parsers.detector import _looks_like_text_log_head
from studiologhelper.core.markdown import markdown_to_html_builtin
from studiologhelper.core.models import ChatLog, Message

LABEL = sys.argv[1] if len(sys.argv) > 1 else "run"


def bench(name, fn, n=3):
    best = float("inf")
    for _ in range(n):
        t0 = time.perf_counter()
        result = fn()
        dt = time.perf_counter() - t0
        best = min(best, dt)
    print(f"[{LABEL}] {name:42s} {best*1000:9.2f} ms   (result={str(result)[:40]})")
    return best


# --- Корпус: 30 чатов x 40 сообщений ---
WORDS = ("сковородка книга рефакторинг производительность python qt поиск индекс "
         "оптимизация память поток файл лог чат модель ответ пользователь запрос "
         "algorithm memory search index chat log model performance refactor code").split()

def make_corpus():
    import random
    random.seed(42)
    chats = []
    for c in range(30):
        msgs = []
        for m in range(40):
            text = " ".join(random.choices(WORDS, k=120))
            role = "user" if m % 2 == 0 else "model"
            th = [" ".join(random.choices(WORDS, k=40))] if role == "model" else []
            msgs.append(Message(role=role, text=text, thoughts=th))
        chats.append(ChatLog(path=f"/tmp/chat{c}.json", title=f"chat{c}", model="gemini", messages=msgs))
    return chats

CORPUS = make_corpus()

# --- Текстовый лог ~1.5MB ---
def make_text_log():
    lines = []
    for i in range(2500):
        lines.append(f"--- #{i+1} {'USER' if i % 2 == 0 else 'MODEL'} ---")
        lines.append(" ".join(WORDS) * 3)
        lines.append("")
    return "\n".join(lines)

TEXT_LOG = make_text_log()

# --- Markdown-текст ---
MD_TEXT = ("\n\n".join(f"## Раздел {i}\n\n**Жирный** текст с `кодом` и [ссылкой](https://example.com/{i}).\n\n"
                      f"- пункт один\n- пункт два\n\n```python\nprint({i})\n```" for i in range(80)))

HEAD_SAMPLE = "Arena Side-by-Side Chat\nUser:\nhello\nRight AI:\nworld\n" * 40


def b_stemmer():
    total = 0
    for w in WORDS * 300:
        total += len(stem_word(w))
    return total

def b_tokenize_stem():
    text = CORPUS[0].messages[0].text * 5
    return sum(len(stem_word(t)) for t, _, _ in tokenize_words(text))

def b_match_stemmed():
    n = 0
    for chat in CORPUS[:10]:
        for msg in chat.messages[:10]:
            ok, _, _ = match_stemmed_query("сковородка оптимизация*", msg.text)
            n += ok
    return n

def b_memory_search():
    return len(fast_search_chats(CORPUS, "сковородка оптимизация"))

def b_regex_search():
    return len(regex_search_chats(CORPUS, r"сковород\w+"))

def b_hybrid_search():
    eng = HybridSearchEngine()
    return len(eng.search_chats(CORPUS, "производительность python"))

def b_text_parser():
    return len(parse_text_log(TEXT_LOG, "/tmp/big.log").messages)

def b_detector_head():
    n = 0
    for _ in range(200):
        n += _looks_like_text_log_head(HEAD_SAMPLE)
    return n

def b_markdown():
    return len(markdown_to_html_builtin(MD_TEXT))


if __name__ == "__main__":
    print(f"corpus: {len(CORPUS)} chats, text log: {len(TEXT_LOG)//1024} KB")
    bench("stem_word x9000", b_stemmer)
    bench("tokenize+stem (1 msg x5)", b_tokenize_stem)
    bench("match_stemmed_query (100 msgs)", b_match_stemmed)
    bench("fast_search_chats (30 chats)", b_memory_search)
    bench("regex_search_chats (30 chats)", b_regex_search)
    bench("hybrid_search (30 chats)", b_hybrid_search)
    bench("parse_text_log (2500 blocks)", b_text_parser)
    bench("detector head x200", b_detector_head)
    bench("markdown_to_html_builtin (80 sect)", b_markdown)
