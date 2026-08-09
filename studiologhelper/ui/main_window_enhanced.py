# -*- coding: utf-8 -*-
"""MainWindow v2 — виртуализация + стриминг + быстрый поиск + плагины + undo + логи + хоткеи + экспорт воркер"""

from __future__ import annotations

import json
import re
import sys
import html as _html
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QSettings, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QGuiApplication, QKeySequence, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QToolButton, QMenu,
    QFileDialog, QMessageBox, QTabWidget, QPlainTextEdit, QScrollArea,
    QFrame, QDialog, QCheckBox, QComboBox, QFormLayout, QLineEdit,
    QStatusBar, QSizePolicy, QProgressDialog, QInputDialog, QAbstractItemView,
)

from ..core.parsers.base import TextParseOptions
from ..core.models import ChatLog
from ..core.exporters.base import ExportOptions, CONTENT_ALL, CONTENT_THOUGHTS, THOUGHTS_INCLUDE, THOUGHTS_EXCLUDE, CONTENT_PROMPTS, CONTENT_ANSWERS
from ..core.exporters.manager import export_to_files
from ..i18n.translator import Translator, LANGS, DEFAULT_LANG
from ..indexer import SearchIndex
from ..indexer.memory_search import fast_search_chats
from ..utils.paths import reveal_in_file_manager
from ..utils.logger import setup_logger, get_logger
from .themes import THEMES, build_stylesheet_cached, build_palette
from .widgets.message_card import MessageCard, load_icon
from .widgets.virtual_view import MessageListModel, MessageDelegate, VirtualMessageListView
from .dialogs import ExportDialog, TextSeparatorsDialog, CopySettingsDialog, BatchExportDialog, CollapseSettingsDialog
from .undo import UndoManager, Command
from .workers.export_worker import ExportWorker

logger = setup_logger()

APP_NAME = "StudioLogHelper"
ORG = "ArenaTools"
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 70, 200, 10
BASE_FONT_PT = 10.0
VIEW_BATCH = 25
LONG_PREVIEW = 5000
RAW_PREVIEW_LIMIT = 1_500_000


def strip_emoji(t: str) -> str:
    return re.sub(r"^[^\wА-Яа-яЁё]+\s*", "", t, count=1)


