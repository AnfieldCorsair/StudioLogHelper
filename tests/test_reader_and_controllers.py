# -*- coding: utf-8 -*-
"""Unit tests for reader mode, stemming, hybrid search, hierarchical categories, and bookmarks."""

from pathlib import Path
from studiologhelper.core.models import ChatLog, Message
from studiologhelper.core.project import (
    Project,
    ProjectBookmark,
    ProjectFile,
    matches_hierarchical_category,
)
from studiologhelper.i18n.translator import Translator
from studiologhelper.indexer.stemmer import match_stemmed_query, stem_ru, stem_en, stem_word
from studiologhelper.indexer.hybrid_search import (
    HybridSearchEngine,
    compute_subword_vector,
    cosine_similarity,
)
from studiologhelper.ui.controllers.project_controller import ProjectController
from studiologhelper.ui.controllers.file_list_controller import FileListController
from studiologhelper.ui.services.copy_service import CopyService


class MockSettings:
    """Mock for QSettings to test controllers without GUI dependencies."""
    def __init__(self):
        self._data = {}

    def value(self, key, default=None):
        return self._data.get(key, default)

    def setValue(self, key, val):
        self._data[key] = val


def test_russian_and_english_stemmer():
    assert stem_ru("сковорода") == "сковород"
    assert stem_ru("сковороду") == "сковород"
    assert stem_ru("сковородой") == "сковород"
    assert stem_ru("сковородка") == "сковород"
    assert stem_ru("сковородку") == "сковород"

    assert stem_en("running") == "runn"
    assert stem_en("developers") == "developer"
    assert stem_en("searches") == "search"


def test_stemmed_query_matching():
    text = "Сегодня мы купили новую чугунную сковороду для жарки мяса."
    matched, score, spans = match_stemmed_query("сковородка", text)
    assert matched is True
    assert score > 0
    assert len(spans) == 1
    start, end = spans[0]
    assert text[start:end] == "сковороду"

    text2 = "Искусственный интеллект меняет разработку программного обеспечения."
    matched2, _, _ = match_stemmed_query('"искусственный интеллект"', text2)
    assert matched2 is True

    matched3, _, _ = match_stemmed_query("пылесос", text2)
    assert matched3 is False


def test_hybrid_search_engine():
    engine = HybridSearchEngine()
    chat = ChatLog(
        title="Python Discussion",
        model="gpt-4",
        path="/tmp/python.json",
        messages=[
            Message(role="user", text="Как жарить на сковороде без прилипания?"),
            Message(role="model", text="Нагрейте чугунную сковородку и добавьте немного масла."),
            Message(role="user", text="Что такое квантовая запутанность?"),
            Message(role="model", text="Квантовая запутанность — физическое явление в квантовой механике."),
        ],
    )

    # Search word variation "сковородка"
    hits = engine.search_chats([chat], "сковородка")
    assert len(hits) >= 1
    assert hits[0].msg_num in (1, 2)
    assert hits[0].score > 0

    # Search subword / fuzzy
    hits_quantum = engine.search_chats([chat], "квантовый")
    assert len(hits_quantum) >= 1
    assert hits_quantum[0].msg_num == 4


def test_hierarchical_categories_matching():
    assert matches_hierarchical_category("Work/Research/Gemini", "Work") is True
    assert matches_hierarchical_category("Work/Research/Gemini", "Work/Research") is True
    assert matches_hierarchical_category("Work/Research/Gemini", "Work/Research/Gemini") is True
    assert matches_hierarchical_category("Work/ProjectA", "Work/Research") is False
    assert matches_hierarchical_category("Personal/Notes", "Work") is False
    assert matches_hierarchical_category("", "__none__") is True
    assert matches_hierarchical_category("Work", "__none__") is False


def test_project_highlights_and_autosave(tmp_path):
    proj_path = tmp_path / "test_proj.slh.json"
    bm = ProjectBookmark(
        block_num=2,
        role="model",
        title="Chat Title",
        note="Key insight",
        quote="чугунную сковородку",
        color="yellow",
    )
    pf = ProjectFile(
        path="/path/to/chat.json",
        title="Chat Title",
        model="gemini-1.5-pro",
        bookmarks=[bm],
    )
    proj = Project(name="TestProj", files=[pf])
    proj.save(proj_path)

    loaded = Project.load(proj_path)
    assert len(loaded.files) == 1
    assert len(loaded.files[0].bookmarks) == 1
    assert loaded.files[0].bookmarks[0].quote == "чугунную сковородку"
    assert loaded.files[0].bookmarks[0].color == "yellow"


def test_controllers_and_services(tmp_path):
    settings = MockSettings()
    proj_ctrl = ProjectController(settings)
    file_ctrl = FileListController(proj_ctrl)

    # Categories with hierarchy
    proj_ctrl.create_category("Work/AI/Gemini")
    assert "Work" in proj_ctrl.categories
    assert "Work/AI" in proj_ctrl.categories
    assert "Work/AI/Gemini" in proj_ctrl.categories

    # Add chats
    chat1 = ChatLog(
        title="Chat 1",
        model="gpt-4",
        path="/tmp/chat1.json",
        messages=[
            Message(role="user", text="Hello"),
            Message(role="model", text="Hi there!"),
        ],
    )
    chat2 = ChatLog(
        title="Chat 2",
        model="claude-3",
        path="/tmp/chat2.json",
        messages=[
            Message(role="user", text="Code review"),
            Message(role="model", text="Here is feedback."),
        ],
    )
    file_ctrl.add_chats([chat1, chat2])
    assert len(file_ctrl.chats) == 2

    # Tags, notes, and highlights
    proj_ctrl.set_tags(chat1.path, ["python", "ai"])
    assert proj_ctrl.get_tags(chat1.path) == ["python", "ai"]

    proj_ctrl.add_highlight(chat1.path, block_num=1, quote="Hello", color="green", note="Greeting quote")
    bms = proj_ctrl.get_bookmarks(chat1.path)
    assert len(bms) == 1
    assert bms[0]["quote"] == "Hello"
    assert bms[0]["color"] == "green"

    # Hierarchical filter test
    proj_ctrl.assign_category(chat1.path, "Work/AI/Gemini")
    file_ctrl.set_filters(category="Work")
    filtered = file_ctrl.get_filtered_chats()
    assert len(filtered) == 1
    assert filtered[0].title == "Chat 1"
