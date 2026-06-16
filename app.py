# -*- coding: utf-8 -*-
"""
AI Studio Log Parser — десктоп-приложение (PySide6) для парсинга логов
чатов Google AI Studio (JSON с Google Drive, в т.ч. файлы без расширения).

Запуск:  python app.py
"""

from __future__ import annotations

import json
import sys
import re
import html as _html
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QIcon, QPixmap, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QToolButton, QMenu,
    QFileDialog, QMessageBox, QTabWidget, QPlainTextEdit, QScrollArea,
    QFrame, QDialog, QDialogButtonBox, QCheckBox, QComboBox, QGroupBox,
    QFormLayout, QLineEdit, QStatusBar, QSizePolicy, QProgressDialog,
    QTextEdit, QInputDialog, QAbstractItemView,
)

import core
import i18n
from i18n import tr

APP_NAME = "AI Studio Log Parser"
ORG = "ArenaTools"
ASSET_DIR = Path(__file__).resolve().parent / "assets" / "icons"

ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 70, 200, 10
BASE_FONT_PT = 10.0
RESPONSIVE_ICON_ONLY_ZOOM = 150
RESPONSIVE_ICON_ONLY_WIDTH = 980
VIEW_BATCH = 60

# ----------------------------------------------------------------------------
# Темы
# ----------------------------------------------------------------------------

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


def build_stylesheet(t: dict, scale: float = 1.0) -> str:
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
    """Единая палитра для Fusion/native диалогов, чтобы не всплывали белые фоны."""
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(t["bg"]))
    pal.setColor(QPalette.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.Base, QColor(t["code_bg"]))
    pal.setColor(QPalette.AlternateBase, QColor(t["panel"]))
    pal.setColor(QPalette.ToolTipBase, QColor(t["panel"]))
    pal.setColor(QPalette.ToolTipText, QColor(t["text"]))
    pal.setColor(QPalette.Text, QColor(t["text"]))
    pal.setColor(QPalette.Button, QColor(t["btn"]))
    pal.setColor(QPalette.ButtonText, QColor(t["btn_text"]))
    pal.setColor(QPalette.BrightText, QColor("#ff6b6b"))
    pal.setColor(QPalette.Highlight, QColor(t["sel"]))
    pal.setColor(QPalette.HighlightedText, QColor(t["text"]))
    return pal


# ----------------------------------------------------------------------------
# Иконки с безопасным fallback на эмодзи/текст
# ----------------------------------------------------------------------------

def icon_file(name: str) -> Path:
    return ASSET_DIR / name


_ICON_CACHE = {}
_PIXMAP_CACHE = {}


def load_icon(name: str) -> QIcon:
    if name in _ICON_CACHE:
        return _ICON_CACHE[name]
    p = icon_file(name)
    ic = QIcon(str(p)) if p.exists() else QIcon()
    _ICON_CACHE[name] = ic
    return ic


def load_pixmap(name: str, size: int = 18) -> QPixmap:
    key = (name, size)
    if key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[key]
    p = icon_file(name)
    out = QPixmap()
    if p.exists():
        pix = QPixmap(str(p))
        if not pix.isNull():
            out = pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    _PIXMAP_CACHE[key] = out
    return out


def strip_leading_emoji(text: str) -> str:
    # Убираем только декоративный первый символ/кластер перед обычной подписью.
    return re.sub(r"^[^\wА-Яа-яЁё]+\s*", "", text, count=1)

# ----------------------------------------------------------------------------
# Диалог настроек экспорта
# ----------------------------------------------------------------------------


