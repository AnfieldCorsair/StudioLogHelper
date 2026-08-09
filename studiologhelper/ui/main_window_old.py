# -*- coding: utf-8 -*-
"""Главное окно PyQt6 — рефактор с воркерами, кроссплатформенностью."""

from __future__ import annotations

import json
import re
import sys
import html as _html
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QSettings, QTimer, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QAction, QGuiApplication, QKeySequence, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QToolButton, QMenu,
    QFileDialog, QMessageBox, QTabWidget, QPlainTextEdit, QScrollArea,
    QFrame, QDialog, QDialogButtonBox, QCheckBox, QComboBox, QGroupBox,
    QFormLayout, QLineEdit, QStatusBar, QSizePolicy, QProgressDialog,
    QTextEdit, QInputDialog, QAbstractItemView, QSpinBox,
)

from ..core.parsers.base import TextParseOptions
from ..core.models import ChatLog
from ..core.exporters.base import ExportOptions, CONTENT_ALL, CONTENT_ANSWERS, CONTENT_PROMPTS, CONTENT_THOUGHTS, THOUGHTS_INCLUDE, THOUGHTS_EXCLUDE
from ..core.exporters.manager import export_to_files
from ..core.project import Project, ProjectFile
from ..i18n.translator import Translator, LANGS, DEFAULT_LANG
from ..indexer import SearchIndex
from ..utils.paths import get_app_data_dir, reveal_in_file_manager
from .themes import THEMES, build_stylesheet_cached, build_palette
from .widgets.message_card import MessageCard, load_icon, load_pixmap
from .dialogs import ExportDialog, TextSeparatorsDialog, CopySettingsDialog, BatchExportDialog, CollapseSettingsDialog

APP_NAME = "StudioLogHelper"
ORG = "ArenaTools"

ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 70, 200, 10
BASE_FONT_PT = 10.0
RESPONSIVE_ICON_ONLY_ZOOM = 150
RESPONSIVE_ICON_ONLY_WIDTH = 980
VIEW_BATCH = 25
LONG_MESSAGE_PREVIEW_CHARS = 5000
RAW_PREVIEW_LIMIT = 1_500_000

ASSET_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons"


def strip_leading_emoji(text: str) -> str:
    return re.sub(r"^[^\wА-Яа-яЁё]+\s*", "", text, count=1)


