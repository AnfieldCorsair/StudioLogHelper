import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studiologhelper.indexer.memory_search import fast_search_chats, regex_search_chats
from studiologhelper.core.models import ChatLog, Message


def make_chat(title, texts):
    chat = ChatLog(title=title, path=f"/tmp/{title}.json", model="test-model")
    chat.messages = [Message(role="user" if i % 2 == 0 else "model", text=t) for i, t in enumerate(texts)]
    return chat


def test_memory_search_basic():
    chats = [
        make_chat("chat1", ["hello world", "this is about сковородка", "another"]),
        make_chat("chat2", ["nothing", "frying pan сковородка again"]),
    ]
    hits = fast_search_chats(chats, "сковородка", scope="all", max_workers=1)
    assert len(hits) == 2
    assert all("сковородка" in h.snippet.lower() or "сковородка" in chats[0].messages[1].text.lower() for h in hits)


def test_memory_search_scope():
    chats = [make_chat("c", ["user message about apple", "model answer about apple"])]
    hits_user = fast_search_chats(chats, "apple", scope="user", max_workers=1)
    assert len(hits_user) == 1
    assert hits_user[0].role == "user"

    hits_model = fast_search_chats(chats, "apple", scope="model", max_workers=1)
    assert len(hits_model) == 1
    assert hits_model[0].role == "model"


def test_memory_search_parallel():
    chats = [make_chat(f"chat{i}", [f"message {i} contains keyword"]) for i in range(20)]
    hits = fast_search_chats(chats, "keyword", scope="all", max_workers=4, limit=10)
    assert len(hits) == 10


def test_regex_search():
    chats = [make_chat("c", ["hello 123 world", "test 456"])]
    hits = regex_search_chats(chats, r"\d{3}", scope="all")
    assert len(hits) == 2
