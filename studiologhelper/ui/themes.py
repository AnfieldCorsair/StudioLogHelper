# -*- coding: utf-8 -*-
"""Темы + кэшированный QSS"""

from __future__ import annotations

from functools import lru_cache

from PyQt6.QtGui import QPalette, QColor

THEMES = {
    "dark": {
        "bg": "#18191a", "panel": "#202122", "card": "#242526",
        "card_user": "#1f2b3e", "text": "#e4e6eb", "muted": "#9a9da3",
        "border": "#3e4042", "accent": "#8ab4f8", "user": "#8ab4f8",
        "model": "#81c995", "thought": "#fdd663", "thought_bg": "#332b14",
        "code_bg": "#1b1c1d", "btn": "#3a3b3c", "btn_text": "#e4e6eb",
        "sel": "#2d4368", "accent_text": "#0b1325",
    },
    "light": {
        "bg": "#f4f5f7", "panel": "#eceef1", "card": "#ffffff",
        "card_user": "#e8f0fe", "text": "#1c1e21", "muted": "#65676b",
        "border": "#d8dadf", "accent": "#1a73e8", "user": "#1a73e8",
        "model": "#188038", "thought": "#b06000", "thought_bg": "#fef7e0",
        "code_bg": "#f0f2f5", "btn": "#e4e6eb", "btn_text": "#1c1e21",
        "sel": "#cfe0fc", "accent_text": "#ffffff",
    },
}


@lru_cache(maxsize=32)
def build_stylesheet_cached(theme_name: str, scale: float) -> str:
    t = THEMES.get(theme_name, THEMES["dark"])
    return _build_stylesheet(t, scale)


def _build_stylesheet(t: dict, scale: float = 1.0) -> str:
    def fs(px: float) -> str:
        return f"{px * scale:.1f}px"

    return f"""
    QMainWindow, QDialog {{ background: {t['bg']}; }}
    QWidget {{ color: {t['text']}; font-size: {fs(13)}; }}
    QSplitter::handle {{ background: {t['border']}; width: 2px; }}
    QListWidget {{
        background: {t['panel']}; border: 1px solid {t['border']};
        border-radius: 8px; padding: 4px; outline: none;
    }}
    QListWidget::item {{ padding: 7px 8px; border-radius: 6px; }}
    QListWidget::item:selected {{ background: {t['sel']}; color: {t['text']}; }}
    QListWidget::item:hover {{ background: {t['btn']}; }}
    QPushButton, QToolButton {{
        background: {t['btn']}; color: {t['btn_text']};
        border: 1px solid {t['border']}; border-radius: 7px;
        padding: 5px 12px; font-weight: 600;
    }}
    QPushButton:hover, QToolButton:hover {{ border-color: {t['accent']}; }}
    QPushButton:disabled, QToolButton:disabled {{ color: {t['muted']}; }}
    QToolButton::menu-indicator {{ image: none; width: 0; }}
    QPushButton#accent {{
        background: {t['accent']}; border: none; color: {t['accent_text']};
    }}
    QPlainTextEdit, QTextEdit {{
        background: {t['code_bg']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 8px;
        font-family: Consolas, "Courier New", monospace;
        font-size: {fs(12.5)};
        selection-background-color: {t['sel']};
    }}
    QTabWidget::pane {{ border: 1px solid {t['border']}; border-radius: 8px; }}
    QTabBar::tab {{
        background: {t['panel']}; color: {t['muted']};
        padding: 6px 16px; border: 1px solid {t['border']};
        border-bottom: none; border-top-left-radius: 7px;
        border-top-right-radius: 7px; margin-right: 2px; font-weight: 600;
    }}
    QTabBar::tab:selected {{ background: {t['card']}; color: {t['text']}; }}
    QScrollArea {{ border: 1px solid {t['border']}; border-radius: 8px;
        background: {t['bg']}; }}
    QScrollArea > QWidget > QWidget#scrollHost {{ background: {t['bg']}; }}
    QScrollArea QWidget#scrollHost QLabel {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 12px; }}
    QScrollBar::handle:vertical {{ background: {t['border']};
        border-radius: 5px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; }}
    QScrollBar::handle:horizontal {{ background: {t['border']};
        border-radius: 5px; min-width: 30px; }}
    QComboBox, QLineEdit {{
        background: {t['panel']}; border: 1px solid {t['border']};
        border-radius: 6px; padding: 4px 8px;
    }}
    QComboBox QAbstractItemView {{
        background: {t['panel']}; border: 1px solid {t['border']};
        selection-background-color: {t['sel']};
    }}
    QGroupBox {{
        border: 1px solid {t['border']}; border-radius: 8px;
        margin-top: 12px; padding-top: 8px; font-weight: 700;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
    QCheckBox {{ spacing: 7px; }}
    QStatusBar {{ background: {t['panel']}; color: {t['muted']};
        border-top: 1px solid {t['border']}; }}
    QMenu {{ background: {t['panel']}; border: 1px solid {t['border']};
        border-radius: 8px; padding: 4px; }}
    QMenu::item {{ padding: 6px 22px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {t['sel']}; }}
    QLabel#muted {{ color: {t['muted']}; }}
    QFrame#msgCard {{ background: {t['card']};
        border: 1px solid {t['border']}; border-radius: 10px; }}
    QFrame#msgCardUser {{ background: {t['card_user']};
        border: 1px solid {t['border']}; border-radius: 10px; }}
    QFrame#msgCard QLabel, QFrame#msgCardUser QLabel {{
        background: transparent; }}
    QFrame#thoughtBox {{ background: {t['thought_bg']};
        border: 1px solid {t['border']}; border-radius: 8px; }}
    QFrame#thoughtBox QLabel {{ background: transparent; }}
    QMessageBox, QFileDialog, QInputDialog {{ background: {t['bg']}; }}
    QDialog QLabel, QMessageBox QLabel, QFileDialog QLabel {{ color: {t['text']}; background: transparent; }}
    QDialogButtonBox QPushButton {{ min-width: 88px; }}
    QProgressDialog {{ background: {t['panel']}; }}
    """


def build_palette(t: dict) -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(t["code_bg"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(t["panel"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(t["panel"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(t["btn"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t["btn_text"]))
    pal.setColor(QPalette.ColorRole.BrightText, QColor("#ff6b6b"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t["sel"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(t["text"]))
    return pal