class ParseWorker(QThread):
    fileDone = pyqtSignal(object)
    fileError = pyqtSignal(str, str)
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
        self.setWindowTitle(APP_NAME + " 2.0 (PyQt6 + Virtual)")
        self.resize(1320, 850)
        self.setAcceptDrops(True)

        self.settings = QSettings(ORG, APP_NAME)
        self.translator = Translator(lang=self.settings.value("ui/lang", DEFAULT_LANG))

        self.theme_name = self.settings.value("ui/theme", "dark")
        self.render_md = self.settings.value("ui/render_md", "true") == "true"
        self.show_thoughts = self.settings.value("ui/show_thoughts", "true") == "true"
        self.show_extensions = self.settings.value("ui/show_extensions", "false") == "true"
        self.show_diagnostics = self.settings.value("ui/show_diagnostics", "false") == "true"
        self.auto_collapse_long = self.settings.value("ui/auto_collapse_long", "true") == "true"
        self.use_virtual = self.settings.value("ui/use_virtual", "false") == "true"
        try:
            self.collapse_preview_chars = int(self.settings.value("ui/collapse_preview_chars", LONG_PREVIEW))
        except:
            self.collapse_preview_chars = LONG_PREVIEW
        try:
            self.zoom = int(self.settings.value("ui/zoom", 100))
        except:
            self.zoom = 100
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom))
        self.text_parse_options = self._load_text_parse_options()

        self.chats: list[ChatLog] = []
        self.current: ChatLog | None = None
        self.chat_categories: dict = self._load_json("org/chat_categories", {})
        self.chat_notes: dict = self._load_json("org/chat_notes", {})
        self.chat_tags: dict = self._load_json("org/chat_tags", {})
        self.chat_derived: dict = self._load_json("org/chat_derived", {})
        self.categories: set = set(v for v in self.chat_categories.values() if v)
        self.recent_projects = self._load_json("org/recent_projects", [])
        self.recent_projects = [x for x in self.recent_projects if isinstance(x, str)]

        self._index = None
        self._render_gen = 0
        self._render_next = 0
        self._parse_worker = None
        self._export_worker = None

        self.undo_manager = UndoManager()
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.timeout.connect(self._apply_zoom)
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.timeout.connect(self._rebuild_view)

        self._build_ui()
        self.apply_theme()
        self._setup_hotkeys()
        self.statusBar().showMessage(self.tr("status_hint"))
        logger.info("MainWindow initialized")

    def tr(self, k, **kw):
        return self.translator.tr(k, **kw)

    def _load_text_parse_options(self):
        def split(v):
            return [x.strip() for x in str(v or "").splitlines() if x.strip()]
        return TextParseOptions(
            user_headers=split(self.settings.value("parse/user_headers", "")),
            model_headers=split(self.settings.value("parse/model_headers", "")),
            numbered_mode=self.settings.value("parse/numbered_mode", "model"),
        )

    def _load_json(self, key, default):
        try:
            import json as _j
            return _j.loads(self.settings.value(key, _j.dumps(default, ensure_ascii=False)))
        except:
            return default

    def _save_json(self, key, val):
        import json as _j
        self.settings.setValue(key, _j.dumps(val, ensure_ascii=False))

    def _chat_tags(self, chat):
        v = self.chat_tags.get(chat.path, [])
        return v if isinstance(v, list) else []

    def _chat_category(self, chat):
        return self.chat_categories.get(chat.path, "")

    def _chat_note(self, chat):
        return self.chat_notes.get(chat.path, "")

    def _decorate(self, btn, icon_name, min_w=0):
        orig = btn.text()
        ic = load_icon(icon_name)
        compact = strip_emoji(orig) or orig
        if not ic.isNull():
            btn.setIcon(ic)
            btn.setText(compact)
        btn.setProperty("fullText", compact)
        btn.setProperty("compactText", orig[:2])
        btn.setToolTip(btn.toolTip() or compact)
        if hasattr(btn, "setToolButtonStyle"):
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        if min_w:
            btn.setMinimumWidth(min_w)
        btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    # ---- plugins info ----
    def _show_plugins(self):
        from ..core.plugins import get_global_registry
        reg = get_global_registry()
        names = "\n".join([f"• {p.name}: {p.description}" for p in reg.plugins]) or "No plugins"
        QMessageBox.information(self, "Plugins", f"Loaded {len(reg.plugins)} plugins:\n\n{names}\n\nUser plugins folder: {Path.home() / '.local' / 'share' / APP_NAME / 'plugins'}")

    # ---- UI ----
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10,10,10,6)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(6)
        b_open = QPushButton(self.tr("open_files"))
        b_open.clicked.connect(self.open_files)
        self._decorate(b_open, "search.png", 140)
        b_folder = QPushButton(self.tr("open_folder"))
        b_folder.clicked.connect(self.open_folder)
        self._decorate(b_folder, "search.png", 145)
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
        self._decorate(self.btn_copy, "export.png", 120)
        top.addWidget(self.btn_copy)

        self.btn_export = QPushButton(self.tr("export_current"))
        self.btn_export.setObjectName("accent")
        self.btn_export.clicked.connect(self.export_current)
        self._decorate(self.btn_export, "export.png", 120)
        self.btn_export_all = QPushButton(self.tr("export_all"))
        self.btn_export_all.clicked.connect(self.export_all)
        self._decorate(self.btn_export_all, "export.png", 180)
        top.addWidget(self.btn_export)
        top.addWidget(self.btn_export_all)

        b_sep = QPushButton(self.tr("sep_button"))
        b_sep.clicked.connect(self.open_text_separators)
        self._decorate(b_sep, "search.png", 150)
        top.addWidget(b_sep)

        self.btn_org = QToolButton()
        self.btn_org.setText(self.tr("organize_button"))
        self.btn_org.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        om = QMenu(self.btn_org)
        om.addAction(self.tr("new_category"), self.create_category)
        om.addAction(self.tr("assign_category"), self.assign_category_current)
        om.addAction(self.tr("set_tags_current"), self.set_tags_current)
        om.addAction(self.tr("project_note_current"), self.set_note_current)
        om.addAction(self.tr("reveal_current_file"), self.reveal_current_file)
        om.addSeparator()
        om.addAction("Plugins…", self._show_plugins)
        om.addAction("Undo (Ctrl+Z)", self.undo)
        om.addAction("Redo (Ctrl+Y)", self.redo)
        self.btn_org.setMenu(om)
        self._decorate(self.btn_org, "export.png", 160)
        top.addWidget(self.btn_org)

        top.addStretch(1)
        root.addLayout(top)

        # second row
        top2 = QHBoxLayout()
        top2.addStretch(1)
        self.chk_view_md = QCheckBox(self.tr("view_markdown"))
        self.chk_view_md.setChecked(self.render_md)
        self.chk_view_md.toggled.connect(self._toggle_md)
        self.chk_view_th = QCheckBox(self.tr("view_thoughts"))
        self.chk_view_th.setChecked(self.show_thoughts)
        self.chk_view_th.toggled.connect(self._toggle_th)
        top2.addWidget(self.chk_view_md)
        top2.addWidget(self.chk_view_th)

        self.chk_virtual = QCheckBox("Виртуализация (10k+)")
        self.chk_virtual.setChecked(self.use_virtual)
        self.chk_virtual.setToolTip("Включить виртуализированный список для очень больших чатов (экспериментально, быстрее)")
        self.chk_virtual.toggled.connect(self._toggle_virtual)
        top2.addWidget(self.chk_virtual)

        self.btn_collapse = QToolButton()
        self.btn_collapse.setText(self.tr("collapse_all_long"))
        self.btn_collapse.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.btn_collapse.clicked.connect(lambda: self.set_all_collapsed(True))
        cm = QMenu(self.btn_collapse)
        cm.addAction(self.tr("collapse_all_long"), lambda: self.set_all_collapsed(True))
        cm.addAction(self.tr("expand_all_long"), lambda: self.set_all_collapsed(False))
        cm.addAction(self.tr("collapse_settings"), self.open_collapse_settings)
        self.btn_collapse.setMenu(cm)
        top2.addWidget(self.btn_collapse)

        b_zout = QPushButton("A−")
        b_zout.setFixedWidth(36)
        b_zout.clicked.connect(lambda: self.set_zoom(self.zoom - ZOOM_STEP))
        b_zin = QPushButton("A+")
        b_zin.setFixedWidth(36)
        b_zin.clicked.connect(lambda: self.set_zoom(self.zoom + ZOOM_STEP))
        self.lbl_zoom = QLabel(f"{self.zoom}%")
        self.lbl_zoom.setMinimumWidth(40)
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top2.addWidget(b_zout)
        top2.addWidget(self.lbl_zoom)
        top2.addWidget(b_zin)

        self.cmb_lang = QComboBox()
        for code, name in LANGS.items():
            self.cmb_lang.addItem(name, code)
        self.cmb_lang.setCurrentIndex(max(0, self.cmb_lang.findData(self.translator.get_lang())))
        self.cmb_lang.currentIndexChanged.connect(self._change_lang)
        top2.addWidget(self.cmb_lang)

        self.btn_theme = QPushButton("🌙" if self.theme_name=="dark" else "☀️")
        self.btn_theme.setFixedWidth(40)
        self.btn_theme.clicked.connect(self.toggle_theme)
        top2.addWidget(self.btn_theme)
        root.addLayout(top2)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0,0,0,0)
        ll.setSpacing(6)
        cap_row = QHBoxLayout()
        cap = QLabel(self.tr("loaded_logs"))
        cap.setObjectName("muted")
        cap_row.addWidget(cap,1)
        self.chk_show_ext = QCheckBox(self.tr("show_extensions"))
        self.chk_show_ext.setChecked(self.show_extensions)
        self.chk_show_ext.toggled.connect(self._toggle_ext)
        cap_row.addWidget(self.chk_show_ext)
        self.chk_show_diag = QCheckBox(self.tr("show_diagnostics"))
        self.chk_show_diag.setChecked(self.show_diagnostics)
        self.chk_show_diag.toggled.connect(self._toggle_diag)
        cap_row.addWidget(self.chk_show_diag)
        ll.addLayout(cap_row)

        filt = QFormLayout()
        self.cmb_filter_cat = QComboBox()
        self.cmb_filter_cat.currentIndexChanged.connect(lambda *_: self._refresh_file_list())
        self.cmb_filter_tag = QComboBox()
        self.cmb_filter_tag.currentIndexChanged.connect(lambda *_: self._refresh_file_list())
        self.ed_filter = QLineEdit()
        self.ed_filter.setPlaceholderText(self.tr("filter_placeholder"))
        self.ed_filter.textChanged.connect(lambda *_: self._refresh_file_list())
        filt.addRow(self.tr("filter_category"), self.cmb_filter_cat)
        filt.addRow(self.tr("filter_tag"), self.cmb_filter_tag)
        filt.addRow(self.tr("filter_text"), self.ed_filter)
        ll.addLayout(filt)
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
        rl.setContentsMargins(0,0,0,0)
        self.info_label = QLabel("")
        self.info_label.setObjectName("muted")
        self.info_label.setWordWrap(True)
        rl.addWidget(self.info_label)

        self.tabs = QTabWidget()

        # Old clean view (cards)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_host = QWidget()
        self.scroll_host.setObjectName("scrollHost")
        self.scroll_lay = QVBoxLayout(self.scroll_host)
        self.scroll_lay.setContentsMargins(10,10,10,10)
        self.scroll_lay.setSpacing(10)
        self.scroll_lay.addStretch(1)
        self.scroll.setWidget(self.scroll_host)
        self.scroll.verticalScrollBar().valueChanged.connect(self._maybe_load_more)
        self.tabs.addTab(self.scroll, self.tr("tab_clean") + " (Cards)")

        # Virtual view
        self.virtual_view = VirtualMessageListView()
        self.virtual_model = MessageListModel()
        self.virtual_delegate = MessageDelegate(THEMES[self.theme_name], self.render_md, self.show_thoughts, self.collapse_preview_chars, self.tr)
        self.virtual_view.setModel(self.virtual_model)
        self.virtual_view.setItemDelegate(self.virtual_delegate)
        self.virtual_view.requestCopy.connect(self._on_virtual_copy)
        self.tabs.addTab(self.virtual_view, "⚡ Virtual (10k+)")

        # Raw
        raw_tab = QWidget()
        rt = QVBoxLayout(raw_tab)
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
        split.setSizes([300, 1000])
        root.addWidget(split)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def _build_search_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        row1 = QHBoxLayout()
        self.ed_query = QLineEdit()
        self.ed_query.setPlaceholderText(self.tr("search_placeholder"))
        self.ed_query.returnPressed.connect(self.do_search)
        row1.addWidget(self.ed_query,1)
        b_search = QPushButton(self.tr("search_btn"))
        b_search.setObjectName("accent")
        b_search.clicked.connect(self.do_search)
        self._decorate(b_search, "search.png", 80)
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
        row_scope.addWidget(self.cmb_search_where,1)
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
        row2.addWidget(self.lbl_index_stats,1)
        v.addLayout(row2)

        self.search_results = QListWidget()
        self.search_results.setWordWrap(True)
        self.search_results.itemActivated.connect(self._open_search_hit)
        v.addWidget(self.search_results,1)

        hint = QLabel(self.tr("search_hint") + " | Ctrl+F фокус, Ctrl+K быстрый поиск")
        hint.setObjectName("muted")
        v.addWidget(hint)
        return w

    def _setup_hotkeys(self):
        # Clear old
        for act in getattr(self, "_hotkey_actions", []):
            self.removeAction(act)
        self._hotkey_actions = []

        def add(seq, fn, name=""):
            act = QAction(self)
            act.setShortcut(seq)
            act.triggered.connect(fn)
            self.addAction(act)
            self._hotkey_actions.append(act)

        add(QKeySequence.StandardKey.Open, self.open_files)
        add(QKeySequence("Ctrl+Shift+O"), self.open_folder)
        add(QKeySequence("Ctrl+E"), self.export_current)
        add(QKeySequence("Ctrl+Shift+E"), self.export_all)
        add(QKeySequence.StandardKey.Find, self._focus_search)
        add(QKeySequence("Ctrl+K"), self._quick_search)
        add(QKeySequence("Ctrl+1"), lambda: self.tabs.setCurrentIndex(0))
        add(QKeySequence("Ctrl+2"), lambda: self.tabs.setCurrentIndex(1))
        add(QKeySequence("Ctrl+3"), lambda: self.tabs.setCurrentIndex(2))
        add(QKeySequence("Ctrl+4"), lambda: self.tabs.setCurrentIndex(3))
        add(QKeySequence.StandardKey.ZoomIn, lambda: self.set_zoom(self.zoom+ZOOM_STEP))
        add(QKeySequence("Ctrl+="), lambda: self.set_zoom(self.zoom+ZOOM_STEP))
        add(QKeySequence.StandardKey.ZoomOut, lambda: self.set_zoom(self.zoom-ZOOM_STEP))
        add(QKeySequence("Ctrl+0"), lambda: self.set_zoom(100))
        add(QKeySequence.StandardKey.Undo, self.undo)
        add(QKeySequence.StandardKey.Redo, self.redo)
        add(QKeySequence("F5"), lambda: self._rebuild_view())
        logger.info("Hotkeys registered")

    def _focus_search(self):
        self.tabs.setCurrentIndex(3)
        self.ed_query.setFocus()
        self.ed_query.selectAll()

    def _quick_search(self):
        # quick search in loaded chats using memory search
        q, ok = QInputDialog.getText(self, "Quick Search", "Query (search in loaded):")
        if not ok or not q.strip():
            return
        self.ed_query.setText(q)
        self.cmb_search_where.setCurrentIndex(1)  # loaded
        self.do_search()

    def undo(self):
        cmd = self.undo_manager.undo()
        if cmd:
            self.statusBar().showMessage(f"Undo: {cmd.name}", 3000)
            self._refresh_filter_controls()
            self._refresh_file_list()
            self._rebuild_view()

    def redo(self):
        cmd = self.undo_manager.redo()
        if cmd:
            self.statusBar().showMessage(f"Redo: {cmd.name}", 3000)
            self._refresh_filter_controls()
            self._refresh_file_list()
            self._rebuild_view()

    # ---- theme/zoom ----
    def apply_theme(self, rebuild=True):
        t = THEMES[self.theme_name]
        scale = self.zoom/100.0
        QApplication.instance().setPalette(build_palette(t))
        self.setStyleSheet(build_stylesheet_cached(self.theme_name, scale))
        f = QApplication.instance().font()
        f.setPointSizeF(BASE_FONT_PT*scale)
        QApplication.instance().setFont(f)
        self.btn_theme.setText("🌙" if self.theme_name=="dark" else "☀️")
        # update delegate theme
        if hasattr(self, "virtual_delegate"):
            self.virtual_delegate.theme = t
            self.virtual_delegate.clear_cache()
            self.virtual_view.viewport().update()
        if rebuild:
            self._rebuild_view()
        self._update_index_stats()

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name=="dark" else "dark"
        self.settings.setValue("ui/theme", self.theme_name)
        self.apply_theme(True)

    def set_zoom(self, z):
        z = max(ZOOM_MIN, min(ZOOM_MAX, z))
        if z==self.zoom:
            return
        self.zoom=z
        self.settings.setValue("ui/zoom", z)
        self.lbl_zoom.setText(f"{z}%")
        self._zoom_timer.start(90)
        self.statusBar().showMessage(f"Zoom {z}%", 1200)

    def _apply_zoom(self):
        self.apply_theme(False)

    def _change_lang(self):
        code = self.cmb_lang.currentData()
        if code==self.translator.get_lang():
            return
        self.translator.set_lang(code)
        self.settings.setValue("ui/lang", code)
        QMessageBox.information(self, APP_NAME, "Restart UI to fully apply language / Перезапустите для языка")

    def _toggle_md(self, on):
        self.render_md=on
        self.settings.setValue("ui/render_md", "true" if on else "false")
        self.virtual_delegate.render_md = on
        self._rebuild_timer.start(80)

    def _toggle_th(self, on):
        self.show_thoughts=on
        self.settings.setValue("ui/show_thoughts", "true" if on else "false")
        self.virtual_delegate.show_thoughts = on
        self._rebuild_timer.start(80)

    def _toggle_virtual(self, on):
        self.use_virtual=on
        self.settings.setValue("ui/use_virtual", "true" if on else "false")
        self._rebuild_view()
        if on:
            self.tabs.setCurrentIndex(1)

    def open_collapse_settings(self):
        dlg = CollapseSettingsDialog(self, self.settings, self.tr)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            self.auto_collapse_long, self.collapse_preview_chars = dlg.save()
            self.virtual_delegate.preview_chars = self.collapse_preview_chars
            self.statusBar().showMessage(self.tr("collapse_saved"),4000)
            self._rebuild_timer.start(80)

    def set_all_collapsed(self, collapsed):
        self.auto_collapse_long=collapsed
        self.settings.setValue("ui/auto_collapse_long", "true" if collapsed else "false")
        # cards
        for i in range(self.scroll_lay.count()):
            w = self.scroll_lay.itemAt(i).widget()
            if isinstance(w, MessageCard) and w.is_long_card():
                w.set_collapsed(collapsed)
        # virtual
        self.virtual_model.set_all_collapsed(collapsed)

    # ---- drag drop ----
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths=[u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        files=[]
        from ..core.scanner import scan_folder
        for p in paths:
            pp=Path(p)
            if pp.is_dir():
                files.extend(scan_folder(pp))
            elif pp.is_file():
                files.append(str(pp))
        self.load_paths(files)

    # ---- file list ----
    def open_files(self):
        last=self.settings.value("ui/last_dir", str(Path.home()))
        files,_=QFileDialog.getOpenFileNames(self, self.tr("dlg_open_files"), last, self.tr("dlg_all_files"))
        if files:
            self.settings.setValue("ui/last_dir", str(Path(files[0]).parent))
            self.load_paths(files)

    def open_folder(self):
        last=self.settings.value("ui/last_dir", str(Path.home()))
        folder=QFileDialog.getExistingDirectory(self, self.tr("dlg_open_folder"), last)
        if not folder:
            return
        self.settings.setValue("ui/last_dir", folder)
        from ..core.scanner import scan_folder
        files=scan_folder(folder)
        if not files:
            QMessageBox.information(self, APP_NAME, self.tr("no_logs_in_folder"))
            return
        self.load_paths(files)

    def _format_badge(self, chat):
        p=Path(chat.path) if chat.path else Path("")
        ext=p.suffix.lower().lstrip(".") or self.tr("no_extension")
        kind="JSON" if chat.source_format=="json" else "TXT"
        return f"{kind} · {ext}"

    def _refresh_filter_controls(self):
        if not hasattr(self, "cmb_filter_cat"):
            return
        cur_cat=self.cmb_filter_cat.currentData()
        cur_tag=self.cmb_filter_tag.currentData()
        for cmb in (self.cmb_filter_cat, self.cmb_filter_tag):
            cmb.blockSignals(True)
            cmb.clear()
        self.cmb_filter_cat.addItem(self.tr("all_categories"), "")
        self.cmb_filter_cat.addItem(self.tr("uncategorized"), "__none__")
        for c in sorted(self.categories):
            self.cmb_filter_cat.addItem(c,c)
        self.cmb_filter_tag.addItem(self.tr("all_tags"), "")
        tags=sorted({t for vals in self.chat_tags.values() if isinstance(vals,list) for t in vals})
        for t in tags:
            self.cmb_filter_tag.addItem("#"+t,t)
        for cmb,val in ((self.cmb_filter_cat,cur_cat),(self.cmb_filter_tag,cur_tag)):
            i=cmb.findData(val)
            cmb.setCurrentIndex(i if i>=0 else 0)
            cmb.blockSignals(False)

    def _passes_filters(self, chat):
        cat_f=self.cmb_filter_cat.currentData() if hasattr(self,"cmb_filter_cat") else ""
        tag_f=self.cmb_filter_tag.currentData() if hasattr(self,"cmb_filter_tag") else ""
        text_f=self.ed_filter.text().strip().lower() if hasattr(self,"ed_filter") else ""
        cat=self._chat_category(chat)
        if cat_f=="__none__" and cat:
            return False
        if cat_f and cat_f!="__none__" and cat!=cat_f:
            return False
        if tag_f and tag_f not in self._chat_tags(chat):
            return False
        if text_f:
            hay=" ".join([chat.title, chat.path, chat.model, cat, " ".join(self._chat_tags(chat))]).lower()
            if text_f not in hay:
                return False
        return True

    def _add_list_item(self, chat):
        cat=self._chat_category(chat)
        tags=self._chat_tags(chat)
        title=f"[{cat}] {chat.title}" if cat else chat.title
        if tags:
            title+="  "+" ".join("#"+t for t in tags[:4])
        extra=f" · {self._format_badge(chat)}" if self.show_extensions else ""
        item=QListWidgetItem(f"{title}\n   {chat.model or '—'} · {len(chat.messages)} {self.tr('messages_short')}{extra}")
        item.setToolTip(chat.path)
        item.setData(Qt.ItemDataRole.UserRole, chat.path)
        self.file_list.addItem(item)

    def _refresh_file_list(self, select_path=None):
        if not hasattr(self,"file_list"):
            return
        cur=select_path or (self.current.path if self.current else None)
        self.file_list.blockSignals(True)
        self.file_list.clear()
        for chat in self.chats:
            if self._passes_filters(chat):
                self._add_list_item(chat)
        self.file_list.blockSignals(False)
        if cur:
            for row in range(self.file_list.count()):
                if self.file_list.item(row).data(Qt.ItemDataRole.UserRole)==cur:
                    self.file_list.setCurrentRow(row)
                    break
        elif self.file_list.count():
            self.file_list.setCurrentRow(0)

    def _toggle_ext(self, on):
        self.show_extensions=on
        self.settings.setValue("ui/show_extensions", "true" if on else "false")
        self._refresh_file_list()

    def _toggle_diag(self, on):
        self.show_diagnostics=on
        self.settings.setValue("ui/show_diagnostics", "true" if on else "false")
        self._rebuild_view()

    # ---- loading ----
    def load_paths(self, paths, select_path=None):
        if not paths:
            return
        existing={c.path for c in self.chats}
        to_load=[p for p in paths if p not in existing]
        if not to_load:
            if select_path:
                self._refresh_file_list(select_path)
            return
        if len(to_load)>15:
            self._start_parse_worker(to_load, select_path)
        else:
            self._load_sync(to_load, select_path)

    def _load_sync(self, paths, select_path=None):
        from ..core.parsers.parser import parse_file
        from ..core.exceptions import ParseError
        loaded, errors=0, []
        for p in paths:
            try:
                chat=parse_file(p, self.text_parse_options)
                self.chats.append(chat)
                loaded+=1
                logger.info(f"Loaded {p}")
            except (ParseError, OSError, ValueError) as ex:
                errors.append(f"{Path(p).name}: {ex}")
                logger.warning(f"Failed {p}: {ex}")
        self._refresh_filter_controls()
        if select_path:
            self._refresh_file_list(select_path)
        elif loaded:
            self._refresh_file_list(self.chats[-1].path if self.chats else None)
        msg=self.tr("loaded_n", n=loaded)
        if errors:
            msg+=self.tr("errors_n", n=len(errors))
            QMessageBox.warning(self, self.tr("not_all_loaded"), self.tr("not_logs")+"\n\n"+"\n".join(errors[:12]))
        self.statusBar().showMessage(msg,6000)

    def _start_parse_worker(self, paths, select_path):
        if self._parse_worker and self._parse_worker.isRunning():
            self._parse_worker.abort()
            self._parse_worker.wait()
        self._parse_errors=[]
        self._parse_loaded=0
        self._parse_select=select_path
        prog=QProgressDialog(self.tr("loading"), self.tr("cancel"), 0, len(paths), self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(300)
        self._parse_worker=ParseWorker(paths, self.text_parse_options)

        def on_done(chat):
            self.chats.append(chat)
            self._parse_loaded+=1
            prog.setValue(self._parse_loaded)

        def on_err(path, err):
            self._parse_errors.append(f"{Path(path).name}: {err}")
            prog.setValue(prog.value()+1)

        def on_all():
            prog.setValue(len(paths))
            prog.close()
            self._refresh_filter_controls()
            if self._parse_select:
                self._refresh_file_list(self._parse_select)
            elif self._parse_loaded:
                self._refresh_file_list(self.chats[-1].path if self.chats else None)
            msg=self.tr("loaded_n", n=self._parse_loaded)
            if self._parse_errors:
                msg+=self.tr("errors_n", n=len(self._parse_errors))
                QMessageBox.warning(self, self.tr("not_all_loaded"), self.tr("not_logs")+"\n\n"+"\n".join(self._parse_errors[:12]))
            self.statusBar().showMessage(msg,6000)

        def on_cancel():
            if self._parse_worker:
                self._parse_worker.abort()

        prog.canceled.connect(on_cancel)
        self._parse_worker.fileDone.connect(on_done)
        self._parse_worker.fileError.connect(on_err)
        self._parse_worker.allDone.connect(on_all)
        self._parse_worker.start()

    def clear_list(self):
        self.chats.clear()
        self.current=None
        self.file_list.clear()
        self.raw_view.clear()
        self.info_label.setText("")
        self._clear_cards()
        self.virtual_model.set_chat(None)
        logger.info("Cleared list")

    def _select_chat(self, row):
        if row<0 or row>=self.file_list.count():
            self.current=None
            return
        path=self.file_list.item(row).data(Qt.ItemDataRole.UserRole)
        self.current=next((c for c in self.chats if c.path==path), None)
        self._rebuild_view()

    def _clear_cards(self):
        self._render_gen+=1
        self.scroll_host.setUpdatesEnabled(False)
        while self.scroll_lay.count()>1:
            it=self.scroll_lay.takeAt(0)
            w=it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.scroll_host.setUpdatesEnabled(True)

    def _rebuild_view(self):
        self.scroll.setUpdatesEnabled(False)
        self.raw_view.setUpdatesEnabled(False)
        self._clear_cards()
        chat=self.current
        if chat is None:
            self.scroll.setUpdatesEnabled(True)
            self.raw_view.setUpdatesEnabled(True)
            self.virtual_model.set_chat(None)
            return
        # info
        info=[f"<b>{_html.escape(chat.title)}</b>"]
        cat=self._chat_category(chat)
        if cat:
            info.append(f"{self.tr('category_label')}: {_html.escape(cat)}")
        tags=self._chat_tags(chat)
        if tags:
            info.append(f"{self.tr('tags_label')}: "+" ".join("#"+_html.escape(t) for t in tags))
        note=self._chat_note(chat)
        if note:
            info.append(f"{self.tr('note_label')}: {_html.escape(note[:160])}")
        if self.show_diagnostics:
            diag=f"{self._format_badge(chat)} · {chat.path}"
            info.append(f"{self.tr('diagnostics_label')}: {_html.escape(diag)}")
        if chat.model:
            info.append(f"{self.tr('info_model')}: {_html.escape(chat.model)}")
        info.append(self.tr("info_msgs", n=len(chat.messages), u=chat.user_count, m=chat.model_count))
        if chat.thought_count:
            info.append(self.tr("info_thoughts", n=chat.thought_count))
        if chat.warnings:
            info.append(f"⚠ {'; '.join(chat.warnings)}")
        self.info_label.setText(" · ".join(info))

        # system instruction card
        if chat.system_instruction:
            box=QFrame()
            box.setObjectName("msgCard")
            box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            bl=QVBoxLayout(box)
            bl.setContentsMargins(14,10,14,12)
            cap=QLabel(f"<b>{self.tr('system_instruction')}</b>")
            cap.setObjectName("muted")
            bl.addWidget(cap)
            lab=QLabel(chat.system_instruction)
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            bl.addWidget(lab)
            self.scroll_lay.insertWidget(self.scroll_lay.count()-1, box)

        self._render_gen+=1
        self._render_next=0
        self._append_batch(self._render_gen)

        # virtual model set
        self.virtual_model.set_chat(chat, collapse_long=self.auto_collapse_long, preview_chars=self.collapse_preview_chars)

        # raw
        if chat.source_format=="json":
            self.tabs.setTabText(2, self.tr("source_json"))
            self.b_copy_raw.setText(self.tr("copy_source_json"))
            try:
                import json as _j
                raw=_j.dumps(chat.raw, ensure_ascii=False, indent=2)
                if len(raw)>RAW_PREVIEW_LIMIT:
                    raw=raw[:RAW_PREVIEW_LIMIT]+self.tr("raw_preview_truncated", shown=RAW_PREVIEW_LIMIT, total=len(raw))
                self.raw_view.setPlainText(raw)
            except:
                self.raw_view.setPlainText("<JSON?>")
        else:
            self.tabs.setTabText(2, self.tr("source_text"))
            self.b_copy_raw.setText(self.tr("copy_source_text"))
            raw=chat.raw_text or ""
            if len(raw)>RAW_PREVIEW_LIMIT:
                raw=raw[:RAW_PREVIEW_LIMIT]+self.tr("raw_preview_truncated", shown=RAW_PREVIEW_LIMIT, total=len(raw))
            self.raw_view.setPlainText(raw)

        self.raw_view.setUpdatesEnabled(True)
        self.scroll.setUpdatesEnabled(True)
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(0))

        # auto switch to virtual if enabled and large
        if self.use_virtual and len(chat.messages)>100:
            self.tabs.setCurrentIndex(1)

    def _append_batch(self, gen):
        if gen!=self._render_gen or self.current is None:
            return
        chat=self.current
        t=THEMES[self.theme_name]
        status=lambda s: self.statusBar().showMessage(s,4000)
        start=self._render_next
        end=min(start+VIEW_BATCH, len(chat.messages))
        self.scroll_host.setUpdatesEnabled(False)
        for idx in range(start,end):
            msg=chat.messages[idx]
            card=MessageCard(msg, idx+1, t, self.render_md, self.show_thoughts, status, model_name=chat.model, collapse_long=self.auto_collapse_long, preview_chars=self.collapse_preview_chars, tr_func=self.tr)
            self.scroll_lay.insertWidget(self.scroll_lay.count()-1, card)
        self.scroll_host.setUpdatesEnabled(True)
        self._render_next=end

    def _maybe_load_more(self):
        if self.current is None:
            return
        sb=self.scroll.verticalScrollBar()
        if sb.maximum()-sb.value()<900 and self._render_next < len(self.current.messages):
            self._append_batch(self._render_gen)

    def _on_virtual_copy(self, row, mode):
        if not self.current or row<0 or row>=len(self.current.messages):
            return
        msg=self.current.messages[row]
        from ..core.models import message_copy_text
        if mode=="normal":
            txt=message_copy_text(msg, include_thoughts=False)
        elif mode=="with_thoughts":
            txt=message_copy_text(msg, include_thoughts=True)
        else:
            txt=message_copy_text(msg, thoughts_only=True)
        QGuiApplication.clipboard().setText(txt)
        self.statusBar().showMessage(self.tr("msg_copied"),4000)

    # ---- copy ----
    def _need_chat(self):
        if self.current is None:
            QMessageBox.information(self, APP_NAME, self.tr("open_first"))
            return False
        return True

    def open_copy_settings(self):
        dlg=CopySettingsDialog(self, self.settings, self.tr)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            dlg.save()
            self.statusBar().showMessage(self.tr("copy_settings_saved"),4000)

    def _copy_sep(self):
        mode=self.settings.value("copy/separator","blank")
        if mode=="double":
            return "\n\n\n"
        if mode=="long":
            return "\n\n"+"—"*70+"\n\n"
        if mode=="custom":
            raw=self.settings.value("copy/custom_separator","\n---\n")
            return raw.replace("\\n","\n")
        return "\n\n"

    def _clean_copy(self, chat, which):
        parts=[]
        for msg in chat.messages:
            if which==CONTENT_PROMPTS and not msg.is_user:
                continue
            if which==CONTENT_ANSWERS and msg.is_user:
                continue
            if which==CONTENT_THOUGHTS:
                if msg.has_thoughts:
                    parts.extend(t.strip() for t in msg.thoughts if t.strip())
                continue
            if msg.text.strip():
                parts.append(msg.text.strip())
        return self._copy_sep().join(parts).strip()+("\n" if parts else "")

    def copy_chat(self, which):
        if not self._need_chat():
            return
        from ..core.models import COPY_PROMPTS, COPY_ANSWERS, COPY_THOUGHTS, COPY_ALL
        inc=self.settings.value("copy/include_service","true")=="true"
        if not inc:
            txt=self._clean_copy(self.current, which)
            QGuiApplication.clipboard().setText(txt)
            names={COPY_ALL:self.tr("copy_all"), COPY_PROMPTS:self.tr("copy_prompts"), COPY_ANSWERS:self.tr("copy_answers"), COPY_THOUGHTS:self.tr("copy_thoughts")}
            self.statusBar().showMessage(self.tr("copied_n", what=names[which], n=len(txt)),5000)
            return
        opts=ExportOptions(fmt="txt", metadata=False, system_instruction=False, auto_model_label=True, user_label=self.tr("user"), model_label=self.tr("model"), thoughts=THOUGHTS_INCLUDE if (self.show_thoughts and which!=COPY_PROMPTS) else THOUGHTS_EXCLUDE)
        from ..core.models import chat_to_clipboard_text
        txt=chat_to_clipboard_text(self.current, which, opts)
        QGuiApplication.clipboard().setText(txt)
        names={COPY_ALL:self.tr("copy_all"), COPY_PROMPTS:self.tr("copy_prompts"), COPY_ANSWERS:self.tr("copy_answers"), COPY_THOUGHTS:self.tr("copy_thoughts")}
        self.statusBar().showMessage(self.tr("copied_n", what=names[which], n=len(txt)),5000)

    def copy_raw(self):
        if not self._need_chat():
            return
        if self.current.source_format=="text":
            QGuiApplication.clipboard().setText(self.current.raw_text or "")
        else:
            import json as _j
            QGuiApplication.clipboard().setText(_j.dumps(self.current.raw, ensure_ascii=False, indent=2))
        self.statusBar().showMessage(self.tr("source_copied"),4000)

    # ---- export with worker ----
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
        dlg=ExportDialog(self, self.settings, self.tr, batch_count=len(chats))
        if dlg.exec()!=QDialog.DialogCode.Accepted:
            return
        opts=dlg.options()
        last=self.settings.value("ui/export_dir", self.settings.value("ui/last_dir", str(Path.home())))
        out_dir=QFileDialog.getExistingDirectory(self, self.tr("dlg_save_dir"), last)
        if not out_dir:
            return
        self.settings.setValue("ui/export_dir", out_dir)

        if len(chats)>5:
            # use worker
            prog=QProgressDialog(self.tr("export_done"), self.tr("cancel"), 0, len(chats), self)
            prog.setWindowModality(Qt.WindowModality.WindowModal)
            prog.setMinimumDuration(300)
            self._export_worker=ExportWorker(chats, opts, out_dir)
            created_all=[]
            errors=[]

            def on_prog(done, total, title):
                prog.setMaximum(total)
                prog.setValue(done)
                prog.setLabelText(f"Exporting {title}")

            def on_file_done(title, paths):
                created_all.extend(paths)

            def on_err(title, err):
                errors.append(f"{title}: {err}")

            def on_all_done(created, errs):
                prog.setValue(len(chats))
                prog.close()
                msg=self.tr("export_result", n=len(created_all), dir=out_dir)
                if errs or errors:
                    msg+="\n\n"+self.tr("export_errors")+"\n"+"\n".join((errs+errors)[:10])
                QMessageBox.information(self, self.tr("export_done"), msg)
                self.statusBar().showMessage(self.tr("exported_n", n=len(created_all)),6000)

            def on_cancel():
                if self._export_worker:
                    self._export_worker.abort()

            prog.canceled.connect(on_cancel)
            self._export_worker.progress.connect(on_prog)
            self._export_worker.fileDone.connect(on_file_done)
            self._export_worker.error.connect(on_err)
            self._export_worker.allDone.connect(on_all_done)
            self._export_worker.start()
        else:
            created, errors=[], []
            for chat in chats:
                try:
                    created.extend(export_to_files(chat, opts, out_dir))
                except Exception as ex:
                    errors.append(f"{chat.title}: {ex}")
            msg=self.tr("export_result", n=len(created), dir=out_dir)
            if errors:
                msg+="\n\n"+self.tr("export_errors")+"\n"+"\n".join(errors[:10])
            QMessageBox.information(self, self.tr("export_done"), msg)
            self.statusBar().showMessage(self.tr("exported_n", n=len(created)),6000)

    # ---- tags/categories with undo ----
    def set_note_current(self):
        if not self._need_chat():
            return
        old=self.chat_notes.get(self.current.path, "")
        note, ok=QInputDialog.getMultiLineText(self, APP_NAME, self.tr("project_note"), old)
        if not ok:
            return
        note=note.strip()
        cur_path=self.current.path

        def do():
            if note:
                self.chat_notes[cur_path]=note
            else:
                self.chat_notes.pop(cur_path,None)
            self._save_json("org/chat_notes", self.chat_notes)
            self._rebuild_view()
            self.statusBar().showMessage(self.tr("note_saved"),4000)

        def undo():
            if old:
                self.chat_notes[cur_path]=old
            else:
                self.chat_notes.pop(cur_path,None)
            self._save_json("org/chat_notes", self.chat_notes)
            self._rebuild_view()

        self.undo_manager.execute(Command("Set note", do, undo))

    def reveal_current_file(self):
        if not self._need_chat():
            return
        p=Path(self.current.path)
        if not p.exists():
            QMessageBox.information(self, APP_NAME, self.tr("reveal_no_file"))
            return
        ok=reveal_in_file_manager(p)
        if not ok:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))

    def set_tags_current(self):
        if not self._need_chat():
            return
        cur_path=self.current.path
        old_tags=self.chat_tags.get(cur_path, [])
        current=", ".join(old_tags)
        raw, ok=QInputDialog.getText(self, APP_NAME, self.tr("tags_prompt"), text=current)
        if not ok:
            return
        tags=[]
        seen=set()
        for t in re.split(r"[,;]", raw):
            t=t.strip().lstrip("#")
            if t and t.lower() not in seen:
                tags.append(t)
                seen.add(t.lower())

        def do():
            if tags:
                self.chat_tags[cur_path]=tags
            else:
                self.chat_tags.pop(cur_path,None)
            self._save_json("org/chat_tags", self.chat_tags)
            self._refresh_filter_controls()
            self._refresh_file_list(select_path=cur_path)
            self._rebuild_view()
            self.statusBar().showMessage(self.tr("tags_saved"),4000)

        def undo():
            if old_tags:
                self.chat_tags[cur_path]=old_tags
            else:
                self.chat_tags.pop(cur_path,None)
            self._save_json("org/chat_tags", self.chat_tags)
            self._refresh_filter_controls()
            self._refresh_file_list(select_path=cur_path)
            self._rebuild_view()

        self.undo_manager.execute(Command("Set tags", do, undo))

    def create_category(self):
        name, ok=QInputDialog.getText(self, APP_NAME, self.tr("category_name"))
        name=name.strip()
        if not ok or not name:
            return
        old_cats=set(self.categories)

        def do():
            self.categories.add(name)
            self._refresh_filter_controls()
            self.statusBar().showMessage(self.tr("category_created", name=name),4000)

        def undo():
            self.categories=old_cats
            self._refresh_filter_controls()

        self.undo_manager.execute(Command("Create category", do, undo))

    def assign_category_current(self):
        if not self._need_chat():
            return
        cur_path=self.current.path
        old_cat=self.chat_categories.get(cur_path, "")
        items=sorted(self.categories) or [self.tr("uncategorized")]
        name, ok=QInputDialog.getItem(self, APP_NAME, self.tr("category_name"), items, 0, True)
        name=name.strip()
        if not ok or not name:
            return

        def do():
            self.categories.add(name)
            self.chat_categories[cur_path]=name
            self._save_json("org/chat_categories", self.chat_categories)
            self._refresh_filter_controls()
            self._refresh_file_list(select_path=cur_path)
            self.statusBar().showMessage(self.tr("category_assigned", name=name),4000)

        def undo():
            if old_cat:
                self.chat_categories[cur_path]=old_cat
            else:
                self.chat_categories.pop(cur_path,None)
            self._save_json("org/chat_categories", self.chat_categories)
            self._refresh_filter_controls()
            self._refresh_file_list(select_path=cur_path)

        self.undo_manager.execute(Command("Assign category", do, undo))

    def create_text_log(self):
        last=self.settings.value("ui/last_dir", str(Path.home()))
        name, ok=QInputDialog.getText(self, APP_NAME, self.tr("file_name"), text="new_chat.txt")
        name=name.strip()
        if not ok or not name:
            return
        if not Path(name).suffix:
            name+=".txt"
        folder=QFileDialog.getExistingDirectory(self, self.tr("dlg_save_dir"), last)
        if not folder:
            return
        p=Path(folder)/Path(name).name
        if p.exists():
            QMessageBox.warning(self, APP_NAME, f"File exists: {p}")
            return
        clip=QGuiApplication.clipboard().text().strip()
        content="User:\n[запрос]\n\nModel:\n"+clip+"\n" if clip else "User:\n[запрос]\n\nModel:\n[ответ]\n"
        p.write_text(content, encoding="utf-8")
        self.settings.setValue("ui/last_dir", folder)
        self.statusBar().showMessage(self.tr("text_log_created", path=str(p)),5000)
        self.load_paths([str(p)], select_path=str(p))

    def open_text_separators(self):
        dlg=TextSeparatorsDialog(self, self.settings, self.tr)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            self.text_parse_options=dlg.options()
            self.statusBar().showMessage(self.tr("sep_saved"),4000)

    def open_copy_settings(self):
        dlg=CopySettingsDialog(self, self.settings, self.tr)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            dlg.save()
            self.statusBar().showMessage(self.tr("copy_settings_saved"),4000)

    # ---- indexer ----
    def _get_index(self):
        if self._index is None:
            self._index=SearchIndex()
        return self._index

    def _update_index_stats(self):
        if not hasattr(self,"lbl_index_stats") or self._index is None:
            return
        try:
            st=self._index.stats()
            self.lbl_index_stats.setText(self.tr("index_stats", files=st["files"], msgs=st["messages"], mb=st["db_size"]/1e6))
        except:
            pass

    def index_folder(self):
        last=self.settings.value("ui/index_dir", self.settings.value("ui/last_dir", str(Path.home())))
        folder=QFileDialog.getExistingDirectory(self, self.tr("dlg_open_folder"), last)
        if not folder:
            return
        self.settings.setValue("ui/index_dir", folder)
        prog=QProgressDialog(self.tr("indexing"), self.tr("cancel"), 0, 100, self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)

        def cb(done,total,path):
            if total:
                prog.setMaximum(total)
                prog.setValue(done)
                prog.setLabelText(f"{self.tr('indexing')}\n{Path(path).name}" if path else self.tr("indexing"))
            QApplication.processEvents()
            if prog.wasCanceled():
                raise KeyboardInterrupt

        idx=self._get_index()
        try:
            stats=idx.index_paths([folder], progress=cb)
            prog.setValue(prog.maximum())
            QMessageBox.information(self, self.tr("index_done"), self.tr("index_done")+":\n"+stats.summary() + (("\n\n"+"\n".join(stats.errors[:8])) if stats.errors else ""))
        except KeyboardInterrupt:
            pass
        finally:
            prog.close()
        self._update_index_stats()
        logger.info(f"Indexing done: {stats.summary() if 'stats' in locals() else 'cancelled'}")

    # ---- search with memory fast path ----
    def do_search(self):
        q=self.ed_query.text().strip()
        self.search_results.clear()
        if not q:
            return
        where=self.cmb_search_where.currentData()
        scope=self.cmb_scope.currentData()

        if where in ("current","loaded"):
            chats=[self.current] if where=="current" else list(self.chats)
            if where=="current" and not self.current:
                QMessageBox.information(self, APP_NAME, self.tr("open_first"))
                return
            # use fast memory search
            hits=fast_search_chats(chats, q, scope, max_workers=4, limit=300)
            if not hits:
                it=QListWidgetItem(self.tr("search_no_results"))
                it.setFlags(Qt.ItemFlag.NoItemFlags)
                self.search_results.addItem(it)
                return
            for h in hits:
                icon="💭" if h.is_thought else ("👤" if h.role=="user" else "🤖")
                it=QListWidgetItem(f"{icon} {h.chat_title}  ·  {self._format_badge(next((c for c in chats if c.path==h.chat_path), type('o',(),{'path':h.chat_path})()))}  ·  #{h.msg_num}\n{h.snippet}")
                it.setToolTip(h.chat_path)
                it.setData(Qt.ItemDataRole.UserRole, (h.chat_path, "log"))
                self.search_results.addItem(it)
            self.statusBar().showMessage(self.tr("search_results_n", n=len(hits)),5000)
            logger.info(f"Memory search '{q}' found {len(hits)}")
            return

        if self._index is None:
            it=QListWidgetItem(self.tr("search_need_index"))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.search_results.addItem(it)
            return

        role, thoughts, kind=None,None,None
        if scope=="user":
            role,thoughts="user",False
        elif scope=="model":
            role,thoughts="model",False
        elif scope=="thoughts":
            thoughts=True
        if where=="index_txt":
            kind="txt"
        elif where=="index_json":
            kind="log"
        try:
            hits=self._index.search(q, role=role, thoughts=thoughts, kind=kind, limit=300)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, str(ex))
            return
        if not hits:
            it=QListWidgetItem(self.tr("search_no_results"))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.search_results.addItem(it)
            return
        for h in hits:
            icon="📄" if h.kind=="txt" else ("💭" if h.is_thought else ("👤" if h.role=="user" else "🤖"))
            it=QListWidgetItem(f"{icon} {h.title}  ·  {h.model or '—'}  ·  #{h.msg_num}\n{h.snippet}")
            it.setToolTip(h.path)
            it.setData(Qt.ItemDataRole.UserRole, (h.path, h.kind))
            self.search_results.addItem(it)
        self.statusBar().showMessage(self.tr("search_results_n", n=len(hits)),5000)

    def _open_search_hit(self, item):
        data=item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        path,kind=data if isinstance(data,tuple) else (data,"log")
        if not Path(path).exists():
            QMessageBox.warning(self, APP_NAME, f"404: {path}")
            return
        if kind=="txt":
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            return
        self.load_paths([path], select_path=path)
        self.tabs.setCurrentIndex(0)