# --- Worker thread для парсинга файлов без фриза UI ---
class ParseWorker(QThread):
    fileDone = pyqtSignal(object)  # ChatLog
    fileError = pyqtSignal(str, str)  # path, error
    allDone = pyqtSignal()

    def __init__(self, paths, text_options):
        super().__init__()
        self.paths = paths
        self.text_options = text_options
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        from ..core.parsers.parser import parse_file
        from ..core.exceptions import ParseError

        for p in self.paths:
            if self._abort:
                break
            try:
                chat = parse_file(p, self.text_options)
                self.fileDone.emit(chat)
            except (ParseError, OSError, ValueError) as ex:
                self.fileError.emit(p, str(ex))
        self.allDone.emit()


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
        self.translator = Translator(lang=self.settings.value("ui/lang", DEFAULT_LANG))

        self.theme_name = self.settings.value("ui/theme", "dark")
        self.render_md = self.settings.value("ui/render_md", "true") == "true"
        self.show_thoughts = self.settings.value("ui/show_thoughts", "true") == "true"
        self.show_extensions = self.settings.value("ui/show_extensions", "false") == "true"
        self.show_diagnostics = self.settings.value("ui/show_diagnostics", "false") == "true"
        self.auto_collapse_long = self.settings.value("ui/auto_collapse_long", "true") == "true"
        try:
            self.collapse_preview_chars = int(self.settings.value("ui/collapse_preview_chars", LONG_MESSAGE_PREVIEW_CHARS))
        except (TypeError, ValueError):
            self.collapse_preview_chars = LONG_MESSAGE_PREVIEW_CHARS
        self.collapse_preview_chars = max(800, min(50000, self.collapse_preview_chars))
        try:
            self.zoom = int(self.settings.value("ui/zoom", 100))
        except (TypeError, ValueError):
            self.zoom = 100
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom))
        self.text_parse_options = self._load_text_parse_options()

        self.chats: list[ChatLog] = []
        self.current: ChatLog | None = None
        self.chat_categories: dict = self._load_chat_categories()
        self.chat_notes: dict = self._load_chat_notes()
        self.chat_tags: dict = self._load_chat_tags()
        self.chat_derived: dict = self._load_chat_derived()
        self.categories: set = set(v for v in self.chat_categories.values() if v)
        self.project_name = self.settings.value("org/project_name", "")
        self.project_path = self.settings.value("org/project_path", "")
        self.recent_projects = self._load_recent_projects()
        self._index = None
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.timeout.connect(self._apply_pending_zoom)
        self._render_generation = 0
        self._render_next = 0
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.timeout.connect(self._rebuild_view)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave_project)
        self._autosave_timer.start(30000)
        self._parse_worker: ParseWorker | None = None

        self._build_ui()
        self.apply_theme()
        self.statusBar().showMessage(self.tr("status_hint"))

    def tr(self, key, **kwargs):
        return self.translator.tr(key, **kwargs)

    # ---------- settings helpers ----------
    def _load_text_parse_options(self) -> TextParseOptions:
        def split_saved(v):
            return [x.strip() for x in str(v or "").splitlines() if x.strip()]
        return TextParseOptions(
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
        self.settings.setValue("org/chat_categories", json.dumps(self.chat_categories, ensure_ascii=False))

    def _load_chat_notes(self) -> dict:
        try:
            data = json.loads(self.settings.value("org/chat_notes", "{}"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_chat_notes(self):
        self.settings.setValue("org/chat_notes", json.dumps(self.chat_notes, ensure_ascii=False))

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
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        if min_width:
            btn.setMinimumWidth(min_width)
        btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    # ---------- project ----------
    def new_project(self):
        name, ok = QInputDialog.getText(self, APP_NAME, self.tr("project_name"), text=self.project_name or "StudioLogHelper project")
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
        self.statusBar().showMessage(self.tr("project_created", name=name), 5000)

    def _project_doc(self) -> dict:
        files = []
        known = {c.path: c for c in self.chats}
        for path in sorted(set(known) | set(self.chat_categories) | set(self.chat_notes) | set(self.chat_tags) | set(self.chat_derived)):
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
            "schema": "studiologhelper.project.v2",
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
        path, _ = QFileDialog.getSaveFileName(self, self.tr("project_save"), last, "StudioLogHelper Project (*.slh.json);;JSON (*.json)")
        if not path:
            return
        if not path.endswith(".json"):
            path += ".slh.json"
        self._write_project(path)
        self.statusBar().showMessage(self.tr("project_saved", path=path), 6000)

    def _autosave_project(self):
        if not self.project_path:
            return
        try:
            self._write_project(self.project_path)
        except OSError:
            return

    def closeEvent(self, e):
        self._autosave_project()
        if self._parse_worker and self._parse_worker.isRunning():
            self._parse_worker.abort()
            self._parse_worker.wait(1000)
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
        self.statusBar().showMessage(self.tr("project_loaded", path=path), 6000)

    def open_project(self):
        last = self.project_path or self.settings.value("ui/last_dir", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(self, self.tr("project_open"), last, "StudioLogHelper Project (*.slh.json *.json);;All files (*)")
        if not path:
            return
        self.open_project_path(path)

    def set_note_current(self):
        if not self._need_chat():
            return
        note, ok = QInputDialog.getMultiLineText(self, APP_NAME, self.tr("project_note"), self._chat_note(self.current))
        if not ok:
            return
        note = note.strip()
        if note:
            self.chat_notes[self.current.path] = note
        else:
            self.chat_notes.pop(self.current.path, None)
        self._save_chat_notes()
        self._rebuild_view()
        self.statusBar().showMessage(self.tr("note_saved"), 4000)

    def reveal_current_file(self):
        if not self._need_chat():
            return
        p = Path(self.current.path)
        if not p.exists():
            QMessageBox.information(self, APP_NAME, self.tr("reveal_no_file"))
            return
        ok = reveal_in_file_manager(p)
        if not ok:
            # fallback Qt
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))

    def set_tags_current(self):
        if not self._need_chat():
            return
        current = ", ".join(self._chat_tags(self.current))
        raw, ok = QInputDialog.getText(self, APP_NAME, self.tr("tags_prompt"), text=current)
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
        self.statusBar().showMessage(self.tr("tags_saved"), 4000)

    def _selected_chats(self) -> list:
        selected = []
        for it in self.file_list.selectedItems():
            path = it.data(Qt.ItemDataRole.UserRole)
            for c in self.chats:
                if c.path == path:
                    selected.append(c)
                    break
        return selected

    def create_category(self):
        name, ok = QInputDialog.getText(self, APP_NAME, self.tr("category_name"))
        name = name.strip()
        if not ok or not name:
            return
        self.categories.add(name)
        self._refresh_filter_controls()
        self.statusBar().showMessage(self.tr("category_created", name=name), 4000)

    def assign_category_current(self):
        if not self._need_chat():
            return
        items = sorted(self.categories) or [self.tr("uncategorized")]
        name, ok = QInputDialog.getItem(self, APP_NAME, self.tr("category_name"), items, 0, True)
        name = name.strip()
        if not ok or not name:
            return
        self.categories.add(name)
        self.chat_categories[self.current.path] = name
        self._save_chat_categories()
        self._refresh_filter_controls()
        self._refresh_file_list(select_path=self.current.path)
        self.statusBar().showMessage(self.tr("category_assigned", name=name), 4000)

    def batch_export_set(self):
        selected = self._selected_chats()
        if not self.chats:
            QMessageBox.information(self, APP_NAME, self.tr("batch_no_files"))
            return
        bd = BatchExportDialog(self, self.settings, len(selected), len(self.chats), self.categories, self.tr)
        if bd.exec() != QDialog.DialogCode.Accepted:
            return
        bopts = bd.result_options()
        chats = selected if bopts["source"] == "selected" and selected else list(self.chats)
        if not chats:
            QMessageBox.information(self, APP_NAME, self.tr("batch_no_files"))
            return
        dlg = ExportDialog(self, self.settings, self.tr, batch_count=len(chats))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dlg.options()
        last = self.settings.value("ui/export_dir", self.settings.value("ui/last_dir", str(Path.home())))
        out_dir = QFileDialog.getExistingDirectory(self, self.tr("dlg_save_dir"), last)
        if not out_dir:
            return
        self.settings.setValue("ui/export_dir", out_dir)
        created, errors = [], []
        source_by_out = {}
        for chat in chats:
            try:
                paths = export_to_files(chat, opts, out_dir)
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
        msg = self.tr("batch_done", n=len(created), dir=out_dir)
        if errors:
            msg += "\n\n" + self.tr("export_errors") + "\n" + "\n".join(errors[:10])
        QMessageBox.information(self, self.tr("export_done"), msg)
        self._autosave_project()

    def create_text_log(self):
        last = self.settings.value("ui/last_dir", str(Path.home()))
        name, ok = QInputDialog.getText(self, APP_NAME, self.tr("file_name"), text="new_chat.txt")
        name = name.strip()
        if not ok or not name:
            return
        if not Path(name).suffix:
            name += ".txt"
        folder = QFileDialog.getExistingDirectory(self, self.tr("dlg_save_dir"), last)
        if not folder:
            return
        p = Path(folder) / Path(name).name
        if p.exists():
            QMessageBox.warning(self, APP_NAME, f"File exists: {p}")
            return
        clip = QGuiApplication.clipboard().text().strip()
        if clip:
            content = "User:\n[добавьте запрос]\n\nModel:\n" + clip + "\n"
        else:
            content = "User:\n[сюда запрос]\n\nModel:\n[сюда ответ]\n"
        p.write_text(content, encoding="utf-8")
        self.settings.setValue("ui/last_dir", folder)
        self.statusBar().showMessage(self.tr("text_log_created", path=str(p)), 5000)
        self.load_paths([str(p)], select_path=str(p))

    def open_text_separators(self):
        dlg = TextSeparatorsDialog(self, self.settings, self.tr)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.text_parse_options = dlg.options()
            self.statusBar().showMessage(self.tr("sep_saved"), 4000)

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(6)
        b_open = QPushButton(self.tr("open_files"))
        b_open.clicked.connect(self.open_files)
        self._decorate_button(b_open, "search.png", 150)
        b_folder = QPushButton(self.tr("open_folder"))
        b_folder.clicked.connect(self.open_folder)
        self._decorate_button(b_folder, "search.png", 155)
        top.addWidget(b_open)
        top.addWidget(b_folder)

        self.btn_copy = QToolButton()
        self.btn_copy.setText(self.tr("copy_menu"))
        self.btn_copy.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        m = QMenu(self.btn_copy)
        from ..core.models import COPY_ALL, COPY_PROMPTS, COPY_ANSWERS, COPY_THOUGHTS
        m.addAction(self.tr("copy_all"), lambda: self.copy_chat(COPY_ALL))
        m.addAction(self.tr("copy_prompts"), lambda: self.copy_chat(COPY_PROMPTS))
        m.addAction(self.tr("copy_answers"), lambda: self.copy_chat(COPY_ANSWERS))
        m.addAction(self.tr("copy_thoughts"), lambda: self.copy_chat(COPY_THOUGHTS))
        m.addSeparator()
        m.addAction(self.tr("copy_settings"), self.open_copy_settings)
        self.btn_copy.setMenu(m)
        self._decorate_button(self.btn_copy, "export.png", 130)
        top.addWidget(self.btn_copy)

        self.btn_export = QPushButton(self.tr("export_current"))
        self.btn_export.setObjectName("accent")
        self.btn_export.clicked.connect(self.export_current)
        self._decorate_button(self.btn_export, "export.png", 125)
        self.btn_export_all = QPushButton(self.tr("export_all"))
        self.btn_export_all.clicked.connect(self.export_all)
        self._decorate_button(self.btn_export_all, "export.png", 190)
        top.addWidget(self.btn_export)
        top.addWidget(self.btn_export_all)

        b_sep = QPushButton(self.tr("sep_button"))
        b_sep.clicked.connect(self.open_text_separators)
        self._decorate_button(b_sep, "search.png", 190)
        top.addWidget(b_sep)

        self.btn_org = QToolButton()
        self.btn_org.setText(self.tr("organize_button"))
        self.btn_org.setToolTip(self.tr("organize_tip"))
        self.btn_org.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        om = QMenu(self.btn_org)
        om.addAction(self.tr("project_new"), self.new_project)
        om.addAction(self.tr("project_open"), self.open_project)
        recent = om.addMenu(self.tr("recent_projects"))
        if self.recent_projects:
            for rp in self.recent_projects[:8]:
                recent.addAction(Path(rp).name, lambda p=rp: self.open_project_path(p))
        else:
            a = recent.addAction("—")
            a.setEnabled(False)
        om.addAction(self.tr("project_save"), self.save_project)
        om.addSeparator()
        om.addAction(self.tr("batch_export_set"), self.batch_export_set)
        om.addSeparator()
        om.addAction(self.tr("new_category"), self.create_category)
        om.addAction(self.tr("assign_category"), self.assign_category_current)
        om.addAction(self.tr("set_tags_current"), self.set_tags_current)
        om.addAction(self.tr("project_note_current"), self.set_note_current)
        om.addAction(self.tr("reveal_current_file"), self.reveal_current_file)
        om.addSeparator()
        om.addAction(self.tr("new_text_log"), self.create_text_log)
        self.btn_org.setMenu(om)
        self._decorate_button(self.btn_org, "export.png", 210)
        top.addWidget(self.btn_org)

        top.addStretch(1)
        root.addLayout(top)

        top_opts = QHBoxLayout()
        top_opts.setSpacing(8)
        top_opts.addStretch(1)

        self.chk_view_md = QCheckBox(self.tr("view_markdown"))
        self.chk_view_md.setChecked(self.render_md)
        self.chk_view_md.toggled.connect(self._toggle_md)
        self.chk_view_th = QCheckBox(self.tr("view_thoughts"))
        self.chk_view_th.setChecked(self.show_thoughts)
        self.chk_view_th.toggled.connect(self._toggle_thoughts)
        top_opts.addWidget(self.chk_view_md)
        top_opts.addWidget(self.chk_view_th)

        self.btn_collapse_long = QToolButton()
        self.btn_collapse_long.setText(self.tr("collapse_all_long"))
        self.btn_collapse_long.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.btn_collapse_long.clicked.connect(lambda: self.set_all_long_collapsed(True))
        cm = QMenu(self.btn_collapse_long)
        cm.addAction(self.tr("collapse_all_long"), lambda: self.set_all_long_collapsed(True))
        cm.addAction(self.tr("expand_all_long"), lambda: self.set_all_long_collapsed(False))
        cm.addSeparator()
        cm.addAction(self.tr("collapse_settings"), self.open_collapse_settings)
        self.btn_collapse_long.setMenu(cm)
        top_opts.addWidget(self.btn_collapse_long)

        b_zout = QPushButton("A−")
        b_zout.setFixedWidth(40)
        b_zout.setToolTip(self.tr("zoom_out_tip"))
        b_zout.clicked.connect(lambda: self.set_zoom(self.zoom - ZOOM_STEP))
        b_zin = QPushButton("A+")
        b_zin.setFixedWidth(40)
        b_zin.setToolTip(self.tr("zoom_in_tip"))
        b_zin.clicked.connect(lambda: self.set_zoom(self.zoom + ZOOM_STEP))
        self.lbl_zoom = QLabel(f"{self.zoom}%")
        self.lbl_zoom.setObjectName("muted")
        self.lbl_zoom.setMinimumWidth(48)
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_opts.addWidget(b_zout)
        top_opts.addWidget(self.lbl_zoom)
        top_opts.addWidget(b_zin)

        self.cmb_lang = QComboBox()
        for code, name in LANGS.items():
            self.cmb_lang.addItem(name, code)
        self.cmb_lang.setCurrentIndex(max(0, self.cmb_lang.findData(self.translator.get_lang())))
        self.cmb_lang.setToolTip(self.tr("lang_tip"))
        self.cmb_lang.currentIndexChanged.connect(self._change_lang)
        top_opts.addWidget(self.cmb_lang)

        self.btn_theme = QPushButton("🌙" if self.theme_name == "dark" else "☀️")
        self.btn_theme.setFixedWidth(44)
        self.btn_theme.setToolTip(self.tr("theme_tip"))
        self.btn_theme.clicked.connect(self.toggle_theme)
        top_opts.addWidget(self.btn_theme)
        root.addLayout(top_opts)
        self._top_buttons = [b_open, b_folder, self.btn_copy, self.btn_export, self.btn_export_all, b_sep, self.btn_org]

        split = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        cap_row = QHBoxLayout()
        cap = QLabel(self.tr("loaded_logs"))
        cap.setObjectName("muted")
        cap_row.addWidget(cap, 1)
        self.chk_show_ext = QCheckBox(self.tr("show_extensions"))
        self.chk_show_ext.setToolTip(self.tr("show_extensions_tip"))
        self.chk_show_ext.setChecked(self.show_extensions)
        self.chk_show_ext.toggled.connect(self._toggle_extensions)
        cap_row.addWidget(self.chk_show_ext)
        self.chk_show_diag = QCheckBox(self.tr("show_diagnostics"))
        self.chk_show_diag.setToolTip(self.tr("show_diagnostics_tip"))
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
        self.ed_filter.setPlaceholderText(self.tr("filter_placeholder"))
        self.ed_filter.textChanged.connect(lambda *_: self._refresh_file_list())
        filter_form.addRow(self.tr("filter_category"), self.cmb_filter_cat)
        filter_form.addRow(self.tr("filter_tag"), self.cmb_filter_tag)
        filter_form.addRow(self.tr("filter_text"), self.ed_filter)
        ll.addLayout(filter_form)
        self._refresh_filter_controls()

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.currentRowChanged.connect(self._select_chat)
        ll.addWidget(self.file_list)
        b_clear = QPushButton(self.tr("clear_list"))
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

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_host = QWidget()
        self.scroll_host.setObjectName("scrollHost")
        self.scroll_lay = QVBoxLayout(self.scroll_host)
        self.scroll_lay.setContentsMargins(10, 10, 10, 10)
        self.scroll_lay.setSpacing(10)
        self.scroll_lay.addStretch(1)
        self.scroll.setWidget(self.scroll_host)
        self.scroll.verticalScrollBar().valueChanged.connect(self._maybe_load_more_messages)
        self.tabs.addTab(self.scroll, self.tr("tab_clean"))

        raw_tab = QWidget()
        rt = QVBoxLayout(raw_tab)
        rt.setContentsMargins(6, 6, 6, 6)
        raw_bar = QHBoxLayout()
        self.b_copy_raw = QPushButton(self.tr("copy_source_json"))
        self.b_copy_raw.clicked.connect(self.copy_raw)
        raw_bar.addWidget(self.b_copy_raw)
        raw_bar.addStretch(1)
        rt.addLayout(raw_bar)
        self.raw_view = QPlainTextEdit()
        self.raw_view.setReadOnly(True)
        rt.addWidget(self.raw_view)
        self.tabs.addTab(raw_tab, self.tr("tab_raw"))

        self.tabs.addTab(self._build_search_tab(), self.tr("tab_search"))

        rl.addWidget(self.tabs)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 940])
        root.addWidget(split)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

        for old in getattr(self, "_shortcut_actions", []):
            self.removeAction(old)
        self._shortcut_actions = []
        for seq, fn in (
            (QKeySequence.StandardKey.Open, self.open_files),
            (QKeySequence.StandardKey.ZoomIn, lambda: self.set_zoom(self.zoom + ZOOM_STEP)),
            (QKeySequence("Ctrl+="), lambda: self.set_zoom(self.zoom + ZOOM_STEP)),
            (QKeySequence.StandardKey.ZoomOut, lambda: self.set_zoom(self.zoom - ZOOM_STEP)),
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
        self.ed_query.setPlaceholderText(self.tr("search_placeholder"))
        self.ed_query.returnPressed.connect(self.do_search)
        row1.addWidget(self.ed_query, 1)
        b_search = QPushButton(self.tr("search_btn"))
        b_search.setObjectName("accent")
        b_search.clicked.connect(self.do_search)
        self._decorate_button(b_search, "search.png", 90)
        row1.addWidget(b_search)
        v.addLayout(row1)

        row_scope = QHBoxLayout()
        row_scope.addWidget(QLabel(self.tr("search_where")))
        self.cmb_search_where = QComboBox()
        self.cmb_search_where.addItem(self.tr("search_in_current"), "current")
        self.cmb_search_where.addItem(self.tr("search_in_loaded"), "loaded")
        self.cmb_search_where.addItem(self.tr("search_in_index_all"), "index_all")
        self.cmb_search_where.addItem(self.tr("search_in_index_txt"), "index_txt")
        self.cmb_search_where.addItem(self.tr("search_in_index_json"), "index_json")
        row_scope.addWidget(self.cmb_search_where, 1)
        row_scope.addWidget(QLabel(self.tr("search_what")))
        self.cmb_scope = QComboBox()
        self.cmb_scope.addItem(self.tr("search_scope_all"), "all")
        self.cmb_scope.addItem(self.tr("search_scope_user"), "user")
        self.cmb_scope.addItem(self.tr("search_scope_model"), "model")
        self.cmb_scope.addItem(self.tr("search_scope_thoughts"), "thoughts")
        row_scope.addWidget(self.cmb_scope)
        v.addLayout(row_scope)

        row2 = QHBoxLayout()
        b_index = QPushButton(self.tr("index_folder_btn"))
        b_index.clicked.connect(self.index_folder)
        row2.addWidget(b_index)
        self.lbl_index_stats = QLabel("")
        self.lbl_index_stats.setObjectName("muted")
        row2.addWidget(self.lbl_index_stats, 1)
        v.addLayout(row2)

        self.search_results = QListWidget()
        self.search_results.setWordWrap(True)
        self.search_results.itemActivated.connect(self._open_search_hit)
        v.addWidget(self.search_results, 1)

        hint = QLabel(self.tr("search_hint"))
        hint.setObjectName("muted")
        v.addWidget(hint)
        return w

    # ---------- themes / zoom / lang ----------
    def apply_theme(self, rebuild_view: bool = True):
        t = THEMES[self.theme_name]
        scale = self.zoom / 100.0
        QApplication.instance().setPalette(build_palette(t))
        self.setStyleSheet(build_stylesheet_cached(self.theme_name, scale))
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
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            value = ctypes.c_int(1 if self.theme_name == "dark" else 0)
            dwm = ctypes.windll.dwmapi
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
        icon_only = (self.zoom >= RESPONSIVE_ICON_ONLY_ZOOM or self.width() < RESPONSIVE_ICON_ONLY_WIDTH)
        for btn in self._top_buttons:
            full = btn.property("fullText") or btn.text()
            compact = btn.property("compactText") or full[:1]
            has_icon = hasattr(btn, "icon") and not btn.icon().isNull()
            btn.setText("" if icon_only and has_icon else (compact if icon_only else full))
            btn.setToolTip(full)
            if hasattr(btn, "setToolButtonStyle"):
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if icon_only and has_icon else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

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
        self._zoom_timer.start(90)
        self.statusBar().showMessage(f"Zoom: {z}%", 1200)
        self._responsive_topbar()

    def _apply_pending_zoom(self):
        self.apply_theme(rebuild_view=False)

    def _change_lang(self):
        code = self.cmb_lang.currentData()
        if code == self.translator.get_lang():
            return
        self.translator.set_lang(code)
        self.settings.setValue("ui/lang", code)
        self._rebuild_all_ui()

    def _rebuild_all_ui(self):
        cur_row = self.file_list.currentRow()
        cur_tab = self.tabs.currentIndex()
        self._build_ui()
        for chat in self.chats:
            self._add_list_item(chat)
        if 0 <= cur_row < self.file_list.count():
            self.file_list.setCurrentRow(cur_row)
        self.tabs.setCurrentIndex(cur_tab)
        self.apply_theme()
        self.statusBar().showMessage(self.tr("status_hint"))

    def open_collapse_settings(self):
        dlg = CollapseSettingsDialog(self, self.settings, self.tr)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.auto_collapse_long, self.collapse_preview_chars = dlg.save()
            self.statusBar().showMessage(self.tr("collapse_saved"), 4000)
            self._schedule_rebuild_view()

    def _iter_message_cards(self):
        for i in range(self.scroll_lay.count()):
            w = self.scroll_lay.itemAt(i).widget()
            if isinstance(w, MessageCard):
                yield w

    def set_all_long_collapsed(self, collapsed: bool):
        self.auto_collapse_long = collapsed
        self.settings.setValue("ui/auto_collapse_long", "true" if collapsed else "false")
        for card in self._iter_message_cards():
            if card.is_long_card():
                card.set_collapsed(collapsed)
        self.statusBar().showMessage(self.tr("collapse_all_long" if collapsed else "expand_all_long"), 2500)

    def _schedule_rebuild_view(self, delay: int = 80):
        if hasattr(self, "_rebuild_timer"):
            self._rebuild_timer.start(delay)
        else:
            self._rebuild_view()

    def _toggle_md(self, on):
        self.render_md = on
        self.settings.setValue("ui/render_md", "true" if on else "false")
        self._schedule_rebuild_view()

    def _toggle_thoughts(self, on):
        self.show_thoughts = on
        self.settings.setValue("ui/show_thoughts", "true" if on else "false")
        self._schedule_rebuild_view()

    # ---------- drag & drop ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        files = []
        from ..core.scanner import scan_folder
        for p in paths:
            pp = Path(p)
            if pp.is_dir():
                files.extend(scan_folder(pp))
            elif pp.is_file():
                files.append(str(pp))
        self.load_paths(files)

    # ---------- загрузка ----------
    def open_files(self):
        last = self.settings.value("ui/last_dir", str(Path.home()))
        files, _ = QFileDialog.getOpenFileNames(self, self.tr("dlg_open_files"), last, self.tr("dlg_all_files"))
        if files:
            self.settings.setValue("ui/last_dir", str(Path(files[0]).parent))
            self.load_paths(files)

    def open_folder(self):
        last = self.settings.value("ui/last_dir", str(Path.home()))
        folder = QFileDialog.getExistingDirectory(self, self.tr("dlg_open_folder"), last)
        if not folder:
            return
        self.settings.setValue("ui/last_dir", folder)
        from ..core.scanner import scan_folder
        files = scan_folder(folder)
        if not files:
            QMessageBox.information(self, APP_NAME, self.tr("no_logs_in_folder"))
            return
        self.load_paths(files)

    def _format_source_badge(self, chat: ChatLog) -> str:
        p = Path(chat.path) if chat.path else Path("")
        ext = p.suffix.lower().lstrip(".") or self.tr("no_extension")
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
        self.cmb_filter_cat.addItem(self.tr("all_categories"), "")
        self.cmb_filter_cat.addItem(self.tr("uncategorized"), "__none__")
        for c in sorted(self.categories):
            self.cmb_filter_cat.addItem(c, c)
        self.cmb_filter_tag.addItem(self.tr("all_tags"), "")
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

    def _add_list_item(self, chat: ChatLog):
        cat = self._chat_category(chat)
        tags = self._chat_tags(chat)
        title = f"[{cat}] {chat.title}" if cat else chat.title
        if tags:
            title += "  " + " ".join("#" + t for t in tags[:4])
        extra = f" · {self._format_source_badge(chat)}" if self.show_extensions else ""
        item = QListWidgetItem(f"{title}\n   {chat.model or '—'} · {len(chat.messages)} {self.tr('messages_short')}{extra}")
        item.setToolTip(chat.path)
        item.setData(Qt.ItemDataRole.UserRole, chat.path)
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
                if self.file_list.item(row).data(Qt.ItemDataRole.UserRole) == cur_path:
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

        # Фильтруем уже загруженные
        existing = {c.path for c in self.chats}
        to_load = [p for p in paths if p not in existing]

        if not to_load:
            if select_path:
                self._refresh_file_list(select_path=select_path)
            return

        # Если много файлов — используем воркер, иначе синхронно для быстроты
        if len(to_load) > 15:
            self._start_parse_worker(to_load, select_path)
        else:
            self._load_paths_sync(to_load, select_path)

    def _load_paths_sync(self, paths, select_path=None):
        from ..core.parsers.parser import parse_file
        from ..core.exceptions import ParseError

        loaded, errors = 0, []
        for p in paths:
            try:
                chat = parse_file(p, self.text_parse_options)
                self.chats.append(chat)
                loaded += 1
            except (ParseError, OSError, ValueError) as ex:
                errors.append(f"{Path(p).name}: {ex}")

        self._refresh_filter_controls()
        if select_path:
            self._refresh_file_list(select_path=select_path)
        elif loaded:
            self._refresh_file_list(select_path=self.chats[-1].path if self.chats else None)

        msg = self.tr("loaded_n", n=loaded)
        if errors:
            msg += self.tr("errors_n", n=len(errors))
            QMessageBox.warning(self, self.tr("not_all_loaded"), self.tr("not_logs") + "\n\n" + "\n".join(errors[:12]) + ("\\n…" if len(errors) > 12 else ""))
        self.statusBar().showMessage(msg, 6000)

    def _start_parse_worker(self, paths, select_path):
        if self._parse_worker and self._parse_worker.isRunning():
            self._parse_worker.abort()
            self._parse_worker.wait()

        self._parse_errors = []
        self._parse_loaded = 0
        self._parse_select_path = select_path

        prog = QProgressDialog(self.tr("loading"), self.tr("cancel"), 0, len(paths), self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(300)

        self._parse_worker = ParseWorker(paths, self.text_parse_options)

        def on_file_done(chat):
            self.chats.append(chat)
            self._parse_loaded += 1
            prog.setValue(self._parse_loaded)

        def on_file_error(path, err):
            self._parse_errors.append(f"{Path(path).name}: {err}")
            prog.setValue(prog.value() + 1)

        def on_all_done():
            prog.setValue(len(paths))
            prog.close()
            self._refresh_filter_controls()
            if self._parse_select_path:
                self._refresh_file_list(select_path=self._parse_select_path)
            elif self._parse_loaded:
                self._refresh_file_list(select_path=self.chats[-1].path if self.chats else None)
            msg = self.tr("loaded_n", n=self._parse_loaded)
            if self._parse_errors:
                msg += self.tr("errors_n", n=len(self._parse_errors))
                QMessageBox.warning(self, self.tr("not_all_loaded"), self.tr("not_logs") + "\n\n" + "\n".join(self._parse_errors[:12]))
            self.statusBar().showMessage(msg, 6000)

        def on_cancel():
            if self._parse_worker:
                self._parse_worker.abort()

        prog.canceled.connect(on_cancel)
        self._parse_worker.fileDone.connect(on_file_done)
        self._parse_worker.fileError.connect(on_file_error)
        self._parse_worker.allDone.connect(on_all_done)
        self._parse_worker.start()

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
        path = self.file_list.item(row).data(Qt.ItemDataRole.UserRole)
        self.current = next((c for c in self.chats if c.path == path), None)
        self._rebuild_view()

    def _clear_cards(self):
        self._render_generation += 1
        if hasattr(self, "scroll_host"):
            self.scroll_host.setUpdatesEnabled(False)
        while self.scroll_lay.count() > 1:
            it = self.scroll_lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        if hasattr(self, "scroll_host"):
            self.scroll_host.setUpdatesEnabled(True)

    def _rebuild_view(self):
        if hasattr(self, "scroll"):
            self.scroll.setUpdatesEnabled(False)
        if hasattr(self, "raw_view"):
            self.raw_view.setUpdatesEnabled(False)
        self._clear_cards()
        chat = self.current
        if chat is None:
            if hasattr(self, "scroll"):
                self.scroll.setUpdatesEnabled(True)
            if hasattr(self, "raw_view"):
                self.raw_view.setUpdatesEnabled(True)
            return
        t = THEMES[self.theme_name]

        info = [f"<b>{_html.escape(chat.title)}</b>"]
        cat = self._chat_category(chat)
        note = self._chat_note(chat)
        if cat:
            info.append(f"{self.tr('category_label')}: {_html.escape(cat)}")
        tags = self._chat_tags(chat)
        if tags:
            info.append(f"{self.tr('tags_label')}: " + " ".join("#" + _html.escape(t) for t in tags))
        if note:
            short_note = note.replace("\n", " ")[:160]
            info.append(f"{self.tr('note_label')}: {_html.escape(short_note)}")
        if self.show_diagnostics:
            diag = f"{self._format_source_badge(chat)} · {chat.path}"
            if self.chat_derived.get(chat.path):
                diag += f" · derived_from={self.chat_derived.get(chat.path)}"
            info.append(f"{self.tr('diagnostics_label')}: {_html.escape(diag)}")
        if chat.model:
            info.append(f"{self.tr('info_model')}: {_html.escape(chat.model)}")
        info.append(self.tr("info_msgs", n=len(chat.messages), u=chat.user_count, m=chat.model_count))
        if chat.thought_count:
            info.append(self.tr("info_thoughts", n=chat.thought_count))
        if chat.warnings:
            info.append(f"⚠ {'; '.join(chat.warnings)}")
        self.info_label.setText(" · ".join(info))

        if chat.system_instruction:
            box = QFrame()
            box.setObjectName("msgCard")
            box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            bl = QVBoxLayout(box)
            bl.setContentsMargins(14, 10, 14, 12)
            cap = QLabel(f"<b>{self.tr('system_instruction')}</b>")
            cap.setObjectName("muted")
            bl.addWidget(cap)
            lab = QLabel(chat.system_instruction)
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lab.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
            bl.addWidget(lab)
            self.scroll_lay.insertWidget(self.scroll_lay.count() - 1, box)

        self._render_generation += 1
        self._render_next = 0
        self._append_message_batch(self._render_generation)

        if chat.source_format == "json":
            self.tabs.setTabText(1, self.tr("source_json"))
            self.b_copy_raw.setText(self.tr("copy_source_json"))
            try:
                import json as _json
                raw = _json.dumps(chat.raw, ensure_ascii=False, indent=2)
                if len(raw) > RAW_PREVIEW_LIMIT:
                    raw = raw[:RAW_PREVIEW_LIMIT] + self.tr("raw_preview_truncated", shown=RAW_PREVIEW_LIMIT, total=len(raw))
                self.raw_view.setPlainText(raw)
            except (TypeError, ValueError):
                self.raw_view.setPlainText("<JSON?>")
        else:
            self.tabs.setTabText(1, self.tr("source_text"))
            self.b_copy_raw.setText(self.tr("copy_source_text"))
            raw = chat.raw_text or ""
            if len(raw) > RAW_PREVIEW_LIMIT:
                raw = raw[:RAW_PREVIEW_LIMIT] + self.tr("raw_preview_truncated", shown=RAW_PREVIEW_LIMIT, total=len(raw))
            self.raw_view.setPlainText(raw)

        self.raw_view.setUpdatesEnabled(True)
        self.scroll.setUpdatesEnabled(True)
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(0))

    def _append_message_batch(self, generation: int):
        if generation != self._render_generation or self.current is None:
            return
        chat = self.current
        t = THEMES[self.theme_name]
        status = lambda s: self.statusBar().showMessage(s, 4000)
        start = self._render_next
        end = min(start + VIEW_BATCH, len(chat.messages))
        self.scroll_host.setUpdatesEnabled(False)
        for idx in range(start, end):
            msg = chat.messages[idx]
            card = MessageCard(msg, idx + 1, t, self.render_md, self.show_thoughts, status, model_name=chat.model, collapse_long=self.auto_collapse_long, preview_chars=self.collapse_preview_chars, tr_func=self.tr)
            self.scroll_lay.insertWidget(self.scroll_lay.count() - 1, card)
        self.scroll_host.setUpdatesEnabled(True)
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
            QMessageBox.information(self, APP_NAME, self.tr("open_first"))
            return False
        return True

    def open_copy_settings(self):
        dlg = CopySettingsDialog(self, self.settings, self.tr)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.save()
            self.statusBar().showMessage(self.tr("copy_settings_saved"), 4000)

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

    def _clean_copy_text(self, chat: ChatLog, which: str) -> str:
        parts = []
        for msg in chat.messages:
            if which == CONTENT_PROMPTS and not msg.is_user:
                continue
            if which == CONTENT_ANSWERS and msg.is_user:
                continue
            if which == CONTENT_THOUGHTS:
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
        from ..core.models import COPY_PROMPTS, COPY_ANSWERS, COPY_THOUGHTS, COPY_ALL

        include_service = self.settings.value("copy/include_service", "true") == "true"
        if not include_service:
            text = self._clean_copy_text(self.current, which)
            QGuiApplication.clipboard().setText(text)
            names = {COPY_ALL: self.tr("copy_all"), COPY_PROMPTS: self.tr("copy_prompts"), COPY_ANSWERS: self.tr("copy_answers"), COPY_THOUGHTS: self.tr("copy_thoughts")}
            self.statusBar().showMessage(self.tr("copied_n", what=names[which], n=len(text)), 5000)
            return
        opts = ExportOptions(fmt="txt", metadata=False, system_instruction=False, auto_model_label=True, user_label=self.tr("user"), model_label=self.tr("model"), thoughts=THOUGHTS_INCLUDE if (self.show_thoughts and which != COPY_PROMPTS) else THOUGHTS_EXCLUDE)
        from ..core.models import chat_to_clipboard_text
        text = chat_to_clipboard_text(self.current, which, opts)
        QGuiApplication.clipboard().setText(text)
        names = {COPY_ALL: self.tr("copy_all"), COPY_PROMPTS: self.tr("copy_prompts"), COPY_ANSWERS: self.tr("copy_answers"), COPY_THOUGHTS: self.tr("copy_thoughts")}
        self.statusBar().showMessage(self.tr("copied_n", what=names[which], n=len(text)), 5000)

    def copy_raw(self):
        if not self._need_chat():
            return
        if self.current.source_format == "text":
            QGuiApplication.clipboard().setText(self.current.raw_text or "")
        else:
            import json as _json
            QGuiApplication.clipboard().setText(_json.dumps(self.current.raw, ensure_ascii=False, indent=2))
        self.statusBar().showMessage(self.tr("source_copied"), 4000)

    # ---------- экспорт ----------
    def export_current(self):
        if not self._need_chat():
            return
        self._export([self.current])

    def export_all(self):
        if not self.chats:
            QMessageBox.information(self, APP_NAME, self.tr("list_empty"))
            return
        self._export(list(self.chats))

    def _export(self, chats):
        dlg = ExportDialog(self, self.settings, self.tr, batch_count=len(chats))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dlg.options()
        last = self.settings.value("ui/export_dir", self.settings.value("ui/last_dir", str(Path.home())))
        out_dir = QFileDialog.getExistingDirectory(self, self.tr("dlg_save_dir"), last)
        if not out_dir:
            return
        self.settings.setValue("ui/export_dir", out_dir)

        created, errors = [], []
        for chat in chats:
            try:
                created.extend(export_to_files(chat, opts, out_dir))
            except (OSError, ValueError) as ex:
                errors.append(f"{chat.title}: {ex}")

        msg = self.tr("export_result", n=len(created), dir=out_dir)
        if errors:
            msg += "\n\n" + self.tr("export_errors") + "\n" + "\n".join(errors[:10])
        QMessageBox.information(self, self.tr("export_done"), msg)
        self.statusBar().showMessage(self.tr("exported_n", n=len(created)), 6000)

    # ---------- поиск ----------
    def _get_index(self):
        if self._index is None:
            self._index = SearchIndex()
        return self._index

    def _update_index_stats(self):
        if not hasattr(self, "lbl_index_stats"):
            return
        if self._index is None:
            self.lbl_index_stats.setText("")
            return
        try:
            st = self._index.stats()
            self.lbl_index_stats.setText(self.tr("index_stats", files=st["files"], msgs=st["messages"], mb=st["db_size"] / 1e6))
        except Exception:
            self.lbl_index_stats.setText("")

    def index_folder(self):
        last = self.settings.value("ui/index_dir", self.settings.value("ui/last_dir", str(Path.home())))
        folder = QFileDialog.getExistingDirectory(self, self.tr("dlg_open_folder"), last)
        if not folder:
            return
        self.settings.setValue("ui/index_dir", folder)

        prog = QProgressDialog(self.tr("indexing"), self.tr("cancel"), 0, 100, self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(0)

        def cb(done, total, path):
            if total:
                prog.setMaximum(total)
                prog.setValue(done)
                prog.setLabelText(f"{self.tr('indexing')}\n{Path(path).name}" if path else self.tr("indexing"))
            QApplication.processEvents()
            if prog.wasCanceled():
                raise KeyboardInterrupt

        idx = self._get_index()
        try:
            stats = idx.index_paths([folder], progress=cb)
            prog.setValue(prog.maximum())
            QMessageBox.information(self, self.tr("index_done"), self.tr("index_done") + ":\n" + stats.summary() + (("\n\n" + "\n".join(stats.errors[:8])) if stats.errors else ""))
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

        if where in ("current", "loaded"):
            if where == "current":
                if not self._need_chat():
                    return
                chats = [self.current]
            else:
                chats = list(self.chats)
            hits = self._local_search_hits(q, chats, scope)
            if not hits:
                it = QListWidgetItem(self.tr("search_no_results"))
                it.setFlags(Qt.ItemFlag.NoItemFlags)
                self.search_results.addItem(it)
                return
            for chat, num, icon, role, snip in hits[:300]:
                it = QListWidgetItem(f"{icon} {chat.title}  ·  {self._format_source_badge(chat)}  ·  #{num}\n{snip}")
                it.setToolTip(chat.path)
                it.setData(Qt.ItemDataRole.UserRole, (chat.path, "log"))
                self.search_results.addItem(it)
            self.statusBar().showMessage(self.tr("search_results_n", n=len(hits)), 5000)
            return

        if self._index is None:
            it = QListWidgetItem(self.tr("search_need_index"))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
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
            hits = self._index.search(q, role=role, thoughts=thoughts, kind=kind, limit=300)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, str(ex))
            return
        if not hits:
            it = QListWidgetItem(self.tr("search_no_results"))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.search_results.addItem(it)
            return
        for h in hits:
            if h.kind == "txt":
                icon = "📄"
            else:
                icon = "💭" if h.is_thought else ("👤" if h.role == "user" else "🤖")
            it = QListWidgetItem(f"{icon} {h.title}  ·  {h.model or '—'}  ·  #{h.msg_num}\n{h.snippet}")
            it.setToolTip(h.path)
            it.setData(Qt.ItemDataRole.UserRole, (h.path, h.kind))
            self.search_results.addItem(it)
        self.statusBar().showMessage(self.tr("search_results_n", n=len(hits)), 5000)

    def _open_search_hit(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        path, kind = data if isinstance(data, tuple) else (data, "log")
        if not Path(path).exists():
            QMessageBox.warning(self, APP_NAME, f"404: {path}")
            return
        if kind == "txt":
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            return
        self.load_paths([path], select_path=path)
        self.tabs.setCurrentIndex(0)