class TextSeparatorsDialog(QDialog):
    """Расширенные настройки распознавания текстовых логов Arena/экспортов."""

    def __init__(self, parent, settings: QSettings):
        super().__init__(parent)
        self.setWindowTitle(tr("sep_title"))
        self.setMinimumWidth(560)
        self._s = settings

        lay = QVBoxLayout(self)
        hint = QLabel(tr("sep_hint"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        form = QFormLayout()
        self.ed_user = QTextEdit()
        self.ed_user.setAcceptRichText(False)
        self.ed_user.setMinimumHeight(86)
        self.ed_model = QTextEdit()
        self.ed_model.setAcceptRichText(False)
        self.ed_model.setMinimumHeight(86)
        self.cmb_num = QComboBox()
        self.cmb_num.addItem(tr("sep_num_alternating"), "alternating")
        self.cmb_num.addItem(tr("sep_num_model"), "model")
        self.cmb_num.addItem(tr("sep_num_user"), "user")
        form.addRow(tr("sep_user_headers"), self.ed_user)
        form.addRow(tr("sep_model_headers"), self.ed_model)
        form.addRow(tr("sep_numbered_mode"), self.cmb_num)
        lay.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("sep_save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._load()

    def _load(self):
        self.ed_user.setPlainText(self._s.value("parse/user_headers", ""))
        self.ed_model.setPlainText(self._s.value("parse/model_headers", ""))
        mode = self._s.value("parse/numbered_mode", "model")
        i = self.cmb_num.findData(mode)
        self.cmb_num.setCurrentIndex(i if i >= 0 else 0)

    def options(self) -> core.TextParseOptions:
        def lines(txt):
            return [x.strip() for x in txt.splitlines() if x.strip()]
        opts = core.TextParseOptions(
            user_headers=lines(self.ed_user.toPlainText()),
            model_headers=lines(self.ed_model.toPlainText()),
            numbered_mode=self.cmb_num.currentData(),
        )
        self._s.setValue("parse/user_headers", "\n".join(opts.user_headers))
        self._s.setValue("parse/model_headers", "\n".join(opts.model_headers))
        self._s.setValue("parse/numbered_mode", opts.numbered_mode)
        return opts



class CopySettingsDialog(QDialog):
    def __init__(self, parent, settings: QSettings):
        super().__init__(parent)
        self.setWindowTitle(tr("copy_settings_title"))
        self.setMinimumWidth(460)
        self._s = settings
        lay = QVBoxLayout(self)
        self.chk_service = QCheckBox(tr("copy_include_service"))
        self.chk_service.setChecked(self._s.value("copy/include_service", "true") == "true")
        lay.addWidget(self.chk_service)
        form = QFormLayout()
        self.cmb_sep = QComboBox()
        self.cmb_sep.addItem(tr("copy_sep_blank"), "blank")
        self.cmb_sep.addItem(tr("copy_sep_double"), "double")
        self.cmb_sep.addItem(tr("copy_sep_long"), "long")
        self.cmb_sep.addItem(tr("copy_sep_custom"), "custom")
        cur = self._s.value("copy/separator", "blank")
        i = self.cmb_sep.findData(cur)
        self.cmb_sep.setCurrentIndex(i if i >= 0 else 0)
        self.ed_custom = QLineEdit()
        self.ed_custom.setText(self._s.value("copy/custom_separator", "\n---\n"))
        form.addRow(tr("copy_separator"), self.cmb_sep)
        form.addRow(tr("copy_custom_separator"), self.ed_custom)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("sep_save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def save(self):
        self._s.setValue("copy/include_service", "true" if self.chk_service.isChecked() else "false")
        self._s.setValue("copy/separator", self.cmb_sep.currentData())
        self._s.setValue("copy/custom_separator", self.ed_custom.text())

class BatchExportDialog(QDialog):
    def __init__(self, parent, settings: QSettings, selected_count: int, all_count: int,
                 categories: set):
        super().__init__(parent)
        self.setWindowTitle(tr("batch_title"))
        self.setMinimumWidth(520)
        self._s = settings
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.cmb_source = QComboBox()
        self.cmb_source.addItem(tr("batch_selected", n=selected_count), "selected")
        self.cmb_source.addItem(tr("batch_all_loaded", n=all_count), "all")
        if selected_count <= 0:
            self.cmb_source.setCurrentIndex(1)
        form.addRow(tr("batch_source"), self.cmb_source)
        self.ed_cat = QLineEdit()
        self.ed_cat.setPlaceholderText("Только ответы модели по произведению")
        if categories:
            self.ed_cat.setText(sorted(categories)[0])
        form.addRow(tr("batch_result_category"), self.ed_cat)
        self.ed_note = QLineEdit()
        self.ed_note.setPlaceholderText("Экспортировано пакетной операцией")
        form.addRow(tr("batch_note"), self.ed_note)
        self.ed_tags = QLineEdit()
        self.ed_tags.setPlaceholderText("answers, novel-x, clean")
        form.addRow(tr("tags_label"), self.ed_tags)
        lay.addLayout(form)
        self.chk_load = QCheckBox(tr("batch_load_results"))
        self.chk_load.setChecked(True)
        self.chk_index = QCheckBox(tr("batch_index_results"))
        self.chk_index.setChecked(True)
        lay.addWidget(self.chk_load)
        lay.addWidget(self.chk_index)
        hint = QLabel(tr("batch_title") + ": " + tr("export_profiles"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("exp_ok"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def result_options(self):
        return {
            "source": self.cmb_source.currentData(),
            "category": self.ed_cat.text().strip(),
            "note": self.ed_note.text().strip(),
            "tags": [x.strip().lstrip("#") for x in re.split(r"[,;]", self.ed_tags.text()) if x.strip()],
            "load": self.chk_load.isChecked(),
            "index": self.chk_index.isChecked(),
        }

class ExportDialog(QDialog):
    def __init__(self, parent, settings: QSettings, batch_count: int = 1):
        super().__init__(parent)
        self.setWindowTitle(tr("exp_title"))
        self.setMinimumWidth(460)
        self._s = settings

        lay = QVBoxLayout(self)

        prof_row = QHBoxLayout()
        prof_row.addWidget(QLabel(tr("export_profiles")))
        self.cmb_profile = QComboBox()
        self.cmb_profile.addItem(tr("profile_none"), None)
        self.cmb_profile.addItem(tr("profile_answers_txt"), {"fmt": "txt", "content": core.CONTENT_ANSWERS, "thoughts": core.THOUGHTS_EXCLUDE})
        self.cmb_profile.addItem(tr("profile_full_txt"), {"fmt": "txt", "content": core.CONTENT_ALL, "thoughts": core.THOUGHTS_EXCLUDE})
        self.cmb_profile.addItem(tr("profile_full_md"), {"fmt": "md", "content": core.CONTENT_ALL, "thoughts": core.THOUGHTS_EXCLUDE})
        self.cmb_profile.addItem(tr("profile_prompts_txt"), {"fmt": "txt", "content": core.CONTENT_PROMPTS, "thoughts": core.THOUGHTS_EXCLUDE})
        try:
            for name, data in json.loads(self._s.value("exp/profiles", "{}" )).items():
                if isinstance(data, dict):
                    self.cmb_profile.addItem(name, data)
        except Exception:
            pass
        b_save_profile = QPushButton(tr("profile_save"))
        b_save_profile.clicked.connect(self._save_profile_from_current)
        prof_row.addWidget(self.cmb_profile, 1)
        prof_row.addWidget(b_save_profile)
        lay.addLayout(prof_row)

        gb_fmt = QGroupBox(tr("exp_format"))
        f = QFormLayout(gb_fmt)
        self.cmb_fmt = QComboBox()
        self.cmb_fmt.addItem(tr("exp_fmt_txt"), "txt")
        self.cmb_fmt.addItem(tr("exp_fmt_html"), "html")
        self.cmb_fmt.addItem(tr("exp_fmt_md"), "md")
        self.cmb_fmt.addItem(tr("exp_fmt_json"), "json")
        self.cmb_fmt.addItem(tr("exp_fmt_jsonl"), "jsonl")
        f.addRow(tr("exp_format_file"), self.cmb_fmt)
        self.cmb_content = QComboBox()
        self.cmb_content.addItem(tr("exp_content_all"), core.CONTENT_ALL)
        self.cmb_content.addItem(tr("exp_content_prompts"), core.CONTENT_PROMPTS)
        self.cmb_content.addItem(tr("exp_content_answers"), core.CONTENT_ANSWERS)
        self.cmb_content.addItem(tr("exp_content_thoughts"), core.CONTENT_THOUGHTS)
        f.addRow(tr("exp_content_what"), self.cmb_content)
        lay.addWidget(gb_fmt)

        gb_opt = QGroupBox(tr("exp_content"))
        v = QVBoxLayout(gb_opt)
        self.chk_num = QCheckBox(tr("exp_numbering"))
        self.chk_time = QCheckBox(tr("exp_timestamps"))
        self.chk_meta = QCheckBox(tr("exp_metadata"))
        self.chk_sys = QCheckBox(tr("exp_sysinstr"))
        self.chk_att = QCheckBox(tr("exp_attachments"))
        self.chk_md = QCheckBox(tr("exp_render_md"))
        for w in (self.chk_num, self.chk_time, self.chk_meta,
                  self.chk_sys, self.chk_att, self.chk_md):
            v.addWidget(w)

        f2 = QFormLayout()
        self.cmb_th = QComboBox()
        self.cmb_th.addItem(tr("exp_th_exclude"), core.THOUGHTS_EXCLUDE)
        self.cmb_th.addItem(tr("exp_th_include"), core.THOUGHTS_INCLUDE)
        self.cmb_th.addItem(tr("exp_th_separate"), core.THOUGHTS_SEPARATE)
        f2.addRow(tr("exp_thoughts"), self.cmb_th)
        v.addLayout(f2)
        lay.addWidget(gb_opt)

        gb_lbl = QGroupBox(tr("exp_labels"))
        vl = QVBoxLayout(gb_lbl)
        self.chk_auto_model = QCheckBox(tr("exp_auto_model"))
        vl.addWidget(self.chk_auto_model)
        fl = QFormLayout()
        self.ed_user = QLineEdit()
        self.ed_model = QLineEdit()
        fl.addRow(tr("exp_label_user"), self.ed_user)
        fl.addRow(tr("exp_label_model"), self.ed_model)
        vl.addLayout(fl)
        self.chk_auto_model.toggled.connect(
            lambda on: self.ed_model.setEnabled(not on))
        lay.addWidget(gb_lbl)

        if batch_count > 1:
            note = QLabel(tr("exp_batch_note", n=batch_count))
            note.setObjectName("muted")
            lay.addWidget(note)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("exp_ok"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._load()
        self.cmb_profile.currentIndexChanged.connect(self._apply_profile)

    def _set_combo_data(self, cmb, value):
        i = cmb.findData(value)
        if i >= 0:
            cmb.setCurrentIndex(i)

    def _apply_profile(self):
        data = self.cmb_profile.currentData()
        if not isinstance(data, dict):
            return
        self._set_combo_data(self.cmb_fmt, data.get("fmt", "txt"))
        self._set_combo_data(self.cmb_content, data.get("content", core.CONTENT_ALL))
        self._set_combo_data(self.cmb_th, data.get("thoughts", core.THOUGHTS_EXCLUDE))
        if "numbering" in data:
            self.chk_num.setChecked(bool(data["numbering"]))
        if "timestamps" in data:
            self.chk_time.setChecked(bool(data["timestamps"]))
        if "metadata" in data:
            self.chk_meta.setChecked(bool(data["metadata"]))

    def _save_profile_from_current(self):
        name, ok = QInputDialog.getText(self, tr("exp_title"), tr("profile_name"))
        name = name.strip()
        if not ok or not name:
            return
        try:
            profiles = json.loads(self._s.value("exp/profiles", "{}"))
            if not isinstance(profiles, dict):
                profiles = {}
        except Exception:
            profiles = {}
        profiles[name] = {
            "fmt": self.cmb_fmt.currentData(),
            "content": self.cmb_content.currentData(),
            "thoughts": self.cmb_th.currentData(),
            "numbering": self.chk_num.isChecked(),
            "timestamps": self.chk_time.isChecked(),
            "metadata": self.chk_meta.isChecked(),
        }
        self._s.setValue("exp/profiles", json.dumps(profiles, ensure_ascii=False))
        self.cmb_profile.addItem(name, profiles[name])
        self.cmb_profile.setCurrentIndex(self.cmb_profile.count() - 1)
        if self.parent():
            self.parent().statusBar().showMessage(tr("profile_saved", name=name), 4000)

    def _load(self):
        s = self._s

        def idx(cmb, val):
            i = cmb.findData(val)
            return i if i >= 0 else 0

        self.cmb_fmt.setCurrentIndex(idx(self.cmb_fmt, s.value("exp/fmt", "txt")))
        self.cmb_content.setCurrentIndex(
            idx(self.cmb_content, s.value("exp/content", core.CONTENT_ALL)))
        self.cmb_th.setCurrentIndex(idx(self.cmb_th, s.value("exp/thoughts",
                                                             core.THOUGHTS_EXCLUDE)))
        self.chk_num.setChecked(s.value("exp/num", "true") == "true")
        self.chk_time.setChecked(s.value("exp/time", "false") == "true")
        self.chk_meta.setChecked(s.value("exp/meta", "true") == "true")
        self.chk_sys.setChecked(s.value("exp/sys", "true") == "true")
        self.chk_att.setChecked(s.value("exp/att", "true") == "true")
        self.chk_md.setChecked(s.value("exp/md", "true") == "true")
        self.chk_auto_model.setChecked(
            s.value("exp/auto_model", "true") == "true")
        self.ed_user.setText(s.value("exp/user_label", tr("user")))
        self.ed_model.setText(s.value("exp/model_label", tr("model")))
        self.ed_model.setEnabled(not self.chk_auto_model.isChecked())

    def options(self) -> core.ExportOptions:
        s = self._s
        opts = core.ExportOptions(
            fmt=self.cmb_fmt.currentData(),
            content=self.cmb_content.currentData(),
            numbering=self.chk_num.isChecked(),
            thoughts=self.cmb_th.currentData(),
            timestamps=self.chk_time.isChecked(),
            metadata=self.chk_meta.isChecked(),
            attachments=self.chk_att.isChecked(),
            system_instruction=self.chk_sys.isChecked(),
            render_markdown=self.chk_md.isChecked(),
            user_label=self.ed_user.text().strip() or tr("user"),
            model_label=self.ed_model.text().strip() or tr("model"),
            auto_model_label=self.chk_auto_model.isChecked(),
        )
        s.setValue("exp/fmt", opts.fmt)
        s.setValue("exp/content", opts.content)
        s.setValue("exp/thoughts", opts.thoughts)
        s.setValue("exp/num", "true" if opts.numbering else "false")
        s.setValue("exp/time", "true" if opts.timestamps else "false")
        s.setValue("exp/meta", "true" if opts.metadata else "false")
        s.setValue("exp/sys", "true" if opts.system_instruction else "false")
        s.setValue("exp/att", "true" if opts.attachments else "false")
        s.setValue("exp/md", "true" if opts.render_markdown else "false")
        s.setValue("exp/auto_model", "true" if opts.auto_model_label else "false")
        s.setValue("exp/user_label", opts.user_label)
        s.setValue("exp/model_label", opts.model_label)
        return opts


# ----------------------------------------------------------------------------
# Карточка сообщения
# ----------------------------------------------------------------------------

class MessageCard(QFrame):
    def __init__(self, msg: core.Message, num: int, theme: dict,
                 render_md: bool, show_thoughts: bool, status_cb,
                 model_name: str = ""):
        super().__init__()
        self.msg = msg
        self._status = status_cb
        self.setObjectName("msgCardUser" if msg.is_user else "msgCard")
        # без этого фон QFrame-наследника может не краситься из QSS
        self.setAttribute(Qt.WA_StyledBackground, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(6)

        # шапка
        hdr = QHBoxLayout()
        if msg.is_user:
            who = tr("user")
        else:
            who = model_name or tr("model")
        if msg.role not in ("user", "model"):
            who = msg.role.upper()
        color = theme["user"] if msg.is_user else theme["model"]
        pix = load_pixmap("user.png" if msg.is_user else "model.png", 18)
        prefix = ""
        if not pix.isNull():
            il = QLabel()
            il.setPixmap(pix)
            hdr.addWidget(il)
        else:
            prefix = "👤 " if msg.is_user else "🤖 "
        lbl = QLabel(f"<b style='color:{color}'>#{num} {prefix}{_html.escape(who)}</b>")
        lbl.setTextFormat(Qt.RichText)
        hdr.addWidget(lbl)
        if msg.time_str():
            tl = QLabel(msg.time_str())
            tl.setObjectName("muted")
            hdr.addWidget(tl)
        if msg.token_count:
            tk = QLabel(f"{msg.token_count} {tr('tokens_short')}")
            tk.setObjectName("muted")
            hdr.addWidget(tk)
        hdr.addStretch(1)

        btn = QPushButton(tr("copy"))
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._copy)
        hdr.addWidget(btn)

        # доп. кнопка-меню для размышлений
        if show_thoughts and msg.has_thoughts:
            more = QToolButton()
            more.setText(tr("copy_more"))
            more.setCursor(Qt.PointingHandCursor)
            more.setPopupMode(QToolButton.InstantPopup)
            m = QMenu(more)
            m.addAction(tr("copy_with_thoughts"), self._copy_with_thoughts)
            m.addAction(tr("copy_only_thoughts"), self._copy_thoughts_only)
            more.setMenu(m)
            hdr.addWidget(more)
        lay.addLayout(hdr)

        # размышления
        if show_thoughts and msg.has_thoughts:
            box = QFrame()
            box.setObjectName("thoughtBox")
            box.setAttribute(Qt.WA_StyledBackground, True)
            bl = QVBoxLayout(box)
            bl.setContentsMargins(10, 8, 10, 8)
            cap = QLabel(f"<b style='color:{theme['thought']}'>"
                         f"{tr('thoughts_n', n=len(msg.thoughts))}</b>")
            cap.setTextFormat(Qt.RichText)
            bl.addWidget(cap)
            body = self._make_body("\n\n".join(t.strip() for t in msg.thoughts),
                                   render_md)
            bl.addWidget(body)
            lay.addWidget(box)

        # вложения
        for a in msg.attachments:
            al = QLabel(
                f"📎 <a href='{_html.escape(a.url, quote=True)}'>"
                f"{_html.escape(a.label)} (Google Drive)</a>"
                if a.url else f"📎 {_html.escape(a.label)}"
            )
            al.setTextFormat(Qt.RichText)
            al.setOpenExternalLinks(True)
            al.setObjectName("muted")
            lay.addWidget(al)

        # текст
        text = msg.text.strip()
        if text:
            body = self._make_body(text, render_md and not msg.is_user)
            lay.addWidget(body)
        elif not msg.attachments and not msg.has_thoughts:
            e = QLabel(tr("empty_message"))
            e.setObjectName("muted")
            lay.addWidget(e)

    def _make_body(self, text: str, rich: bool) -> QLabel:
        body = QLabel()
        body.setWordWrap(True)
        body.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        body.setOpenExternalLinks(True)
        if rich:
            body.setTextFormat(Qt.RichText)
            body.setText(core.markdown_to_html(text))
        else:
            body.setTextFormat(Qt.PlainText)
            body.setText(text)
        # позволяем карточке сжиматься — никаких горизонтальных ползунков
        body.setMinimumWidth(0)
        body.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        return body

    def _copy(self):
        QGuiApplication.clipboard().setText(
            core.message_copy_text(self.msg, include_thoughts=False))
        self._status(tr("msg_copied"))

    def _copy_with_thoughts(self):
        QGuiApplication.clipboard().setText(
            core.message_copy_text(self.msg, include_thoughts=True))
        self._status(tr("msg_copied"))

    def _copy_thoughts_only(self):
        QGuiApplication.clipboard().setText(
            core.message_copy_text(self.msg, thoughts_only=True))
        self._status(tr("thoughts_copied"))


# ----------------------------------------------------------------------------
# Главное окно
# ----------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1240, 800)
        self.setMinimumSize(640, 420)
        self.setAcceptDrops(True)

        app_icon = load_icon("app_logo.png")
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self.settings = QSettings(ORG, APP_NAME)
        self.theme_name = self.settings.value("ui/theme", "dark")
        self.render_md = self.settings.value("ui/render_md", "true") == "true"
        self.show_thoughts = self.settings.value("ui/show_thoughts", "true") == "true"
        self.show_extensions = self.settings.value("ui/show_extensions", "false") == "true"
        self.show_diagnostics = self.settings.value("ui/show_diagnostics", "false") == "true"
        try:
            self.zoom = int(self.settings.value("ui/zoom", 100))
        except (TypeError, ValueError):
            self.zoom = 100
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom))
        i18n.set_lang(self.settings.value("ui/lang", "ru"))
        self.text_parse_options = self._load_text_parse_options()

        self.chats: list = []
        self.current: core.ChatLog | None = None
        self.chat_categories: dict = self._load_chat_categories()
        self.chat_notes: dict = self._load_chat_notes()
        self.chat_tags: dict = self._load_chat_tags()
        self.chat_derived: dict = self._load_chat_derived()
        self.categories: set = set(v for v in self.chat_categories.values() if v)
        self.project_name = self.settings.value("org/project_name", "")
        self.project_path = self.settings.value("org/project_path", "")
        self.recent_projects = self._load_recent_projects()
        self._index = None       # ленивый SearchIndex
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.timeout.connect(self._apply_pending_zoom)
        self._pending_rebuild = False
        self._render_generation = 0
        self._render_next = 0
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave_project)
        self._autosave_timer.start(30000)

        self._build_ui()
        self.apply_theme()
        self.statusBar().showMessage(tr("status_hint"))

    # ---------- UI ----------

    def _load_text_parse_options(self) -> core.TextParseOptions:
        def split_saved(v):
            return [x.strip() for x in str(v or "").splitlines() if x.strip()]
        return core.TextParseOptions(
            user_headers=split_saved(self.settings.value("parse/user_headers", "")),
            model_headers=split_saved(self.settings.value("parse/model_headers", "")),
            numbered_mode=self.settings.value("parse/numbered_mode", "model"),
        )


    def _load_json_setting(self, key: str, default):
        try:
            data = json.loads(self.settings.value(key, json.dumps(default, ensure_ascii=False)))
            return data if isinstance(data, type(default)) else default
        except Exception:
            return default

    def _save_json_setting(self, key: str, value):
        self.settings.setValue(key, json.dumps(value, ensure_ascii=False))

    def _load_chat_tags(self) -> dict:
        return self._load_json_setting("org/chat_tags", {})

    def _save_chat_tags(self):
        self._save_json_setting("org/chat_tags", self.chat_tags)

    def _load_chat_derived(self) -> dict:
        return self._load_json_setting("org/chat_derived", {})

    def _save_chat_derived(self):
        self._save_json_setting("org/chat_derived", self.chat_derived)

    def _load_recent_projects(self) -> list:
        data = self._load_json_setting("org/recent_projects", [])
        return [x for x in data if isinstance(x, str) and x]

    def _save_recent_projects(self):
        self._save_json_setting("org/recent_projects", self.recent_projects[:10])

    def _remember_project(self, path: str):
        if not path:
            return
        self.recent_projects = [path] + [p for p in self.recent_projects if p != path]
        self._save_recent_projects()

    def _chat_tags(self, chat) -> list:
        vals = self.chat_tags.get(chat.path, [])
        return vals if isinstance(vals, list) else []

    def _load_chat_categories(self) -> dict:
        try:
            data = json.loads(self.settings.value("org/chat_categories", "{}"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_chat_categories(self):
        self.settings.setValue("org/chat_categories",
                               json.dumps(self.chat_categories, ensure_ascii=False))

    def _load_chat_notes(self) -> dict:
        try:
            data = json.loads(self.settings.value("org/chat_notes", "{}"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_chat_notes(self):
        self.settings.setValue("org/chat_notes",
                               json.dumps(self.chat_notes, ensure_ascii=False))

    def _chat_category(self, chat) -> str:
        return self.chat_categories.get(chat.path, "")

    def _chat_note(self, chat) -> str:
        return self.chat_notes.get(chat.path, "")

    def _decorate_button(self, btn, icon_name: str, min_width: int = 0):
        original = btn.text()
        ic = load_icon(icon_name)
        compact = strip_leading_emoji(original) or original
        if not ic.isNull():
            btn.setIcon(ic)
            btn.setText(compact)
        btn.setProperty("fullText", compact)
        btn.setProperty("compactText", original[:2].strip() or compact[:1])
        btn.setToolTip(btn.toolTip() or compact)
        if hasattr(btn, "setToolButtonStyle"):
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        if min_width:
            btn.setMinimumWidth(min_width)
        btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)



    def new_project(self):
        name, ok = QInputDialog.getText(self, APP_NAME, tr("project_name"),
                                        text=self.project_name or "StudioLogHelper project")
        name = name.strip()
        if not ok or not name:
            return
        self.project_name = name
        self.project_path = ""
        self.categories.clear()
        self.chat_categories.clear()
        self.chat_notes.clear()
        self.chat_tags.clear()
        self.chat_derived.clear()
        self.settings.setValue("org/project_name", name)
        self.settings.setValue("org/project_path", "")
        self._save_chat_categories()
        self._save_chat_notes()
        self._save_chat_tags()
        self._save_chat_derived()
        self._refresh_filter_controls()
        self._refresh_file_list()
        self.statusBar().showMessage(tr("project_created", name=name), 5000)

    def _project_doc(self) -> dict:
        files = []
        known = {c.path: c for c in self.chats}
        for path in sorted(set(known) | set(self.chat_categories) | set(self.chat_notes)
                           | set(self.chat_tags) | set(self.chat_derived)):
            chat = known.get(path)
            item = {
                "path": path,
                "category": self.chat_categories.get(path, ""),
                "note": self.chat_notes.get(path, ""),
                "tags": self.chat_tags.get(path, []),
                "derived_from": self.chat_derived.get(path, ""),
            }
            if chat:
                item.update({
                    "title": chat.title,
                    "source_format": chat.source_format,
                    "model": chat.model,
                    "messages": len(chat.messages),
                    "prompts": chat.user_count,
                    "answers": chat.model_count,
                })
            files.append(item)
        return {
            "app": APP_NAME,
            "schema": "studiologhelper.project.v1",
            "created_or_saved_at": datetime.now().isoformat(timespec="seconds"),
            "project": {"name": self.project_name or "", "path": self.project_path or ""},
            "categories": sorted(self.categories),
            "files": files,
            "parser": {
                "numbered_mode": self.text_parse_options.numbered_mode,
                "user_headers": self.text_parse_options.user_headers,
                "model_headers": self.text_parse_options.model_headers,
            },
            "ui": {"show_extensions": self.show_extensions, "theme": self.theme_name},
        }

    def _write_project(self, path: str):
        if not path:
            return
        doc = self._project_doc()
        Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        self.project_path = path
        self.settings.setValue("org/project_path", path)
        if self.project_name:
            self.settings.setValue("org/project_name", self.project_name)
        self._remember_project(path)

    def save_project(self):
        last = self.project_path or self.settings.value("ui/last_dir", str(Path.home()))
        path, _ = QFileDialog.getSaveFileName(
            self, tr("project_save"), last, "StudioLogHelper Project (*.slh.json);;JSON (*.json)")
        if not path:
            return
        if not path.endswith(".json"):
            path += ".slh.json"
        self._write_project(path)
        self.statusBar().showMessage(tr("project_saved", path=path), 6000)

    def _autosave_project(self):
        if not self.project_path:
            return
        try:
            self._write_project(self.project_path)
        except OSError:
            return

    def closeEvent(self, e):
        self._autosave_project()
        super().closeEvent(e)


    def open_project_path(self, path: str):
        if not path:
            return
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as ex:
            QMessageBox.warning(self, APP_NAME, str(ex))
            return
        self._load_project_doc(doc, path)

    def _load_project_doc(self, doc: dict, path: str):
        self.project_path = path
        self.project_name = (doc.get("project") or {}).get("name", "")
        self.categories = set(x for x in doc.get("categories", []) if isinstance(x, str))
        self.chat_categories.clear()
        self.chat_notes.clear()
        self.chat_tags.clear()
        self.chat_derived.clear()
        load_paths = []
        for item in doc.get("files", []):
            if not isinstance(item, dict):
                continue
            f = item.get("path", "")
            if not f:
                continue
            cat = item.get("category", "")
            note = item.get("note", "")
            tags = item.get("tags", [])
            derived = item.get("derived_from", "")
            if cat:
                self.chat_categories[f] = cat
                self.categories.add(cat)
            if note:
                self.chat_notes[f] = note
            if isinstance(tags, list) and tags:
                self.chat_tags[f] = [str(x).strip() for x in tags if str(x).strip()]
            if derived:
                self.chat_derived[f] = str(derived)
            if Path(f).exists():
                load_paths.append(f)
        self._save_chat_categories()
        self._save_chat_notes()
        self._save_chat_tags()
        self._save_chat_derived()
        self.settings.setValue("org/project_path", path)
        self.settings.setValue("org/project_name", self.project_name)
        self.load_paths(load_paths)
        self._refresh_file_list()
        self._remember_project(path)
        self.statusBar().showMessage(tr("project_loaded", path=path), 6000)

    def open_project(self):
        last = self.project_path or self.settings.value("ui/last_dir", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self, tr("project_open"), last, "StudioLogHelper Project (*.slh.json *.json);;All files (*)")
        if not path:
            return
        self.open_project_path(path)

    def set_note_current(self):
        if not self._need_chat():
            return
        note, ok = QInputDialog.getMultiLineText(
            self, APP_NAME, tr("project_note"), self._chat_note(self.current))
        if not ok:
            return
        note = note.strip()
        if note:
            self.chat_notes[self.current.path] = note
        else:
            self.chat_notes.pop(self.current.path, None)
        self._save_chat_notes()
        self._rebuild_view()
        self.statusBar().showMessage(tr("note_saved"), 4000)



    def reveal_current_file(self):
        if not self._need_chat():
            return
        p = Path(self.current.path)
        if not p.exists():
            QMessageBox.information(self, APP_NAME, tr("reveal_no_file"))
            return
        if sys.platform == "win32":
            import subprocess
            subprocess.Popen(["explorer", f"/select,{p}"])
            return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))

    def set_tags_current(self):
        if not self._need_chat():
            return
        current = ", ".join(self._chat_tags(self.current))
        raw, ok = QInputDialog.getText(self, APP_NAME, tr("tags_prompt"), text=current)
        if not ok:
            return
        tags = []
        seen = set()
        for t in re.split(r"[,;]", raw):
            t = t.strip().lstrip("#")
            if t and t.lower() not in seen:
                tags.append(t)
                seen.add(t.lower())
        if tags:
            self.chat_tags[self.current.path] = tags
        else:
            self.chat_tags.pop(self.current.path, None)
        self._save_chat_tags()
        self._refresh_filter_controls()
        self._refresh_file_list(select_path=self.current.path)
        self._rebuild_view()
        self.statusBar().showMessage(tr("tags_saved"), 4000)

    def _selected_chats(self) -> list:
        selected = []
        for it in self.file_list.selectedItems():
            path = it.data(Qt.UserRole)
            for c in self.chats:
                if c.path == path:
                    selected.append(c)
                    break
        return selected

    def create_category(self):
        name, ok = QInputDialog.getText(self, APP_NAME, tr("category_name"))
        name = name.strip()
        if not ok or not name:
            return
        self.categories.add(name)
        self._refresh_filter_controls()
        self.statusBar().showMessage(tr("category_created", name=name), 4000)

    def assign_category_current(self):
        if not self._need_chat():
            return
        items = sorted(self.categories) or [tr("uncategorized")]
        name, ok = QInputDialog.getItem(self, APP_NAME, tr("category_name"),
                                        items, 0, True)
        name = name.strip()
        if not ok or not name:
            return
        self.categories.add(name)
        self.chat_categories[self.current.path] = name
        self._save_chat_categories()
        self._refresh_filter_controls()
        self._refresh_file_list(select_path=self.current.path)
        self.statusBar().showMessage(tr("category_assigned", name=name), 4000)


    def batch_export_set(self):
        selected = self._selected_chats()
        if not self.chats:
            QMessageBox.information(self, APP_NAME, tr("batch_no_files"))
            return
        bd = BatchExportDialog(self, self.settings, len(selected), len(self.chats), self.categories)
        if bd.exec() != QDialog.Accepted:
            return
        bopts = bd.result_options()
        chats = selected if bopts["source"] == "selected" and selected else list(self.chats)
        if not chats:
            QMessageBox.information(self, APP_NAME, tr("batch_no_files"))
            return
        # Обычный диалог экспорта остаётся — профили можно выбрать там, ничего не навязываем.
        dlg = ExportDialog(self, self.settings, batch_count=len(chats))
        if dlg.exec() != QDialog.Accepted:
            return
        opts = dlg.options()
        last = self.settings.value("ui/export_dir", self.settings.value("ui/last_dir", str(Path.home())))
        out_dir = QFileDialog.getExistingDirectory(self, tr("dlg_save_dir"), last)
        if not out_dir:
            return
        self.settings.setValue("ui/export_dir", out_dir)
        created, errors = [], []
        source_by_out = {}
        for chat in chats:
            try:
                paths = core.export_to_files(chat, opts, out_dir)
                created.extend(paths)
                for cp in paths:
                    source_by_out[cp] = chat.path
            except (OSError, ValueError) as ex:
                errors.append(f"{chat.title}: {ex}")
        cat = bopts["category"]
        note = bopts["note"]
        tags = bopts.get("tags") or []
        if cat:
            self.categories.add(cat)
        if bopts["load"] and created:
            self.load_paths(created)
            for cp in created:
                if cat:
                    self.chat_categories[cp] = cat
                if note:
                    self.chat_notes[cp] = note
                if tags:
                    self.chat_tags[cp] = tags
                if source_by_out.get(cp):
                    self.chat_derived[cp] = source_by_out[cp]
            self._save_chat_categories()
            self._save_chat_notes()
            self._save_chat_tags()
            self._save_chat_derived()
            self._refresh_filter_controls()
            self._refresh_file_list()
        if bopts["index"] and created:
            try:
                idx = self._get_index()
                idx.index_paths([out_dir])
                self._update_index_stats()
            except Exception as ex:
                errors.append(f"index: {ex}")
        msg = tr("batch_done", n=len(created), dir=out_dir)
        if errors:
            msg += "\n\n" + tr("export_errors") + "\n" + "\n".join(errors[:10])
        QMessageBox.information(self, tr("export_done"), msg)
        self._autosave_project()

    def create_text_log(self):
        last = self.settings.value("ui/last_dir", str(Path.home()))
        name, ok = QInputDialog.getText(self, APP_NAME, tr("file_name"),
                                        text="new_chat.txt")
        name = name.strip()
        if not ok or not name:
            return
        if not Path(name).suffix:
            name += ".txt"
        folder = QFileDialog.getExistingDirectory(self, tr("dlg_save_dir"), last)
        if not folder:
            return
        p = Path(folder) / Path(name).name
        if p.exists():
            QMessageBox.warning(self, APP_NAME, f"File exists: {p}")
            return
        clip = QGuiApplication.clipboard().text().strip()
        if clip:
            content = "User:\n[добавьте запрос или описание главы]\n\nModel:\n" + clip + "\n"
        else:
            content = (
                "User:\n"
                "[сюда можно вставить запрос, план главы или пометку]\n\n"
                "Model:\n"
                "[сюда можно вставить цельный ответ модели / главу / фрагмент]\n"
            )
        p.write_text(content, encoding="utf-8")
        self.settings.setValue("ui/last_dir", folder)
        self.statusBar().showMessage(tr("text_log_created", path=str(p)), 5000)
        self.load_paths([str(p)], select_path=str(p))

    def open_text_separators(self):
        dlg = TextSeparatorsDialog(self, self.settings)
        if dlg.exec() == QDialog.Accepted:
            self.text_parse_options = dlg.options()
            self.statusBar().showMessage(tr("sep_saved"), 4000)

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)

        # верхняя панель
        top = QHBoxLayout()
        top.setSpacing(6)
        b_open = QPushButton(tr("open_files"))
        b_open.clicked.connect(self.open_files)
        self._decorate_button(b_open, "search.png", 150)
        b_folder = QPushButton(tr("open_folder"))
        b_folder.clicked.connect(self.open_folder)
        self._decorate_button(b_folder, "search.png", 155)
        top.addWidget(b_open)
        top.addWidget(b_folder)

        self.btn_copy = QToolButton()
        self.btn_copy.setText(tr("copy_menu"))
        self.btn_copy.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self.btn_copy)
        m.addAction(tr("copy_all"), lambda: self.copy_chat(core.COPY_ALL))
        m.addAction(tr("copy_prompts"), lambda: self.copy_chat(core.COPY_PROMPTS))
        m.addAction(tr("copy_answers"), lambda: self.copy_chat(core.COPY_ANSWERS))
        m.addAction(tr("copy_thoughts"), lambda: self.copy_chat(core.COPY_THOUGHTS))
        m.addSeparator()
        m.addAction(tr("copy_settings"), self.open_copy_settings)
        self.btn_copy.setMenu(m)
        self._decorate_button(self.btn_copy, "export.png", 130)
        top.addWidget(self.btn_copy)

        self.btn_export = QPushButton(tr("export_current"))
        self.btn_export.setObjectName("accent")
        self.btn_export.clicked.connect(self.export_current)
        self._decorate_button(self.btn_export, "export.png", 125)
        self.btn_export_all = QPushButton(tr("export_all"))
        self.btn_export_all.clicked.connect(self.export_all)
        self._decorate_button(self.btn_export_all, "export.png", 190)
        top.addWidget(self.btn_export)
        top.addWidget(self.btn_export_all)

        b_sep = QPushButton(tr("sep_button"))
        b_sep.clicked.connect(self.open_text_separators)
        self._decorate_button(b_sep, "search.png", 190)
        top.addWidget(b_sep)

        self.btn_org = QToolButton()
        self.btn_org.setText(tr("organize_button"))
        self.btn_org.setToolTip(tr("organize_tip"))
        self.btn_org.setPopupMode(QToolButton.InstantPopup)
        om = QMenu(self.btn_org)
        om.addAction(tr("project_new"), self.new_project)
        om.addAction(tr("project_open"), self.open_project)
        recent = om.addMenu(tr("recent_projects"))
        if self.recent_projects:
            for rp in self.recent_projects[:8]:
                recent.addAction(Path(rp).name, lambda p=rp: self.open_project_path(p))
        else:
            a = recent.addAction("—")
            a.setEnabled(False)
        om.addAction(tr("project_save"), self.save_project)
        om.addSeparator()
        om.addAction(tr("batch_export_set"), self.batch_export_set)
        om.addSeparator()
        om.addAction(tr("new_category"), self.create_category)
        om.addAction(tr("assign_category"), self.assign_category_current)
        om.addAction(tr("set_tags_current"), self.set_tags_current)
        om.addAction(tr("project_note_current"), self.set_note_current)
        om.addAction(tr("reveal_current_file"), self.reveal_current_file)
        om.addSeparator()
        om.addAction(tr("new_text_log"), self.create_text_log)
        self.btn_org.setMenu(om)
        self._decorate_button(self.btn_org, "export.png", 210)
        top.addWidget(self.btn_org)

        top.addStretch(1)
        root.addLayout(top)

        # Вторая строка настроек: разгружает панель, чтобы кнопка разделителей
        # не наезжала на Markdown/Размышления при крупном масштабе.
        top_opts = QHBoxLayout()
        top_opts.setSpacing(8)
        top_opts.addStretch(1)

        self.chk_view_md = QCheckBox(tr("view_markdown"))
        self.chk_view_md.setChecked(self.render_md)
        self.chk_view_md.toggled.connect(self._toggle_md)
        self.chk_view_th = QCheckBox(tr("view_thoughts"))
        self.chk_view_th.setChecked(self.show_thoughts)
        self.chk_view_th.toggled.connect(self._toggle_thoughts)
        top_opts.addWidget(self.chk_view_md)
        top_opts.addWidget(self.chk_view_th)

        b_zout = QPushButton("A−")
        b_zout.setFixedWidth(40)
        b_zout.setToolTip(tr("zoom_out_tip"))
        b_zout.clicked.connect(lambda: self.set_zoom(self.zoom - ZOOM_STEP))
        b_zin = QPushButton("A+")
        b_zin.setFixedWidth(40)
        b_zin.setToolTip(tr("zoom_in_tip"))
        b_zin.clicked.connect(lambda: self.set_zoom(self.zoom + ZOOM_STEP))
        self.lbl_zoom = QLabel(f"{self.zoom}%")
        self.lbl_zoom.setObjectName("muted")
        self.lbl_zoom.setMinimumWidth(48)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        top_opts.addWidget(b_zout)
        top_opts.addWidget(self.lbl_zoom)
        top_opts.addWidget(b_zin)

        self.cmb_lang = QComboBox()
        for code, name in i18n.LANGS.items():
            self.cmb_lang.addItem(name, code)
        self.cmb_lang.setCurrentIndex(
            max(0, self.cmb_lang.findData(i18n.get_lang())))
        self.cmb_lang.setToolTip(tr("lang_tip"))
        self.cmb_lang.currentIndexChanged.connect(self._change_lang)
        top_opts.addWidget(self.cmb_lang)

        self.btn_theme = QPushButton("🌙" if self.theme_name == "dark" else "☀️")
        self.btn_theme.setFixedWidth(44)
        self.btn_theme.setToolTip(tr("theme_tip"))
        self.btn_theme.clicked.connect(self.toggle_theme)
        top_opts.addWidget(self.btn_theme)
        root.addLayout(top_opts)
        self._top_buttons = [b_open, b_folder, self.btn_copy, self.btn_export,
                             self.btn_export_all, b_sep, self.btn_org]

        # сплиттер: список файлов | контент
        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        cap_row = QHBoxLayout()
        cap = QLabel(tr("loaded_logs"))
        cap.setObjectName("muted")
        cap_row.addWidget(cap, 1)
        self.chk_show_ext = QCheckBox(tr("show_extensions"))
        self.chk_show_ext.setToolTip(tr("show_extensions_tip"))
        self.chk_show_ext.setChecked(self.show_extensions)
        self.chk_show_ext.toggled.connect(self._toggle_extensions)
        cap_row.addWidget(self.chk_show_ext)
        self.chk_show_diag = QCheckBox(tr("show_diagnostics"))
        self.chk_show_diag.setToolTip(tr("show_diagnostics_tip"))
        self.chk_show_diag.setChecked(self.show_diagnostics)
        self.chk_show_diag.toggled.connect(self._toggle_diagnostics)
        cap_row.addWidget(self.chk_show_diag)
        ll.addLayout(cap_row)

        filter_form = QFormLayout()
        self.cmb_filter_cat = QComboBox()
        self.cmb_filter_cat.currentIndexChanged.connect(lambda *_: self._refresh_file_list())
        self.cmb_filter_tag = QComboBox()
        self.cmb_filter_tag.currentIndexChanged.connect(lambda *_: self._refresh_file_list())
        self.ed_filter = QLineEdit()
        self.ed_filter.setPlaceholderText(tr("filter_placeholder"))
        self.ed_filter.textChanged.connect(lambda *_: self._refresh_file_list())
        filter_form.addRow(tr("filter_category"), self.cmb_filter_cat)
        filter_form.addRow(tr("filter_tag"), self.cmb_filter_tag)
        filter_form.addRow(tr("filter_text"), self.ed_filter)
        ll.addLayout(filter_form)
        self._refresh_filter_controls()

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.currentRowChanged.connect(self._select_chat)
        ll.addWidget(self.file_list)
        b_clear = QPushButton(tr("clear_list"))
        b_clear.clicked.connect(self.clear_list)
        ll.addWidget(b_clear)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        self.info_label = QLabel("")
        self.info_label.setObjectName("muted")
        self.info_label.setWordWrap(True)
        rl.addWidget(self.info_label)

        self.tabs = QTabWidget()

        # вкладка «Чистый вид»
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_host = QWidget()
        self.scroll_host.setObjectName("scrollHost")
        self.scroll_lay = QVBoxLayout(self.scroll_host)
        self.scroll_lay.setContentsMargins(10, 10, 10, 10)
        self.scroll_lay.setSpacing(10)
        self.scroll_lay.addStretch(1)
        self.scroll.setWidget(self.scroll_host)
        self.scroll.verticalScrollBar().valueChanged.connect(self._maybe_load_more_messages)
        self.tabs.addTab(self.scroll, tr("tab_clean"))

        # вкладка «Исходный JSON»
        raw_tab = QWidget()
        rt = QVBoxLayout(raw_tab)
        rt.setContentsMargins(6, 6, 6, 6)
        raw_bar = QHBoxLayout()
        self.b_copy_raw = QPushButton(tr("copy_source_json"))
        self.b_copy_raw.clicked.connect(self.copy_raw)
        raw_bar.addWidget(self.b_copy_raw)
        raw_bar.addStretch(1)
        rt.addLayout(raw_bar)
        self.raw_view = QPlainTextEdit()
        self.raw_view.setReadOnly(True)
        rt.addWidget(self.raw_view)
        self.tabs.addTab(raw_tab, tr("tab_raw"))

        # вкладка «Поиск»
        self.tabs.addTab(self._build_search_tab(), tr("tab_search"))

        rl.addWidget(self.tabs)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 940])
        root.addWidget(split)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

        # горячие клавиши (при пересборке UI старые экшены убираем,
        # иначе Qt получит дублирующиеся «ambiguous» шорткаты)
        for old in getattr(self, "_shortcut_actions", []):
            self.removeAction(old)
        self._shortcut_actions = []
        for seq, fn in (
            (QKeySequence.Open, self.open_files),
            (QKeySequence.ZoomIn, lambda: self.set_zoom(self.zoom + ZOOM_STEP)),
            (QKeySequence("Ctrl+="), lambda: self.set_zoom(self.zoom + ZOOM_STEP)),
            (QKeySequence.ZoomOut, lambda: self.set_zoom(self.zoom - ZOOM_STEP)),
            (QKeySequence("Ctrl+0"), lambda: self.set_zoom(100)),
        ):
            act = QAction(self)
            act.setShortcut(seq)
            act.triggered.connect(fn)
            self.addAction(act)
            self._shortcut_actions.append(act)

    def _build_search_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        row1 = QHBoxLayout()
        self.ed_query = QLineEdit()
        self.ed_query.setPlaceholderText(tr("search_placeholder"))
        self.ed_query.returnPressed.connect(self.do_search)
        row1.addWidget(self.ed_query, 1)
        b_search = QPushButton(tr("search_btn"))
        b_search.setObjectName("accent")
        b_search.clicked.connect(self.do_search)
        self._decorate_button(b_search, "search.png", 90)
        row1.addWidget(b_search)
        v.addLayout(row1)

        row_scope = QHBoxLayout()
        row_scope.addWidget(QLabel(tr("search_where")))
        self.cmb_search_where = QComboBox()
        self.cmb_search_where.addItem(tr("search_in_current"), "current")
        self.cmb_search_where.addItem(tr("search_in_loaded"), "loaded")
        self.cmb_search_where.addItem(tr("search_in_index_all"), "index_all")
        self.cmb_search_where.addItem(tr("search_in_index_txt"), "index_txt")
        self.cmb_search_where.addItem(tr("search_in_index_json"), "index_json")
        row_scope.addWidget(self.cmb_search_where, 1)
        row_scope.addWidget(QLabel(tr("search_what")))
        self.cmb_scope = QComboBox()
        self.cmb_scope.addItem(tr("search_scope_all"), "all")
        self.cmb_scope.addItem(tr("search_scope_user"), "user")
        self.cmb_scope.addItem(tr("search_scope_model"), "model")
        self.cmb_scope.addItem(tr("search_scope_thoughts"), "thoughts")
        row_scope.addWidget(self.cmb_scope)
        v.addLayout(row_scope)

        row2 = QHBoxLayout()
        b_index = QPushButton(tr("index_folder_btn"))
        b_index.clicked.connect(self.index_folder)
        row2.addWidget(b_index)
        self.lbl_index_stats = QLabel("")
        self.lbl_index_stats.setObjectName("muted")
        row2.addWidget(self.lbl_index_stats, 1)
        v.addLayout(row2)

        self.search_results = QListWidget()
        self.search_results.setWordWrap(True)
        # только itemActivated: на всех платформах срабатывает и по
        # дабл-клику, и по Enter; вместе с itemDoubleClicked открывало дважды
        self.search_results.itemActivated.connect(self._open_search_hit)
        v.addWidget(self.search_results, 1)

        hint = QLabel(tr("search_hint"))
        hint.setObjectName("muted")
        v.addWidget(hint)
        return w

    # ---------- темы / зум / язык ----------

    def apply_theme(self, rebuild_view: bool = True):
        t = THEMES[self.theme_name]
        scale = self.zoom / 100.0
        QApplication.instance().setPalette(build_palette(t))
        self.setStyleSheet(build_stylesheet(t, scale))
        f = QApplication.instance().font()
        f.setPointSizeF(BASE_FONT_PT * scale)
        QApplication.instance().setFont(f)
        self.btn_theme.setText("🌙" if self.theme_name == "dark" else "☀️")
        self._apply_window_frame_theme()
        self._responsive_topbar()
        if rebuild_view:
            self._rebuild_view()
        self._update_index_stats()


    def _apply_window_frame_theme(self):
        """Пытаемся синхронизировать системную рамку/заголовок с темой.

        На Windows 10/11 работает через DWM dark titlebar. На Linux/macOS
        это контролирует оконный менеджер/система, поэтому просто пропускаем.
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            value = ctypes.c_int(1 if self.theme_name == "dark" else 0)
            dwm = ctypes.windll.dwmapi
            # 20 — DWMWA_USE_IMMERSIVE_DARK_MODE на новых Windows,
            # 19 — старый номер атрибута.
            for attr in (20, 19):
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.settings.setValue("ui/theme", self.theme_name)
        self.apply_theme(rebuild_view=True)

    def _responsive_topbar(self):
        if not hasattr(self, "_top_buttons"):
            return
        icon_only = (self.zoom >= RESPONSIVE_ICON_ONLY_ZOOM
                     or self.width() < RESPONSIVE_ICON_ONLY_WIDTH)
        for btn in self._top_buttons:
            full = btn.property("fullText") or btn.text()
            compact = btn.property("compactText") or full[:1]
            has_icon = hasattr(btn, "icon") and not btn.icon().isNull()
            btn.setText("" if icon_only and has_icon else (compact if icon_only else full))
            btn.setToolTip(full)
            if hasattr(btn, "setToolButtonStyle"):
                btn.setToolButtonStyle(Qt.ToolButtonIconOnly if icon_only and has_icon
                                       else Qt.ToolButtonTextBesideIcon)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._responsive_topbar()

    def set_zoom(self, z: int):
        z = max(ZOOM_MIN, min(ZOOM_MAX, z))
        if z == self.zoom:
            return
        self.zoom = z
        self.settings.setValue("ui/zoom", z)
        if hasattr(self, "lbl_zoom"):
            self.lbl_zoom.setText(f"{z}%")
        # Debounce: при серии быстрых кликов применяем только последний масштаб.
        self._zoom_timer.start(90)
        self.statusBar().showMessage(f"Zoom: {z}%", 1200)
        self._responsive_topbar()

    def _apply_pending_zoom(self):
        # Важно: не пересоздаём карточки при каждом изменении масштаба.
        # Qt сам перерасчитает размеры по новому QSS/шрифту; это убирает лаги
        # на больших логах.
        self.apply_theme(rebuild_view=False)

    def _change_lang(self):
        code = self.cmb_lang.currentData()
        if code == i18n.get_lang():
            return
        i18n.set_lang(code)
        self.settings.setValue("ui/lang", code)
        self._rebuild_all_ui()

    def _rebuild_all_ui(self):
        """Полная пересборка интерфейса (смена языка)."""
        cur_row = self.file_list.currentRow()
        cur_tab = self.tabs.currentIndex()
        self._build_ui()
        for chat in self.chats:
            self._add_list_item(chat)
        if 0 <= cur_row < self.file_list.count():
            self.file_list.setCurrentRow(cur_row)
        self.tabs.setCurrentIndex(cur_tab)
        self.apply_theme()
        self.statusBar().showMessage(tr("status_hint"))

    def _toggle_md(self, on):
        self.render_md = on
        self.settings.setValue("ui/render_md", "true" if on else "false")
        self._rebuild_view()

    def _toggle_thoughts(self, on):
        self.show_thoughts = on
        self.settings.setValue("ui/show_thoughts", "true" if on else "false")
        self._rebuild_view()

    # ---------- drag & drop ----------

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        files = []
        for p in paths:
            pp = Path(p)
            if pp.is_dir():
                files.extend(core.scan_folder(pp))
            elif pp.is_file():
                files.append(str(pp))
        self.load_paths(files)

    # ---------- загрузка ----------

    def open_files(self):
        last = self.settings.value("ui/last_dir", str(Path.home()))
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("dlg_open_files"), last, tr("dlg_all_files"))
        if files:
            self.settings.setValue("ui/last_dir", str(Path(files[0]).parent))
            self.load_paths(files)

    def open_folder(self):
        last = self.settings.value("ui/last_dir", str(Path.home()))
        folder = QFileDialog.getExistingDirectory(
            self, tr("dlg_open_folder"), last)
        if not folder:
            return
        self.settings.setValue("ui/last_dir", folder)
        files = core.scan_folder(folder)
        if not files:
            QMessageBox.information(self, APP_NAME, tr("no_logs_in_folder"))
            return
        self.load_paths(files)

    def _format_source_badge(self, chat: core.ChatLog) -> str:
        p = Path(chat.path) if chat.path else Path("")
        ext = p.suffix.lower().lstrip(".") or tr("no_extension")
        kind = "JSON" if chat.source_format == "json" else "TXT"
        return f"{kind} · {ext}"

    def _refresh_filter_controls(self):
        if not hasattr(self, "cmb_filter_cat"):
            return
        cur_cat = self.cmb_filter_cat.currentData()
        cur_tag = self.cmb_filter_tag.currentData()
        for cmb in (self.cmb_filter_cat, self.cmb_filter_tag):
            cmb.blockSignals(True)
            cmb.clear()
        self.cmb_filter_cat.addItem(tr("all_categories"), "")
        self.cmb_filter_cat.addItem(tr("uncategorized"), "__none__")
        for c in sorted(self.categories):
            self.cmb_filter_cat.addItem(c, c)
        self.cmb_filter_tag.addItem(tr("all_tags"), "")
        tags = sorted({t for vals in self.chat_tags.values() if isinstance(vals, list) for t in vals})
        for t in tags:
            self.cmb_filter_tag.addItem("#" + t, t)
        for cmb, val in ((self.cmb_filter_cat, cur_cat), (self.cmb_filter_tag, cur_tag)):
            i = cmb.findData(val)
            cmb.setCurrentIndex(i if i >= 0 else 0)
            cmb.blockSignals(False)

    def _passes_filters(self, chat) -> bool:
        cat_filter = self.cmb_filter_cat.currentData() if hasattr(self, "cmb_filter_cat") else ""
        tag_filter = self.cmb_filter_tag.currentData() if hasattr(self, "cmb_filter_tag") else ""
        text_filter = self.ed_filter.text().strip().lower() if hasattr(self, "ed_filter") else ""
        cat = self._chat_category(chat)
        if cat_filter == "__none__" and cat:
            return False
        if cat_filter and cat_filter != "__none__" and cat != cat_filter:
            return False
        if tag_filter and tag_filter not in self._chat_tags(chat):
            return False
        if text_filter:
            hay = " ".join([chat.title, chat.path, chat.model, cat, " ".join(self._chat_tags(chat))]).lower()
            if text_filter not in hay:
                return False
        return True

    def _add_list_item(self, chat: core.ChatLog):
        cat = self._chat_category(chat)
        tags = self._chat_tags(chat)
        title = f"[{cat}] {chat.title}" if cat else chat.title
        if tags:
            title += "  " + " ".join("#" + t for t in tags[:4])
        extra = f" · {self._format_source_badge(chat)}" if self.show_extensions else ""
        item = QListWidgetItem(
            f"{title}\n   {chat.model or '—'} · "
            f"{len(chat.messages)} {tr('messages_short')}{extra}")
        item.setToolTip(chat.path)
        item.setData(Qt.UserRole, chat.path)
        self.file_list.addItem(item)

    def _refresh_file_list(self, select_path: str = None):
        if not hasattr(self, "file_list"):
            return
        cur_path = select_path or (self.current.path if self.current else None)
        self.file_list.blockSignals(True)
        self.file_list.clear()
        for chat in self.chats:
            if self._passes_filters(chat):
                self._add_list_item(chat)
        self.file_list.blockSignals(False)
        if cur_path:
            for row in range(self.file_list.count()):
                if self.file_list.item(row).data(Qt.UserRole) == cur_path:
                    self.file_list.setCurrentRow(row)
                    break
        elif self.file_list.count():
            self.file_list.setCurrentRow(0)

    def _toggle_extensions(self, on):
        self.show_extensions = on
        self.settings.setValue("ui/show_extensions", "true" if on else "false")
        self._refresh_file_list()

    def _toggle_diagnostics(self, on):
        self.show_diagnostics = on
        self.settings.setValue("ui/show_diagnostics", "true" if on else "false")
        self._rebuild_view()

    def load_paths(self, paths, select_path: str = None):
        if not paths:
            return
        loaded, errors = 0, []
        existing = {c.path for c in self.chats}
        prog = None
        if len(paths) > 10:
            prog = QProgressDialog(tr("loading"), tr("cancel"), 0,
                                   len(paths), self)
            prog.setWindowModality(Qt.WindowModal)
        for i, p in enumerate(paths):
            if prog:
                prog.setValue(i)
                if prog.wasCanceled():
                    break
            if p in existing:
                continue
            try:
                chat = core.parse_file(p, self.text_parse_options)
            except (core.ParseError, OSError, ValueError) as ex:
                errors.append(f"{Path(p).name}: {ex}")
                continue
            self.chats.append(chat)
            loaded += 1
        if prog:
            prog.setValue(len(paths))

        self._refresh_filter_controls()
        if select_path:
            self._refresh_file_list(select_path=select_path)
        elif loaded:
            self._refresh_file_list(select_path=self.chats[-1].path if self.chats else None)

        msg = tr("loaded_n", n=loaded)
        if errors:
            msg += tr("errors_n", n=len(errors))
            QMessageBox.warning(
                self, tr("not_all_loaded"),
                tr("not_logs") + "\n\n" + "\n".join(errors[:12])
                + ("\n…" if len(errors) > 12 else ""))
        self.statusBar().showMessage(msg, 6000)

    def clear_list(self):
        self.chats.clear()
        self.current = None
        self.file_list.clear()
        self.raw_view.clear()
        self.info_label.setText("")
        self._clear_cards()

    # ---------- отображение ----------

    def _select_chat(self, row):
        if row < 0 or row >= self.file_list.count():
            self.current = None
            return
        path = self.file_list.item(row).data(Qt.UserRole)
        self.current = next((c for c in self.chats if c.path == path), None)
        self._rebuild_view()

    def _clear_cards(self):
        while self.scroll_lay.count() > 1:
            it = self.scroll_lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def _rebuild_view(self):
        self._clear_cards()
        chat = self.current
        if chat is None:
            return
        t = THEMES[self.theme_name]

        info = [f"<b>{_html.escape(chat.title)}</b>"]
        cat = self._chat_category(chat)
        note = self._chat_note(chat)
        if cat:
            info.append(f"{tr('category_label')}: {_html.escape(cat)}")
        tags = self._chat_tags(chat)
        if tags:
            info.append(f"{tr('tags_label')}: " + " ".join("#" + _html.escape(t) for t in tags))
        if note:
            short_note = note.replace("\n", " ")[:160]
            info.append(f"{tr('note_label')}: {_html.escape(short_note)}")
        if self.show_diagnostics:
            diag = f"{self._format_source_badge(chat)} · {chat.path}"
            if self.chat_derived.get(chat.path):
                diag += f" · derived_from={self.chat_derived.get(chat.path)}"
            info.append(f"{tr('diagnostics_label')}: {_html.escape(diag)}")
        if chat.model:
            info.append(f"{tr('info_model')}: {_html.escape(chat.model)}")
        info.append(tr("info_msgs", n=len(chat.messages),
                       u=chat.user_count, m=chat.model_count))
        if chat.thought_count:
            info.append(tr("info_thoughts", n=chat.thought_count))
        if chat.warnings:
            info.append(f"⚠ {'; '.join(chat.warnings)}")
        self.info_label.setText(" · ".join(info))

        if chat.system_instruction:
            box = QFrame()
            box.setObjectName("msgCard")
            box.setAttribute(Qt.WA_StyledBackground, True)
            bl = QVBoxLayout(box)
            bl.setContentsMargins(14, 10, 14, 12)
            cap = QLabel(f"<b>{tr('system_instruction')}</b>")
            cap.setObjectName("muted")
            bl.addWidget(cap)
            lab = QLabel(chat.system_instruction)
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lab.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
            bl.addWidget(lab)
            self.scroll_lay.insertWidget(self.scroll_lay.count() - 1, box)

        self._render_generation += 1
        self._render_next = 0
        self._append_message_batch(self._render_generation)

        if chat.source_format == "json":
            self.tabs.setTabText(1, tr("source_json"))
            self.b_copy_raw.setText(tr("copy_source_json"))
            try:
                self.raw_view.setPlainText(
                    json.dumps(chat.raw, ensure_ascii=False, indent=2))
            except (TypeError, ValueError):
                self.raw_view.setPlainText("<JSON?>")
        else:
            self.tabs.setTabText(1, tr("source_text"))
            self.b_copy_raw.setText(tr("copy_source_text"))
            self.raw_view.setPlainText(chat.raw_text or "")

        QTimer.singleShot(0, lambda:
                          self.scroll.verticalScrollBar().setValue(0))


    def _append_message_batch(self, generation: int):
        """Ленивая отрисовка карточек батчами.

        Это не полноценная виртуализация, но длинные логи перестают блокировать
        окно на секунды: первый экран появляется быстро, остальные карточки
        дорисовываются небольшими порциями через event loop.
        """
        if generation != self._render_generation or self.current is None:
            return
        chat = self.current
        t = THEMES[self.theme_name]
        status = lambda s: self.statusBar().showMessage(s, 4000)
        start = self._render_next
        end = min(start + VIEW_BATCH, len(chat.messages))
        for idx in range(start, end):
            msg = chat.messages[idx]
            card = MessageCard(msg, idx + 1, t, self.render_md,
                               self.show_thoughts, status,
                               model_name=chat.model)
            self.scroll_lay.insertWidget(self.scroll_lay.count() - 1, card)
        self._render_next = end

    def _maybe_load_more_messages(self):
        if self.current is None:
            return
        sb = self.scroll.verticalScrollBar()
        if sb.maximum() - sb.value() < 900 and self._render_next < len(self.current.messages):
            self._append_message_batch(self._render_generation)

    # ---------- копирование ----------

    def _need_chat(self) -> bool:
        if self.current is None:
            QMessageBox.information(self, APP_NAME, tr("open_first"))
            return False
        return True


    def open_copy_settings(self):
        dlg = CopySettingsDialog(self, self.settings)
        if dlg.exec() == QDialog.Accepted:
            dlg.save()
            self.statusBar().showMessage(tr("copy_settings_saved"), 4000)

    def _copy_separator(self) -> str:
        mode = self.settings.value("copy/separator", "blank")
        if mode == "double":
            return "\n\n\n"
        if mode == "long":
            return "\n\n" + "—" * 70 + "\n\n"
        if mode == "custom":
            raw = self.settings.value("copy/custom_separator", "\n---\n")
            return raw.replace("\\n", "\n")
        return "\n\n"

    def _clean_copy_text(self, chat: core.ChatLog, which: str) -> str:
        parts = []
        for msg in chat.messages:
            if which == core.COPY_PROMPTS and not msg.is_user:
                continue
            if which == core.COPY_ANSWERS and msg.is_user:
                continue
            if which == core.COPY_THOUGHTS:
                if msg.has_thoughts:
                    parts.extend(t.strip() for t in msg.thoughts if t.strip())
                continue
            text = msg.text.strip()
            if text:
                parts.append(text)
        return self._copy_separator().join(parts).strip() + ("\n" if parts else "")

    def copy_chat(self, which):
        if not self._need_chat():
            return
        include_service = self.settings.value("copy/include_service", "true") == "true"
        if not include_service:
            text = self._clean_copy_text(self.current, which)
            QGuiApplication.clipboard().setText(text)
            names = {core.COPY_ALL: tr("copy_all"),
                     core.COPY_PROMPTS: tr("copy_prompts"),
                     core.COPY_ANSWERS: tr("copy_answers"),
                     core.COPY_THOUGHTS: tr("copy_thoughts")}
            self.statusBar().showMessage(
                tr("copied_n", what=names[which], n=len(text)), 5000)
            return
        opts = core.ExportOptions(
            fmt="txt", metadata=False, system_instruction=False,
            auto_model_label=True,
            user_label=tr("user"), model_label=tr("model"),
            thoughts=core.THOUGHTS_INCLUDE if (
                self.show_thoughts and which != core.COPY_PROMPTS)
            else core.THOUGHTS_EXCLUDE,
        )
        text = core.chat_to_clipboard_text(self.current, which, opts)
        QGuiApplication.clipboard().setText(text)
        names = {core.COPY_ALL: tr("copy_all"),
                 core.COPY_PROMPTS: tr("copy_prompts"),
                 core.COPY_ANSWERS: tr("copy_answers"),
                 core.COPY_THOUGHTS: tr("copy_thoughts")}
        self.statusBar().showMessage(
            tr("copied_n", what=names[which], n=len(text)), 5000)

    def copy_raw(self):
        if not self._need_chat():
            return
        QGuiApplication.clipboard().setText(self.raw_view.toPlainText())
        self.statusBar().showMessage(tr("source_copied"), 4000)

    # ---------- экспорт ----------

    def export_current(self):
        if not self._need_chat():
            return
        self._export([self.current])

    def export_all(self):
        if not self.chats:
            QMessageBox.information(self, APP_NAME, tr("list_empty"))
            return
        self._export(list(self.chats))

    def _export(self, chats):
        dlg = ExportDialog(self, self.settings, batch_count=len(chats))
        if dlg.exec() != QDialog.Accepted:
            return
        opts = dlg.options()
        last = self.settings.value("ui/export_dir",
                                   self.settings.value("ui/last_dir",
                                                       str(Path.home())))
        out_dir = QFileDialog.getExistingDirectory(
            self, tr("dlg_save_dir"), last)
        if not out_dir:
            return
        self.settings.setValue("ui/export_dir", out_dir)

        created, errors = [], []
        for chat in chats:
            try:
                created.extend(core.export_to_files(chat, opts, out_dir))
            except (OSError, ValueError) as ex:
                errors.append(f"{chat.title}: {ex}")

        msg = tr("export_result", n=len(created), dir=out_dir)
        if errors:
            msg += "\n\n" + tr("export_errors") + "\n" + "\n".join(errors[:10])
        QMessageBox.information(self, tr("export_done"), msg)
        self.statusBar().showMessage(tr("exported_n", n=len(created)), 6000)

    # ---------- поиск ----------

    def _get_index(self):
        if self._index is None:
            import indexer
            self._index = indexer.SearchIndex()
        return self._index

    def _update_index_stats(self):
        if not hasattr(self, "lbl_index_stats"):
            return
        if self._index is None:
            self.lbl_index_stats.setText("")
            return
        try:
            st = self._index.stats()
            self.lbl_index_stats.setText(
                tr("index_stats", files=st["files"], msgs=st["messages"],
                   mb=st["db_size"] / 1e6))
        except Exception:
            self.lbl_index_stats.setText("")

    def index_folder(self):
        last = self.settings.value("ui/index_dir",
                                   self.settings.value("ui/last_dir",
                                                       str(Path.home())))
        folder = QFileDialog.getExistingDirectory(
            self, tr("dlg_open_folder"), last)
        if not folder:
            return
        self.settings.setValue("ui/index_dir", folder)

        prog = QProgressDialog(tr("indexing"), tr("cancel"), 0, 100, self)
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)

        cancelled = {"flag": False}

        def cb(done, total, path):
            if total:
                prog.setMaximum(total)
                prog.setValue(done)
                prog.setLabelText(f"{tr('indexing')}\n{Path(path).name}"
                                  if path else tr("indexing"))
            QApplication.processEvents()
            if prog.wasCanceled():
                cancelled["flag"] = True
                raise KeyboardInterrupt

        idx = self._get_index()
        try:
            stats = idx.index_paths([folder], progress=cb)
            prog.setValue(prog.maximum())
            QMessageBox.information(
                self, tr("index_done"),
                tr("index_done") + ":\n" + stats.summary()
                + (("\n\n" + "\n".join(stats.errors[:8])) if stats.errors else ""))
        except KeyboardInterrupt:
            pass
        finally:
            prog.close()
        self._update_index_stats()

    def _plain_snippet(self, text: str, q: str, limit: int = 220) -> str:
        one = re.sub(r"\s+", " ", text).strip()
        if not one:
            return ""
        pos = one.lower().find(q.lower())
        if pos < 0:
            return one[:limit] + ("…" if len(one) > limit else "")
        a = max(0, pos - 70)
        b = min(len(one), pos + len(q) + 140)
        return ("…" if a else "") + one[a:b] + ("…" if b < len(one) else "")

    def _local_search_hits(self, q: str, chats: list, scope: str) -> list:
        hits = []
        ql = q.lower()
        for chat in chats:
            for num, msg in enumerate(chat.messages, 1):
                parts = []
                if scope in ("all", "user") and msg.is_user and msg.text:
                    parts.append((msg.text, "👤", "user"))
                if scope in ("all", "model") and not msg.is_user and msg.text:
                    parts.append((msg.text, "🤖", "model"))
                if scope in ("all", "thoughts") and msg.has_thoughts:
                    parts.extend((t, "💭", "thoughts") for t in msg.thoughts)
                for text, icon, role in parts:
                    if ql in text.lower():
                        hits.append((chat, num, icon, role, self._plain_snippet(text, q)))
                        break
        return hits

    def do_search(self):
        q = self.ed_query.text().strip()
        self.search_results.clear()
        if not q:
            return
        where = self.cmb_search_where.currentData()
        scope = self.cmb_scope.currentData()

        # Быстрый поиск без индекса — по уже открытым данным.
        if where in ("current", "loaded"):
            if where == "current":
                if not self._need_chat():
                    return
                chats = [self.current]
            else:
                chats = list(self.chats)
            hits = self._local_search_hits(q, chats, scope)
            if not hits:
                it = QListWidgetItem(tr("search_no_results"))
                it.setFlags(Qt.NoItemFlags)
                self.search_results.addItem(it)
                return
            for chat, num, icon, role, snip in hits[:300]:
                it = QListWidgetItem(
                    f"{icon} {chat.title}  ·  {self._format_source_badge(chat)}  ·  #{num}\n{snip}")
                it.setToolTip(chat.path)
                it.setData(Qt.UserRole, (chat.path, "log"))
                self.search_results.addItem(it)
            self.statusBar().showMessage(tr("search_results_n", n=len(hits)), 5000)
            return

        # Поиск по папке — через индекс.
        if self._index is None:
            it = QListWidgetItem(tr("search_need_index"))
            it.setFlags(Qt.NoItemFlags)
            self.search_results.addItem(it)
            return

        role, thoughts, kind = None, None, None
        if scope == "user":
            role, thoughts = "user", False
        elif scope == "model":
            role, thoughts = "model", False
        elif scope == "thoughts":
            thoughts = True
        if where == "index_txt":
            kind = "txt"
        elif where == "index_json":
            kind = "log"
        try:
            hits = self._index.search(q, role=role, thoughts=thoughts,
                                      kind=kind, limit=300)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, str(ex))
            return
        if not hits:
            it = QListWidgetItem(tr("search_no_results"))
            it.setFlags(Qt.NoItemFlags)
            self.search_results.addItem(it)
            return
        for h in hits:
            if h.kind == "txt":
                icon = "📄"
            else:
                icon = ("💭" if h.is_thought
                        else ("👤" if h.role == "user" else "🤖"))
            it = QListWidgetItem(
                f"{icon} {h.title}  ·  {h.model or '—'}  ·  #{h.msg_num}\n"
                f"{h.snippet}")
            it.setToolTip(h.path)
            it.setData(Qt.UserRole, (h.path, h.kind))
            self.search_results.addItem(it)
        self.statusBar().showMessage(
            tr("search_results_n", n=len(hits)), 5000)

    def _open_search_hit(self, item):
        data = item.data(Qt.UserRole)
        if not data:
            return
        path, kind = data if isinstance(data, tuple) else (data, "log")
        if not Path(path).exists():
            QMessageBox.warning(self, APP_NAME, f"404: {path}")
            return
        if kind == "txt":
            # текстовый файл — открываем системным приложением
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            return
        self.load_paths([path], select_path=path)
        self.tabs.setCurrentIndex(0)


def main():
    app = QApplication(sys.argv)
    # Fusion оставляем для стабильного вида самого приложения, но проводник
    # файлов/папок теперь снова нативный: так привычнее обычным пользователям.
    app.setStyle("Fusion")
    ic = load_icon("app_logo.png")
    if not ic.isNull():
        app.setWindowIcon(ic)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG)
    f = app.font()
    f.setPointSizeF(BASE_FONT_PT)
    app.setFont(f)
    win = MainWindow()
    win.show()
    args = [a for a in sys.argv[1:] if Path(a).exists()]
    files = []
    for a in args:
        p = Path(a)
        files.extend(core.scan_folder(p) if p.is_dir() else [str(p)])
    if files:
        win.load_paths(files)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
