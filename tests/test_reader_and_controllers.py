# -*- coding: utf-8 -*-
"""Unit tests for reader mode, stemming search, controllers, and services."""

import json
from pathlib import Path
from PyQt6.QtCore import QSettings

from studiologhelper.core.models import ChatLog, Message
from studiologhelper.core.project import Project, ProjectBookmark, ProjectFile
from studiologhelper.i18n.translator import Translator
from studiologhelper.indexer.stemmer import match_stemmed_query, stem_ru, stem_en, stem_word
from studiologhelper.ui.controllers.project_controller import ProjectController
from studiologhelper.ui.controllers.file_list_controller import FileListController
from studiologhelper.ui.services.copy_service import CopyService


def test_russian_and_english_stemmer():
    # Russian morphology
    assert stem_ru("сковорода") == "сковород"
    assert stem_ru("сковороду") == "сковород"
    assert stem_ru("сковородой") == "сковород"
    assert stem_ru("сковородка") == "сковород"
    assert stem_ru("сковородку") == "сковород"

    # English morphology
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

    # Phrase match
    text2 = "Искусственный интеллект меняет разработку программного обеспечения."
    matched2, _, _ = match_stemmed_query('"искусственный интеллект"', text2)
    assert matched2 is True

    # No match
    matched3, _, _ = match_stemmed_query("пылесос", text2)
    assert matched3 is False


def test_project_bookmarks_persistence(tmp_path):
    proj_path = tmp_path / "test_proj.slh.json"
    bm = ProjectBookmark(
        block_num=2,
        role="model",
        title="Chat Title",
        note="Key algorithm explanation",
        snippet="def quicksort(): ...",
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
    assert loaded.files[0].bookmarks[0].block_num == 2
    assert loaded.files[0].bookmarks[0].note == "Key algorithm explanation"


def test_controllers_and_services(tmp_path):
    settings = QSettings(str(tmp_path / "test_settings.ini"), QSettings.Format.IniFormat)
    proj_ctrl = ProjectController(settings)
    file_ctrl = FileListController(proj_ctrl)

    # Categories
    proj_ctrl.create_category("Work")
    assert "Work" in proj_ctrl.categories

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

    # Tags and notes
    proj_ctrl.set_tags(chat1.path, ["python", "ai"])
    assert proj_ctrl.get_tags(chat1.path) == ["python", "ai"]

    proj_ctrl.set_note(chat1.path, "Important chat")
    assert proj_ctrl.get_note(chat1.path) == "Important chat"

    # Bookmarks
    proj_ctrl.add_bookmark(chat1.path, block_num=1, role="user", note="First prompt")
    assert proj_ctrl.is_bookmarked(chat1.path, 1) is True
    assert proj_ctrl.is_bookmarked(chat1.path, 2) is False

    # Filters
    file_ctrl.set_filters(tag="python")
    filtered = file_ctrl.get_filtered_chats()
    assert len(filtered) == 1
    assert filtered[0].title == "Chat 1"

    # Copy service
    trans = Translator()
    copy_text = CopyService.clean_copy_text(chat1, which=1, settings=settings)  # prompts only
    assert "Hello" in copy_text
    assert "Hi there!" not in copy_text
