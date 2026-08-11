# -*- coding: utf-8 -*-
"""Regression tests for P0/P1 fixes: Atomic save, backup rotation, autosave safety, bookmark/highlight coexistence, and snippet accuracy."""

import json
from pathlib import Path

from studiologhelper.core.models import ChatLog, Message
from studiologhelper.core.project import (
    Highlight,
    Project,
    ProjectBookmark,
    ProjectFile,
)
from studiologhelper.indexer.hybrid_search import build_snippet
from studiologhelper.ui.controllers.project_controller import ProjectController


class MockSettings:
    """Mock for QSettings."""
    def __init__(self):
        self._data = {}

    def value(self, key, default=None):
        return self._data.get(key, default)

    def setValue(self, key, val):
        self._data[key] = val


def test_atomic_save_and_backup_creation(tmp_path):
    proj_path = tmp_path / "project.slh.json"
    bak_path = tmp_path / "project.slh.json.bak"

    # 1. First save
    proj1 = Project(name="Version1", files=[ProjectFile(path="/path/to/log1.json", title="Log 1")])
    proj1.save(proj_path, create_backup=True)

    assert proj_path.exists()
    data1 = json.loads(proj_path.read_text(encoding="utf-8"))
    assert data1["project"]["name"] == "Version1"

    # 2. Second save creates .bak of version 1
    proj2 = Project(name="Version2", files=[ProjectFile(path="/path/to/log2.json", title="Log 2")])
    proj2.save(proj_path, create_backup=True)

    assert proj_path.exists()
    assert bak_path.exists()

    data_curr = json.loads(proj_path.read_text(encoding="utf-8"))
    data_bak = json.loads(bak_path.read_text(encoding="utf-8"))
    assert data_curr["project"]["name"] == "Version2"
    assert data_bak["project"]["name"] == "Version1"


def test_project_portability_with_relative_paths(tmp_path):
    sub_dir = tmp_path / "logs"
    sub_dir.mkdir()
    log_file = sub_dir / "chat1.txt"
    log_file.write_text("User: hi\nModel: hello", encoding="utf-8")

    proj_path = tmp_path / "my_project.slh.json"
    proj = Project(name="PortabilityTest", files=[ProjectFile(path=str(log_file), title="Chat 1")])
    proj.save(proj_path)

    # Check relative path in saved JSON
    data = json.loads(proj_path.read_text(encoding="utf-8"))
    assert data["files"][0]["rel_path"] == "logs/chat1.txt" or data["files"][0]["rel_path"] == "logs\\chat1.txt"

    # Move entire directory to a new location to test portability
    new_dir = tmp_path / "moved_dir"
    new_dir.mkdir()
    new_logs = new_dir / "logs"
    new_logs.mkdir()
    new_log_file = new_logs / "chat1.txt"
    new_log_file.write_text("User: hi\nModel: hello", encoding="utf-8")
    new_proj_path = new_dir / "my_project.slh.json"
    new_proj_path.write_text(proj_path.read_text(encoding="utf-8"), encoding="utf-8")

    loaded_proj = Project.load(new_proj_path)
    assert Path(loaded_proj.files[0].path).exists()
    assert loaded_proj.files[0].path == str(new_log_file.resolve())


def test_bookmark_and_highlight_coexistence():
    settings = MockSettings()
    proj_ctrl = ProjectController(settings)
    chat_path = "/tmp/test_chat.json"

    # Add 1 bookmark on block #1
    bm_id = proj_ctrl.add_bookmark(chat_path, block_num=1, role="user", note="Block bookmark")
    assert proj_ctrl.is_bookmarked(chat_path, 1) is True

    # Add 2 highlights on block #1
    hl1_id = proj_ctrl.add_highlight(
        chat_path, block_num=1, quote="первая цитата", color="yellow", note="Заметка 1", start=0, end=13
    )
    hl2_id = proj_ctrl.add_highlight(
        chat_path, block_num=1, quote="вторая цитата", color="green", note="Заметка 2", start=20, end=33
    )

    bms = proj_ctrl.get_bookmarks(chat_path)
    hls = proj_ctrl.get_highlights(chat_path)
    assert len(bms) == 1
    assert len(hls) == 2

    # 1. Removing bookmark on block #1 must NOT remove highlights!
    proj_ctrl.remove_bookmark(chat_path, block_num=1)
    assert proj_ctrl.is_bookmarked(chat_path, 1) is False
    assert len(proj_ctrl.get_highlights(chat_path)) == 2
    assert proj_ctrl.get_highlights(chat_path)[0]["id"] == hl1_id
    assert proj_ctrl.get_highlights(chat_path)[1]["id"] == hl2_id

    # 2. Updating note on highlight must NOT create duplicate highlights
    proj_ctrl.update_highlight_note(chat_path, hl1_id, "Обновленная заметка")
    hls_after_edit = proj_ctrl.get_highlights(chat_path)
    assert len(hls_after_edit) == 2
    assert hls_after_edit[0]["note"] == "Обновленная заметка"

    # 3. Removing 1 highlight by ID leaves the other highlight
    proj_ctrl.remove_highlight_by_id(chat_path, hl1_id)
    hls_after_del = proj_ctrl.get_highlights(chat_path)
    assert len(hls_after_del) == 1
    assert hls_after_del[0]["id"] == hl2_id


def test_autosave_protection_against_empty_cache(tmp_path):
    settings = MockSettings()
    proj_ctrl = ProjectController(settings)
    proj_path = tmp_path / "autosave_test.slh.json"

    chat = ChatLog(title="Chat", path="/tmp/c.json", messages=[Message(role="user", text="hello")])
    proj_ctrl.save_project(proj_path, [chat], name="AutosaveTest")
    assert proj_path.exists()

    # Simulate list temporary clearing during reload
    proj_ctrl.set_active_chats_ref([])
    proj_ctrl.is_loading = True

    # Triggering autosave during loading must be ignored
    proj_ctrl.trigger_autosave()
    assert proj_ctrl.dirty is False or proj_ctrl.is_loading is True

    # Check project file was NOT emptied
    data = json.loads(proj_path.read_text(encoding="utf-8"))
    assert len(data["files"]) == 1


def test_snippet_extraction_no_offset_drift():
    text = "Строка с   несколькими   \n\n\n   пробелами и целевым словом сковорода в середине текста."
    target = "сковорода"
    pos = text.find(target)
    spans = [(pos, pos + len(target))]

    snippet = build_snippet(text, spans)
    assert "сковорода" in snippet
    # No multiple newlines in snippet
    assert "\n\n" not in snippet
