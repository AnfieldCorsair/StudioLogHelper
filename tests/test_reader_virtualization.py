# -*- coding: utf-8 -*-
"""Тесты виртуализации «Книги»: окно блоков, догрузка, переходы.

Часть тестов (чистая функция _window_bounds) работает без Qt.
Qt-часть выполняется при доступном PyQt6 (conftest.py создаёт QApplication),
иначе мягко пропускается.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studiologhelper.ui.widgets.reader_view import _window_bounds


# ---- Чистая функция окна (без Qt) ----

def test_window_bounds_covers_all_when_small():
    assert _window_bounds(5, 0, 40) == (0, 5)


def test_window_bounds_centered():
    start, end = _window_bounds(100, 50, 20)
    assert end - start == 20
    assert start <= 50 < end
    assert 40 <= start <= 45  # примерно по центру


def test_window_bounds_clamps_edges():
    assert _window_bounds(100, 0, 20) == (0, 20)
    start, end = _window_bounds(100, 99, 20)
    assert end == 100 and start == 80


def test_window_bounds_degenerate():
    assert _window_bounds(0, 3, 10) == (0, 0)
    start, end = _window_bounds(3, 999, 0)  # size < 1 -> min 1
    assert end - start >= 1


# ---- Qt-часть (нужен QApplication из conftest) ----

class MockSettings:
    def __init__(self):
        self._data = {}

    def value(self, key, default=None):
        return self._data.get(key, default)

    def setValue(self, key, val):
        self._data[key] = val


def _make_reader(n_messages=60):
    try:
        from PyQt6.QtWidgets import QApplication
        from studiologhelper.ui.widgets.reader_view import ReaderView
        from studiologhelper.ui.controllers.project_controller import ProjectController
    except Exception:
        pytest.skip("PyQt6 недоступен — Qt-часть пропущена")
    if QApplication.instance() is None:
        pytest.skip("QApplication недоступен — Qt-часть пропущена")

    from studiologhelper.core.models import ChatLog, Message

    settings = MockSettings()
    settings.setValue("reader/window_init", 10)
    settings.setValue("reader/window_grow", 5)
    proj_ctrl = ProjectController(settings)
    reader = ReaderView(settings, proj_ctrl, lambda k, **kw: k)

    msgs = [Message(role="user" if i % 2 == 0 else "model", text=f"сообщение номер {i} " + "текст " * 20) for i in range(1, n_messages + 1)]
    chat = ChatLog(path="/tmp/virt.json", title="virt", model="m", messages=msgs)
    reader.set_chat(chat)
    return reader


def test_book_windowed_render():
    reader = _make_reader(60)
    html = reader.browser.toHtml()
    # окно 10 блоков: первые блоки отрендерены, дальние — нет
    assert "block_1" in html
    assert "block_10" in html
    assert "block_45" not in html
    # есть ссылка догрузки вниз
    assert "more_down" in html


def test_book_grow_window_down():
    reader = _make_reader(60)
    reader._grow_window(down=True)
    html = reader.browser.toHtml()
    assert "block_15" in html  # окно расширилось
    assert "block_45" not in html  # но не всё


def test_book_jump_Recenters_window():
    reader = _make_reader(60)
    reader.jump_to_block(50)
    html = reader.browser.toHtml()
    assert "block_50" in html     # целевой блок в окне
    assert "more_up" in html      # выше есть ещё блоки


def test_book_small_chat_renders_fully():
    reader = _make_reader(5)
    html = reader.browser.toHtml()
    assert "block_5" in html
    assert "more_down" not in html
    assert "more_up" not in html
