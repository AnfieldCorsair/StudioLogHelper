# -*- coding: utf-8 -*-
"""Тесты режимов интерфейса: простой / расширенный (Qt, headless)."""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _make_main_window(pre_mode: str = "simple"):
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QSettings
        from studiologhelper.ui.main_window import MainWindow, ORG, APP_NAME
    except Exception:
        pytest.skip("PyQt6 недоступен — Qt-часть пропущена")
    if QApplication.instance() is None:
        pytest.skip("QApplication недоступен — Qt-часть пропущена")
    # Детерминированное состояние до создания окна (QSettings персистентен)
    QSettings(ORG, APP_NAME).setValue("ui/mode", pre_mode)
    win = MainWindow()
    win.show()  # без show() дочерние виджеты report isVisible()==False
    QApplication.processEvents()
    return win


def test_default_mode_is_simple():
    win = _make_main_window("simple")
    try:
        assert win.ui_mode == "simple"
        # В простом режиме скрыты перегружающие контролы
        assert not win.btn_org.isVisible()
        assert not win.btn_export_all.isVisible()
        assert not win.chk_virtual.isVisible()
        # Видимы только «Книга» и «Поиск»
        assert win.tabs.isTabVisible(2)
        assert win.tabs.isTabVisible(4)
        assert not win.tabs.isTabVisible(0)
        assert not win.tabs.isTabVisible(1)
        assert not win.tabs.isTabVisible(3)
        # В «Книге» скрыта типографика
        assert not win.reader_view.cmb_font.isVisible()
    finally:
        win.close()
        win.deleteLater()


def test_switch_to_advanced_shows_all():
    win = _make_main_window("simple")
    try:
        win.cmb_ui_mode.setCurrentIndex(1)  # Расширенный
        assert win.ui_mode == "advanced"
        assert win.btn_org.isVisible()
        assert win.chk_virtual.isVisible()
        assert win.tabs.isTabVisible(0)
        assert win.tabs.isTabVisible(1)
        assert win.tabs.isTabVisible(3)
        assert win.reader_view.cmb_font.isVisible()
        # переключение обратно
        win.cmb_ui_mode.setCurrentIndex(0)
        assert win.ui_mode == "simple"
        assert not win.btn_org.isVisible()
    finally:
        win.close()
        win.deleteLater()


def test_mode_persisted_in_settings():
    win = _make_main_window("simple")
    try:
        win.cmb_ui_mode.setCurrentIndex(1)
        assert win.settings.value("ui/mode") == "advanced"
        win.cmb_ui_mode.setCurrentIndex(0)
        assert win.settings.value("ui/mode") == "simple"
    finally:
        win.close()
        win.deleteLater()


def test_switch_tab_respects_hidden():
    win = _make_main_window("simple")
    try:
        win._switch_tab(0)  # скрыта в простом режиме — не переключается
        assert win.tabs.currentIndex() != 0 or win.tabs.isTabVisible(0)
        win._switch_tab(2)
        assert win.tabs.currentIndex() == 2
    finally:
        win.close()
        win.deleteLater()
