# -*- coding: utf-8 -*-
"""conftest.py — общий QApplication для GUI-тестов (headless/CI).

Без QApplication создание QWidget падает (RuntimeError/Abort), поэтому некоторые
тесты раньше gracefully пропускались. С conftest они реально выполняются и в CI.
"""

import os

# Должно быть до первого импорта Qt
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session", autouse=True)
def qapp_session():
    """Единый QApplication на всю сессию тестов (если PyQt6 доступен)."""
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        yield None
        return

    app = QApplication.instance()
    if app is None:
        app = QApplication(["studiologhelper-tests"])
    yield app
