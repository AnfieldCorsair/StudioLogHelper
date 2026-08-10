# -*- coding: utf-8 -*-
"""MainWindow — главное окно приложения StudioLogHelper 2.0 (PyQt6).

Оптимизации:
  - Ленивая отрисовка вкладок (рендерится ТОЛЬКО активная вкладка, 0ms лагов при переключении галочек)
  - Аппаратная виртуализация для 10k+ сообщений
  - Гибридный поиск (FTS5 + Стемминг + Локальные эмбеддинги)
  - Иерархические категории (Work/Research/Gemini)
  - Автосохранение проектов .slh.json
  - Адаптивное масштабирование кнопок и шрифтов
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtGui import QAction, QGuiApplication, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.exporters.base import CONTENT_ALL, CONTENT_ANSWERS, CONTENT_PROMPTS, CONTENT_THOUGHTS
from ..core.models import COPY_ALL, COPY_ANSWERS, COPY_PROMPTS, COPY_THOUGHTS, ChatLog, Message
from ..core.parsers.base import TextParseOptions
from ..i18n.translator import DEFAULT_LANG, LANGS, Translator
from ..indexer import HybridSearchEngine, SearchIndex
from ..indexer.memory_search import fast_search_chats
from ..utils.logger import get_logger, setup_logger
from ..utils.paths import reveal_in_file_manager
from .controllers import FileListController, ProjectController
from .dialogs import (
    BatchExportDialog,
    BookmarkDialog,
    CollapseSettingsDialog,
    CopySettingsDialog,
    ExportDialog,
    TextSeparatorsDialog,
)
from .renderers import MessageRenderer
from .services import CopyService, ExportService
from .themes import THEMES, build_palette, build_stylesheet_cached
from .undo import UndoManager
from .widgets import (
    MessageCard,
    MessageDelegate,
    MessageListModel,
    ReaderView,
    VirtualMessageListView,
    load_icon,
)
from .workers import ParseWorker

logger = setup_logger()

APP_NAME = "StudioLogHelper"
ORG = "ArenaTools"
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 70, 200, 10
BASE_FONT_PT = 10.0
VIEW_BATCH = 25
LONG_PREVIEW = 5000


def strip_emoji(t: str) -> str:
    return re.sub(r"^[^\wА-Яа-яЁё]+\s*", "", t, count=1)


class MainWindow(QMainWindow):
    """Главное окно приложения с оптимизированной архитектурой."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME + " 2.0 (PyQt6 + Book Reader)")
        self.resize(1340, 860)
        self.setMinimumSize(820, 520)
        self.setAcceptDrops(True)

        self.settings = QSettings(ORG, APP_NAME)
        self.translator = Translator(lang=self.settings.value("ui/lang", DEFAULT_LANG))
        self.undo_manager = UndoManager()

        # Controllers
        self.project_ctrl = ProjectController(self.settings, self.undo_manager)
        self.file_ctrl = FileListController(self.project_ctrl)
        self.hybrid_engine = HybridSearchEngine()

        # UI State & Preferences
        self.theme_name = self.settings.value("ui/theme", "dark")
        self.render_md = self.settings.value("ui/render_md", "true") == "true"
        self.show_thoughts = self.settings.value("ui/show_thoughts", "true") == "true"
        self.file_ctrl.show_extensions = self.settings.value("ui/show_extensions", "false") == "true"
        self.file_ctrl.show_diagnostics = self.settings.value("ui/show_diagnostics", "false") == "true"
        self.auto_collapse_long = self.settings.value("ui/auto_collapse_long", "true") == "true"
        self.use_virtual = self.settings.value("ui/use_virtual", "false") == "true"

        try:
            self.collapse_preview_chars = int(self.settings.value("ui/collapse_preview_chars", LONG_PREVIEW))
        except (ValueError, TypeError):
            self.collapse_preview_chars = LONG_PREVIEW

        try:
            self.zoom = int(self.settings.value("ui/zoom", 100))
        except (ValueError, TypeError):
            self.zoom = 100
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom))

        self.text_parse_options = self._load_text_parse_options()
        self._index: Optional[SearchIndex] = None
        self._render_gen = 0
        self._render_next = 0
        self._parse_worker: Optional[ParseWorker] = None

        # Ленивые флаги отрисовки табов (0: Cards, 1: Virtual, 2: Reader, 3: Raw)
        self._tab_dirty: Dict[int, bool] = {0: True, 1: True, 2: True, 3: True}

        # Timers
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.timeout.connect(self._apply_zoom)

        # Build UI & signals
        self._build_ui()
        self._connect_signals()
        self.apply_theme(rebuild_tabs=False)
        self._setup_hotkeys()

        self.statusBar().showMessage(self.tr("status_hint"))
        logger.info("MainWindow initialized with modular architecture")

    def tr(self, k: str, **kw) -> str:
        return self.translator.tr(k, **kw)

    def _load_text_parse_options(self) -> TextParseOptions:
        def split_lines(v):
            return [x.strip() for x in str(v or "").splitlines() if x.strip()]

        return TextParseOptions(
            user_headers=split_lines(self.settings.value("parse/user_headers", "")),
            model_headers=split_lines(self.settings.value("parse/model_headers", "")),
            numbered_mode=self.settings.value("parse/numbered_mode", "model"),
        )

    def _decorate(self, btn, icon_name: str, min_w: int = 0):
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
        btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    # ---- UI Construction ----
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)
        root.setSpacing(6)

        # Top Bar Row 1: Actions
        top1 = QHBoxLayout()
        top1.setSpacing(6)

        b_open = QPushButton(self.tr("open_files"))
        b_open.clicked.connect(self.open_files)
        self._decorate(b_open, "search.png")
        b_folder = QPushButton(self.tr("open_folder"))
        b_folder.clicked.connect(self.open_folder)
        self._decorate(b_folder, "search.png")
        top1.addWidget(b_open)
        top1.addWidget(b_folder)

        self.btn_copy = QToolButton()
        self.btn_copy.setText(self.tr("copy_menu"))
        self.btn_copy.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        m_copy = QMenu(self.btn_copy)
        m_copy.addAction(self.tr("copy_all"), lambda: self.copy_chat(COPY_ALL))
        m_copy.addAction(self.tr("copy_prompts"), lambda: self.copy_chat(COPY_PROMPTS))
        m_copy.addAction(self.tr("copy_answers"), lambda: self.copy_chat(COPY_ANSWERS))
        m_copy.addAction(self.tr("copy_thoughts"), lambda: self.copy_chat(COPY_THOUGHTS))
        m_copy.addSeparator()
        m_copy.addAction(self.tr("copy_settings"), self.open_copy_settings)
        self.btn_copy.setMenu(m_copy)
        self._decorate(self.btn_copy, "export.png")
        top1.addWidget(self.btn_copy)

        self.btn_export = QPushButton(self.tr("export_current"))
        self.btn_export.setObjectName("accent")
        self.btn_export.clicked.connect(self.export_current)
        self._decorate(self.btn_export, "export.png")
        self.btn_export_all = QPushButton(self.tr("export_all"))
        self.btn_export_all.clicked.connect(self.export_all)
        self._decorate(self.btn_export_all, "export.png")
        top1.addWidget(self.btn_export)
        top1.addWidget(self.btn_export_all)

        b_sep = QPushButton(self.tr("sep_button"))
        b_sep.clicked.connect(self.open_text_separators)
        self._decorate(b_sep, "search.png")
        top1.addWidget(b_sep)

        # Organize / Project Menu
        self.btn_org = QToolButton()
        self.btn_org.setText(self.tr("organize_button"))
        self.btn_org.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        om = QMenu(self.btn_org)
        om.addAction(self.tr("new_category"), self.create_category)
        om.addAction(self.tr("assign_category"), self.assign_category_current)
        om.addAction(self.tr("set_tags_current"), self.set_tags_current)
        om.addAction(self.tr("project_note_current"), self.set_note_current)
        om.addAction(self.tr("reader_bookmarks") + " и Цитаты", self.open_bookmarks_dialog)
        om.addAction(self.tr("reveal_current_file"), self.reveal_current_file)
        om.addSeparator()
        om.addAction(self.tr("project_new"), self.new_project)
        om.addAction(self.tr("project_open"), self.open_project)
        om.addAction(self.tr("project_save"), self.save_project)
        om.addSeparator()
        om.addAction("Plugins…", self._show_plugins)
        om.addAction("Undo (Ctrl+Z)", self.undo)
        om.addAction("Redo (Ctrl+Y)", self.redo)
        self.btn_org.setMenu(om)
        self._decorate(self.btn_org, "export.png")
        top1.addWidget(self.btn_org)

        top1.addStretch(1)
        root.addLayout(top1)

        # Top Bar Row 2: View Controls
        top2 = QHBoxLayout()
        top2.setSpacing(8)
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
        self.chk_virtual.setToolTip("Включить режим виртуализации для сверхбольших логов")
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
        b_zout.setMinimumWidth(28)
        b_zout.clicked.connect(lambda: self.set_zoom(self.zoom - ZOOM_STEP))
        b_zin = QPushButton("A+")
        b_zin.setMinimumWidth(28)
        b_zin.clicked.connect(lambda: self.set_zoom(self.zoom + ZOOM_STEP))
        self.lbl_zoom = QLabel(f"{self.zoom}%")
        self.lbl_zoom.setMinimumWidth(36)
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

        self.btn_theme = QPushButton("🌙" if self.theme_name == "dark" else "☀️")
        self.btn_theme.setMinimumWidth(32)
        self.btn_theme.clicked.connect(self.toggle_theme)
        top2.addWidget(self.btn_theme)
        root.addLayout(top2)

        # Main Splitter
        split = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel (File list & filters)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)

        cap_row = QHBoxLayout()
        cap = QLabel(self.tr("loaded_logs"))
        cap.setObjectName("muted")
        cap_row.addWidget(cap, 1)
        self.chk_show_ext = QCheckBox(self.tr("show_extensions"))
        self.chk_show_ext.setChecked(self.file_ctrl.show_extensions)
        self.chk_show_ext.toggled.connect(self._toggle_ext)
        cap_row.addWidget(self.chk_show_ext)
        self.chk_show_diag = QCheckBox(self.tr("show_diagnostics"))
        self.chk_show_diag.setChecked(self.file_ctrl.show_diagnostics)
        self.chk_show_diag.toggled.connect(self._toggle_diag)
        cap_row.addWidget(self.chk_show_diag)
        ll.addLayout(cap_row)

        filt = QFormLayout()
        filt.setContentsMargins(0, 0, 0, 0)
        self.cmb_filter_cat = QComboBox()
        self.cmb_filter_cat.currentIndexChanged.connect(self._on_filter_changed)
        self.cmb_filter_tag = QComboBox()
        self.cmb_filter_tag.currentIndexChanged.connect(self._on_filter_changed)
        self.ed_filter = QLineEdit()
        self.ed_filter.setPlaceholderText(self.tr("filter_placeholder"))
        self.ed_filter.textChanged.connect(self._on_filter_changed)
        filt.addRow(self.tr("filter_category"), self.cmb_filter_cat)
        filt.addRow(self.tr("filter_tag"), self.cmb_filter_tag)
        filt.addRow(self.tr("filter_text"), self.ed_filter)
        ll.addLayout(filt)

        self._refresh_filter_controls()

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.currentRowChanged.connect(self._on_file_list_selection_changed)
        ll.addWidget(self.file_list, 1)

        b_clear = QPushButton(self.tr("clear_list"))
        b_clear.clicked.connect(self.clear_list)
        ll.addWidget(b_clear)
        split.addWidget(left)

        # Right Panel (Header & Tabs)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        self.info_label = QLabel("")
        self.info_label.setObjectName("muted")
        self.info_label.setWordWrap(True)
        rl.addWidget(self.info_label)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Tab 0: Clean Card View
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_host = QWidget()
        self.scroll_host.setObjectName("scrollHost")
        self.scroll_lay = QVBoxLayout(self.scroll_host)
        self.scroll_lay.setContentsMargins(8, 8, 8, 8)
        self.scroll_lay.setSpacing(8)
        self.scroll_lay.addStretch(1)
        self.scroll.setWidget(self.scroll_host)
        self.scroll.verticalScrollBar().valueChanged.connect(self._maybe_load_more)
        self.tabs.addTab(self.scroll, self.tr("tab_clean"))

        # Tab 1: Virtual View
        self.virtual_view = VirtualMessageListView()
        self.virtual_model = MessageListModel()
        self.virtual_delegate = MessageDelegate(
            THEMES[self.theme_name],
            self.render_md,
            self.show_thoughts,
            self.collapse_preview_chars,
            self.tr,
        )
        self.virtual_view.setModel(self.virtual_model)
        self.virtual_view.setItemDelegate(self.virtual_delegate)
        self.virtual_view.requestCopy.connect(self._on_virtual_copy)
        self.tabs.addTab(self.virtual_view, "⚡ Virtual (10k+)")

        # Tab 2: Book Mode (Reader)
        self.reader_view = ReaderView(self.settings, self.project_ctrl, self.tr)
        self.reader_view.bookmarkJump.connect(self._on_reader_bookmark_jump)
        self.tabs.addTab(self.reader_view, self.tr("tab_reader"))

        # Tab 3: Raw Source View
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

        # Tab 4: Search Tab
        self.tabs.addTab(self._build_search_tab(), self.tr("tab_search"))

        rl.addWidget(self.tabs, 1)
        split.addWidget(right)
        split.setSizes([300, 1040])
        root.addWidget(split, 1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def _build_search_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        row1 = QHBoxLayout()
        self.ed_query = QLineEdit()
        self.ed_query.setPlaceholderText("Гибридный поиск (слова, фразы, формы слов)…")
        self.ed_query.returnPressed.connect(self.do_search)
        row1.addWidget(self.ed_query, 1)
        b_search = QPushButton(self.tr("search_btn"))
        b_search.setObjectName("accent")
        b_search.clicked.connect(self.do_search)
        self._decorate(b_search, "search.png")
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

        hint = QLabel(self.tr("search_hint") + " | Ctrl+F фокус, Ctrl+K быстрый поиск")
        hint.setObjectName("muted")
        v.addWidget(hint)
        return w

    def _connect_signals(self):
        self.file_ctrl.chatsChanged.connect(self._refresh_file_list_ui)
        self.file_ctrl.currentChanged.connect(self._on_current_chat_changed)
        self.file_ctrl.filtersChanged.connect(self._refresh_file_list_ui)
        self.project_ctrl.categoriesChanged.connect(self._refresh_filter_controls)
        self.project_ctrl.metadataChanged.connect(lambda _: self._mark_all_tabs_dirty())
        self.project_ctrl.autoSaved.connect(
            lambda path: self.statusBar().showMessage(f"✓ Проект сохранён (autosave): {Path(path).name}", 2500)
        )

    def _setup_hotkeys(self):
        for act in getattr(self, "_hotkey_actions", []):
            self.removeAction(act)
        self._hotkey_actions = []

        def add(seq, fn):
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
        add(QKeySequence("Ctrl+B"), self._toggle_bookmark_active)
        add(QKeySequence("Ctrl+1"), lambda: self.tabs.setCurrentIndex(0))
        add(QKeySequence("Ctrl+2"), lambda: self.tabs.setCurrentIndex(1))
        add(QKeySequence("Ctrl+3"), lambda: self.tabs.setCurrentIndex(2))
        add(QKeySequence("Ctrl+4"), lambda: self.tabs.setCurrentIndex(3))
        add(QKeySequence("Ctrl+5"), lambda: self.tabs.setCurrentIndex(4))
        add(QKeySequence.StandardKey.ZoomIn, lambda: self.set_zoom(self.zoom + ZOOM_STEP))
        add(QKeySequence("Ctrl+="), lambda: self.set_zoom(self.zoom + ZOOM_STEP))
        add(QKeySequence.StandardKey.ZoomOut, lambda: self.set_zoom(self.zoom - ZOOM_STEP))
        add(QKeySequence("Ctrl+0"), lambda: self.set_zoom(100))
        add(QKeySequence.StandardKey.Undo, self.undo)
        add(QKeySequence.StandardKey.Redo, self.redo)
        add(QKeySequence("F5"), self._force_refresh_active_tab)
        logger.info("Hotkeys registered")

    # ---- Lazy Tab Management (Zero Lags!) ----
    def _mark_all_tabs_dirty(self):
        self._tab_dirty = {0: True, 1: True, 2: True, 3: True}
        self._render_active_tab_if_dirty()

    def _on_tab_changed(self, index: int):
        self._render_active_tab_if_dirty()

    def _render_active_tab_if_dirty(self):
        cur_tab = self.tabs.currentIndex()
        if not self._tab_dirty.get(cur_tab, False):
            return

        chat = self.file_ctrl.current
        # Always update header info
        info_str = MessageRenderer.format_info_header(
            chat, self.project_ctrl, self.file_ctrl.show_diagnostics, self.file_ctrl.show_extensions, self.tr
        )
        self.info_label.setText(info_str)

        if cur_tab == 0:  # Cards
            self._render_cards_tab()
        elif cur_tab == 1:  # Virtual
            self.virtual_model.set_chat(
                chat, collapse_long=self.auto_collapse_long, preview_chars=self.collapse_preview_chars
            )
            self.virtual_delegate.clear_cache()
            self.virtual_view.viewport().update()
        elif cur_tab == 2:  # Reader
            self.reader_view.set_chat(chat)
        elif cur_tab == 3:  # Raw
            raw_text, raw_title, copy_btn_text = MessageRenderer.format_raw_content(chat, self.tr)
            self.tabs.setTabText(3, raw_title)
            self.b_copy_raw.setText(copy_btn_text)
            self.raw_view.setPlainText(raw_text)

        self._tab_dirty[cur_tab] = False

    def _render_cards_tab(self):
        self.scroll.setUpdatesEnabled(False)
        self._clear_cards()
        chat = self.file_ctrl.current
        if chat is None:
            self.scroll.setUpdatesEnabled(True)
            return

        if chat.system_instruction:
            sys_card = MessageRenderer.create_system_instruction_card(chat, self.tr)
            self.scroll_lay.insertWidget(self.scroll_lay.count() - 1, sys_card)

        self._render_gen += 1
        self._render_next = 0
        self._append_batch(self._render_gen)
        self.scroll.setUpdatesEnabled(True)
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(0))

    def _force_refresh_active_tab(self):
        self._mark_all_tabs_dirty()

    def _on_current_chat_changed(self, chat: Optional[ChatLog]):
        self._mark_all_tabs_dirty()

    # ---- Theme & Zoom ----
    def apply_theme(self, rebuild_tabs: bool = False):
        t = THEMES[self.theme_name]
        scale = self.zoom / 100.0
        QApplication.instance().setPalette(build_palette(t))
        self.setStyleSheet(build_stylesheet_cached(self.theme_name, scale))
        f = QApplication.instance().font()
        f.setPointSizeF(BASE_FONT_PT * scale)
        QApplication.instance().setFont(f)
        self.btn_theme.setText("🌙" if self.theme_name == "dark" else "☀️")

        if hasattr(self, "virtual_delegate"):
            self.virtual_delegate.theme = t
            self.virtual_delegate.clear_cache()
            self.virtual_view.viewport().update()

        if rebuild_tabs:
            self._mark_all_tabs_dirty()
        self._update_index_stats()

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.settings.setValue("ui/theme", self.theme_name)
        self.apply_theme(rebuild_tabs=True)

    def set_zoom(self, z: int):
        z = max(ZOOM_MIN, min(ZOOM_MAX, z))
        if z == self.zoom:
            return
        self.zoom = z
        self.settings.setValue("ui/zoom", z)
        self.lbl_zoom.setText(f"{z}%")
        self._zoom_timer.start(80)
        self.statusBar().showMessage(f"Zoom {z}%", 1000)

    def _apply_zoom(self):
        self.apply_theme(rebuild_tabs=False)

    def _change_lang(self):
        code = self.cmb_lang.currentData()
        if code == self.translator.get_lang():
            return
        self.translator.set_lang(code)
        self.settings.setValue("ui/lang", code)
        QMessageBox.information(
            self, APP_NAME, "Restart application to apply language / Перезапустите приложение"
        )

    def _toggle_md(self, on: bool):
        self.render_md = on
        self.settings.setValue("ui/render_md", "true" if on else "false")
        self.virtual_delegate.render_md = on
        self.reader_view.render_md = on
        self._mark_all_tabs_dirty()

    def _toggle_th(self, on: bool):
        self.show_thoughts = on
        self.settings.setValue("ui/show_thoughts", "true" if on else "false")
        self.virtual_delegate.show_thoughts = on
        self.reader_view.show_thoughts = on
        self._mark_all_tabs_dirty()

    def _toggle_virtual(self, on: bool):
        self.use_virtual = on
        self.settings.setValue("ui/use_virtual", "true" if on else "false")
        if on:
            self.tabs.setCurrentIndex(1)
        self._mark_all_tabs_dirty()

    def open_collapse_settings(self):
        dlg = CollapseSettingsDialog(self, self.settings, self.tr)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.auto_collapse_long, self.collapse_preview_chars = dlg.save()
            self.virtual_delegate.preview_chars = self.collapse_preview_chars
            self.statusBar().showMessage(self.tr("collapse_saved"), 4000)
            self._mark_all_tabs_dirty()

    def set_all_collapsed(self, collapsed: bool):
        self.auto_collapse_long = collapsed
        self.settings.setValue("ui/auto_collapse_long", "true" if collapsed else "false")
        for i in range(self.scroll_lay.count()):
            w = self.scroll_lay.itemAt(i).widget()
            if isinstance(w, MessageCard) and w.is_long_card():
                w.set_collapsed(collapsed)
        self.virtual_model.set_all_collapsed(collapsed)

    # ---- Filter & File List UI ----
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

        # Иерархический вывод категорий с отступами
        for full_cat, depth, label in self.project_ctrl.get_hierarchical_categories():
            self.cmb_filter_cat.addItem(label, full_cat)

        self.cmb_filter_tag.addItem(self.tr("all_tags"), "")
        all_tags = sorted({t for vals in self.project_ctrl.chat_tags.values() for t in vals})
        for t in all_tags:
            self.cmb_filter_tag.addItem("#" + t, t)

        for cmb, val in ((self.cmb_filter_cat, cur_cat), (self.cmb_filter_tag, cur_tag)):
            i = cmb.findData(val)
            cmb.setCurrentIndex(i if i >= 0 else 0)
            cmb.blockSignals(False)

    def _on_filter_changed(self):
        cat = self.cmb_filter_cat.currentData() or ""
        tag = self.cmb_filter_tag.currentData() or ""
        text = self.ed_filter.text().strip()
        self.file_ctrl.set_filters(cat, tag, text)

    def _refresh_file_list_ui(self):
        if not hasattr(self, "file_list"):
            return
        cur_path = self.file_ctrl.current.path if self.file_ctrl.current else None
        self.file_list.blockSignals(True)
        self.file_list.clear()

        for chat in self.file_ctrl.chats:
            if self.file_ctrl.passes_filters(chat):
                cat = self.project_ctrl.get_category(chat)
                tags = self.project_ctrl.get_tags(chat)
                bms = self.project_ctrl.get_bookmarks(chat)

                title = f"[{cat}] {chat.title}" if cat else chat.title
                if bms:
                    title = f"🔖 {title}"
                if tags:
                    title += "  " + " ".join("#" + t for t in tags[:4])
                extra = (
                    f" · {self.file_ctrl.format_badge(chat, self.tr)}"
                    if self.file_ctrl.show_extensions
                    else ""
                )

                item = QListWidgetItem(
                    f"{title}\n   {chat.model or '—'} · {len(chat.messages)} {self.tr('messages_short')}{extra}"
                )
                item.setToolTip(chat.path)
                item.setData(Qt.ItemDataRole.UserRole, chat.path)
                self.file_list.addItem(item)

        self.file_list.blockSignals(False)

        if cur_path:
            for row in range(self.file_list.count()):
                if self.file_list.item(row).data(Qt.ItemDataRole.UserRole) == cur_path:
                    self.file_list.setCurrentRow(row)
                    break
        elif self.file_list.count():
            self.file_list.setCurrentRow(0)

    def _on_file_list_selection_changed(self, row: int):
        if row < 0 or row >= self.file_list.count():
            self.file_ctrl.select_chat(None)
            return
        path = self.file_list.item(row).data(Qt.ItemDataRole.UserRole)
        self.file_ctrl.select_chat_by_path(path)

    def _toggle_ext(self, on: bool):
        self.file_ctrl.show_extensions = on
        self.settings.setValue("ui/show_extensions", "true" if on else "false")
        self._refresh_file_list_ui()

    def _toggle_diag(self, on: bool):
        self.file_ctrl.show_diagnostics = on
        self.settings.setValue("ui/show_diagnostics", "true" if on else "false")
        self._mark_all_tabs_dirty()

    # ---- Drag and Drop & Loading ----
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

    def open_files(self):
        last = self.settings.value("ui/last_dir", str(Path.home()))
        files, _ = QFileDialog.getOpenFileNames(
            self, self.tr("dlg_open_files"), last, self.tr("dlg_all_files")
        )
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

    def load_paths(self, paths: Sequence[str], select_path: Optional[str] = None):
        if not paths:
            return
        existing = {c.path for c in self.file_ctrl.chats}
        to_load = [p for p in paths if p not in existing]
        if not to_load:
            if select_path:
                self.file_ctrl.select_chat_by_path(select_path)
            return

        if len(to_load) > 15:
            self._start_parse_worker(to_load, select_path)
        else:
            self._load_sync(to_load, select_path)

    def _load_sync(self, paths: Sequence[str], select_path: Optional[str] = None):
        from ..core.exceptions import ParseError
        from ..core.parsers.parser import parse_file

        loaded, errors = 0, []
        new_chats = []
        for p in paths:
            try:
                chat = parse_file(p, self.text_parse_options)
                new_chats.append(chat)
                loaded += 1
            except (ParseError, OSError, ValueError, Exception) as ex:
                errors.append(f"{Path(p).name}: {ex}")

        self.file_ctrl.add_chats(new_chats)
        self._refresh_filter_controls()

        if select_path:
            self.file_ctrl.select_chat_by_path(select_path)
        elif new_chats:
            self.file_ctrl.select_chat(new_chats[-1])

        msg = self.tr("loaded_n", n=loaded)
        if errors:
            msg += self.tr("errors_n", n=len(errors))
            QMessageBox.warning(
                self, self.tr("not_all_loaded"), self.tr("not_logs") + "\n\n" + "\n".join(errors[:12])
            )
        self.statusBar().showMessage(msg, 6000)

    def _start_parse_worker(self, paths: Sequence[str], select_path: Optional[str]):
        if self._parse_worker and self._parse_worker.isRunning():
            self._parse_worker.abort()
            self._parse_worker.wait()

        self._parse_errors = []
        self._parse_loaded = 0
        self._parse_select = select_path

        prog = QProgressDialog(self.tr("loading"), self.tr("cancel"), 0, len(paths), self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(300)

        self._parse_worker = ParseWorker(paths, self.text_parse_options)

        def on_done(chat):
            self.file_ctrl.add_chat(chat)
            self._parse_loaded += 1
            prog.setValue(self._parse_loaded)

        def on_err(path, err):
            self._parse_errors.append(f"{Path(path).name}: {err}")
            prog.setValue(prog.value() + 1)

        def on_all():
            prog.setValue(len(paths))
            prog.close()
            self._refresh_filter_controls()
            if self._parse_select:
                self.file_ctrl.select_chat_by_path(self._parse_select)
            elif self.file_ctrl.chats:
                self.file_ctrl.select_chat(self.file_ctrl.chats[-1])

            msg = self.tr("loaded_n", n=self._parse_loaded)
            if self._parse_errors:
                msg += self.tr("errors_n", n=len(self._parse_errors))
                QMessageBox.warning(
                    self, self.tr("not_all_loaded"), self.tr("not_logs") + "\n\n" + "\n".join(self._parse_errors[:12])
                )
            self.statusBar().showMessage(msg, 6000)

        prog.canceled.connect(self._parse_worker.abort)
        self._parse_worker.fileDone.connect(on_done)
        self._parse_worker.fileError.connect(on_err)
        self._parse_worker.allDone.connect(on_all)
        self._parse_worker.start()

    def clear_list(self):
        self.file_ctrl.clear()
        self.raw_view.clear()
        self.info_label.setText("")
        self._clear_cards()
        self.virtual_model.set_chat(None)
        self.reader_view.set_chat(None)
        logger.info("Cleared file list")

    # ---- Card Batch Rendering ----
    def _clear_cards(self):
        self._render_gen += 1
        self.scroll_host.setUpdatesEnabled(False)
        while self.scroll_lay.count() > 1:
            it = self.scroll_lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.scroll_host.setUpdatesEnabled(True)

    def _append_batch(self, gen: int):
        if gen != self._render_gen or self.file_ctrl.current is None:
            return
        chat = self.file_ctrl.current
        t = THEMES[self.theme_name]
        status = lambda s: self.statusBar().showMessage(s, 4000)

        start = self._render_next
        end = min(start + VIEW_BATCH, len(chat.messages))
        self.scroll_host.setUpdatesEnabled(False)

        for idx in range(start, end):
            msg = chat.messages[idx]
            card = MessageRenderer.create_message_card(
                msg=msg,
                num=idx + 1,
                chat=chat,
                theme=t,
                render_md=self.render_md,
                show_thoughts=self.show_thoughts,
                status_cb=status,
                project_ctrl=self.project_ctrl,
                collapse_long=self.auto_collapse_long,
                preview_chars=self.collapse_preview_chars,
                tr_func=self.tr,
                bookmark_cb=self._on_message_card_bookmark,
            )
            self.scroll_lay.insertWidget(self.scroll_lay.count() - 1, card)

        self.scroll_host.setUpdatesEnabled(True)
        self._render_next = end

    def _maybe_load_more(self):
        if self.file_ctrl.current is None or self.tabs.currentIndex() != 0:
            return
        sb = self.scroll.verticalScrollBar()
        if sb.maximum() - sb.value() < 900 and self._render_next < len(self.file_ctrl.current.messages):
            self._append_batch(self._render_gen)

    def _on_virtual_copy(self, row: int, mode: str):
        if not self.file_ctrl.current or row < 0 or row >= len(self.file_ctrl.current.messages):
            return
        msg = self.file_ctrl.current.messages[row]
        CopyService.copy_message(msg, mode)
        self.statusBar().showMessage(self.tr("msg_copied"), 4000)

    def _on_message_card_bookmark(self, msg: Message, num: int):
        if not self.file_ctrl.current:
            return
        path = self.file_ctrl.current.path
        is_bm = self.project_ctrl.is_bookmarked(path, num)
        if is_bm:
            self.project_ctrl.remove_bookmark(path, num)
            self.statusBar().showMessage(self.tr("bookmark_removed", num=num), 3000)
        else:
            note, ok = QInputDialog.getText(
                self, self.tr("bookmark_add"), self.tr("bookmark_note_prompt"), text=""
            )
            if not ok:
                return
            self.project_ctrl.add_bookmark(
                path=path,
                block_num=num,
                role=msg.role,
                title=self.file_ctrl.current.title,
                note=note.strip(),
                snippet=msg.text[:200],
            )
            self.statusBar().showMessage(self.tr("bookmark_added", num=num), 3000)
        self._mark_all_tabs_dirty()
        self._refresh_file_list_ui()

    def _toggle_bookmark_active(self):
        if self.tabs.currentIndex() == 2:  # Reader tab
            self.reader_view._toggle_current_bookmark()
        elif self.file_ctrl.current and self.file_ctrl.current.messages:
            self._on_message_card_bookmark(self.file_ctrl.current.messages[0], 1)

    def _on_reader_bookmark_jump(self, path: str, block_num: int):
        self.file_ctrl.select_chat_by_path(path)
        self.tabs.setCurrentIndex(2)  # reader tab
        self.reader_view.jump_to_block(block_num)

    def open_bookmarks_dialog(self):
        dlg = BookmarkDialog(self, self.project_ctrl, self.file_ctrl.current, self.translator)
        dlg.jumpToBookmark.connect(self._on_reader_bookmark_jump)
        dlg.exec()

    # ---- Copy & Export Services ----
    def copy_chat(self, which: int):
        if not self.file_ctrl.current:
            QMessageBox.information(self, APP_NAME, self.tr("open_first"))
            return
        txt = CopyService.copy_chat(
            self.file_ctrl.current, which, self.settings, self.translator, self.show_thoughts
        )
        names = {
            COPY_ALL: self.tr("copy_all"),
            COPY_PROMPTS: self.tr("copy_prompts"),
            COPY_ANSWERS: self.tr("copy_answers"),
            COPY_THOUGHTS: self.tr("copy_thoughts"),
        }
        self.statusBar().showMessage(self.tr("copied_n", what=names.get(which, "chat"), n=len(txt)), 5000)

    def copy_raw(self):
        if not self.file_ctrl.current:
            QMessageBox.information(self, APP_NAME, self.tr("open_first"))
            return
        CopyService.copy_raw(self.file_ctrl.current)
        self.statusBar().showMessage(self.tr("source_copied"), 4000)

    def open_copy_settings(self):
        dlg = CopySettingsDialog(self, self.settings, self.tr)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.save()
            self.statusBar().showMessage(self.tr("copy_settings_saved"), 4000)

    def export_current(self):
        if not self.file_ctrl.current:
            QMessageBox.information(self, APP_NAME, self.tr("open_first"))
            return
        ExportService.export_chats(
            parent=self,
            chats=[self.file_ctrl.current],
            settings=self.settings,
            translator=self.translator,
            status_cb=lambda s: self.statusBar().showMessage(s, 5000),
        )

    def export_all(self):
        if not self.file_ctrl.chats:
            QMessageBox.information(self, APP_NAME, self.tr("list_empty"))
            return
        ExportService.export_chats(
            parent=self,
            chats=list(self.file_ctrl.chats),
            settings=self.settings,
            translator=self.translator,
            status_cb=lambda s: self.statusBar().showMessage(s, 5000),
        )

    # ---- Project & Category Operations with Undo ----
    def new_project(self):
        name, ok = QInputDialog.getText(self, APP_NAME, self.tr("project_name"))
        if not ok or not name.strip():
            return
        last_dir = self.settings.value("ui/last_dir", str(Path.home()))
        fn, _ = QFileDialog.getSaveFileName(
            self, self.tr("project_new"), str(Path(last_dir) / f"{name}.slh.json"), "Project (*.slh.json)"
        )
        if not fn:
            return
        self.project_ctrl.save_project(fn, self.file_ctrl.chats, name=name.strip())
        self.statusBar().showMessage(self.tr("project_created", name=name), 4000)

    def save_project(self):
        if not self.file_ctrl.chats:
            QMessageBox.information(self, APP_NAME, self.tr("list_empty"))
            return
        cur_path = self.project_ctrl.current_project_path
        if not cur_path:
            last_dir = self.settings.value("ui/last_dir", str(Path.home()))
            cur_path, _ = QFileDialog.getSaveFileName(
                self, self.tr("project_save"), str(Path(last_dir) / "project.slh.json"), "Project (*.slh.json)"
            )
            if not cur_path:
                return
        self.project_ctrl.save_project(cur_path, self.file_ctrl.chats)
        self.statusBar().showMessage(self.tr("project_saved", path=str(cur_path)), 4000)

    def open_project(self):
        last_dir = self.settings.value("ui/last_dir", str(Path.home()))
        fn, _ = QFileDialog.getOpenFileName(
            self, self.tr("project_open"), last_dir, "Project (*.slh.json);;All Files (*)"
        )
        if not fn:
            return
        try:
            proj, paths = self.project_ctrl.load_project(fn)
            self.load_paths(paths)
            self.statusBar().showMessage(self.tr("project_loaded", path=fn), 4000)
        except Exception as ex:
            QMessageBox.critical(self, APP_NAME, f"Failed to load project: {ex}")

    def create_category(self):
        name, ok = QInputDialog.getText(self, APP_NAME, "Название категории (поддерживается Work/Research):")
        if not ok or not name.strip():
            return
        self.project_ctrl.create_category(
            name.strip(), callback=lambda: self.statusBar().showMessage(self.tr("category_created", name=name), 4000)
        )

    def assign_category_current(self):
        if not self.file_ctrl.current:
            QMessageBox.information(self, APP_NAME, self.tr("open_first"))
            return
        cur_path = self.file_ctrl.current.path
        cats = [c[0] for c in self.project_ctrl.get_hierarchical_categories()] or [self.tr("uncategorized")]
        name, ok = QInputDialog.getItem(self, APP_NAME, self.tr("category_name"), cats, 0, True)
        if not ok or not name.strip():
            return
        self.project_ctrl.assign_category(
            cur_path, name.strip(), callback=lambda: self.statusBar().showMessage(self.tr("category_assigned", name=name), 4000)
        )
        self._refresh_file_list_ui()

    def set_tags_current(self):
        if not self.file_ctrl.current:
            QMessageBox.information(self, APP_NAME, self.tr("open_first"))
            return
        cur_path = self.file_ctrl.current.path
        old_tags = self.project_ctrl.get_tags(cur_path)
        raw, ok = QInputDialog.getText(self, APP_NAME, self.tr("tags_prompt"), text=", ".join(old_tags))
        if not ok:
            return
        tags = [t.strip().lstrip("#") for t in re.split(r"[,;]", raw) if t.strip()]
        self.project_ctrl.set_tags(
            cur_path, tags, callback=lambda: self.statusBar().showMessage(self.tr("tags_saved"), 4000)
        )
        self._refresh_filter_controls()
        self._refresh_file_list_ui()

    def set_note_current(self):
        if not self.file_ctrl.current:
            QMessageBox.information(self, APP_NAME, self.tr("open_first"))
            return
        cur_path = self.file_ctrl.current.path
        old_note = self.project_ctrl.get_note(cur_path)
        note, ok = QInputDialog.getMultiLineText(self, APP_NAME, self.tr("project_note"), old_note)
        if not ok:
            return
        self.project_ctrl.set_note(
            cur_path, note.strip(), callback=lambda: self.statusBar().showMessage(self.tr("note_saved"), 4000)
        )

    def reveal_current_file(self):
        if not self.file_ctrl.current:
            QMessageBox.information(self, APP_NAME, self.tr("open_first"))
            return
        p = Path(self.file_ctrl.current.path)
        if not p.exists():
            QMessageBox.information(self, APP_NAME, self.tr("reveal_no_file"))
            return
        reveal_in_file_manager(p)

    def open_text_separators(self):
        dlg = TextSeparatorsDialog(self, self.settings, self.tr)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.text_parse_options = dlg.options()
            self.statusBar().showMessage(self.tr("sep_saved"), 4000)

    def undo(self):
        cmd = self.undo_manager.undo()
        if cmd:
            self.statusBar().showMessage(f"Undo: {cmd.name}", 3000)
            self._refresh_filter_controls()
            self._refresh_file_list_ui()
            self._mark_all_tabs_dirty()

    def redo(self):
        cmd = self.undo_manager.redo()
        if cmd:
            self.statusBar().showMessage(f"Redo: {cmd.name}", 3000)
            self._refresh_filter_controls()
            self._refresh_file_list_ui()
            self._mark_all_tabs_dirty()

    def _show_plugins(self):
        from ..core.plugins import get_global_registry

        reg = get_global_registry()
        names = "\n".join([f"• {p.name}: {p.description}" for p in reg.plugins]) or "No plugins"
        QMessageBox.information(
            self,
            "Plugins",
            f"Loaded {len(reg.plugins)} plugins:\n\n{names}\n\nUser plugins folder: {Path.home() / '.local' / 'share' / APP_NAME / 'plugins'}",
        )

    # ---- Indexer & Hybrid Search Tab ----
    def _get_index(self) -> SearchIndex:
        if self._index is None:
            self._index = SearchIndex()
        return self._index

    def _update_index_stats(self):
        if not hasattr(self, "lbl_index_stats") or self._index is None:
            return
        try:
            st = self._index.stats()
            self.lbl_index_stats.setText(
                self.tr("index_stats", files=st["files"], msgs=st["messages"], mb=st["db_size"] / 1e6)
            )
        except Exception:
            pass

    def index_folder(self):
        last = self.settings.value("ui/index_dir", self.settings.value("ui/last_dir", str(Path.home())))
        folder = QFileDialog.getExistingDirectory(self, self.tr("dlg_open_folder"), last)
        if not folder:
            return
        self.settings.setValue("ui/index_dir", folder)

        prog = QProgressDialog(self.tr("indexing"), self.tr("cancel"), 0, 100, self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)

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
            QMessageBox.information(
                self,
                self.tr("index_done"),
                self.tr("index_done")
                + ":\n"
                + stats.summary()
                + (("\n\n" + "\n".join(stats.errors[:8])) if stats.errors else ""),
            )
        except KeyboardInterrupt:
            pass
        finally:
            prog.close()
        self._update_index_stats()

    def do_search(self):
        q = self.ed_query.text().strip()
        self.search_results.clear()
        if not q:
            return
        where = self.cmb_search_where.currentData()
        scope = self.cmb_scope.currentData()

        if where in ("current", "loaded"):
            chats = [self.file_ctrl.current] if where == "current" else list(self.file_ctrl.chats)
            if where == "current" and not self.file_ctrl.current:
                QMessageBox.information(self, APP_NAME, self.tr("open_first"))
                return

            # Выполняем гибридный поиск (FTS5 + Стемминг + Векторное сходство)
            hits = self.hybrid_engine.search_chats(chats, q, scope=scope, limit=300)
            if not hits:
                it = QListWidgetItem(self.tr("search_no_results"))
                it.setFlags(Qt.ItemFlag.NoItemFlags)
                self.search_results.addItem(it)
                return

            for h in hits:
                icon = "💭" if h.is_thought else ("👤" if h.role == "user" else "🤖")
                target_chat = next((c for c in chats if c.path == h.chat_path), None)
                badge = self.file_ctrl.format_badge(target_chat, self.tr) if target_chat else ""
                score_str = f"[{h.score:.0f}%]"
                it = QListWidgetItem(f"{icon} {h.chat_title}  ·  {badge}  ·  #{h.msg_num}  {score_str}\n{h.snippet}")
                it.setToolTip(f"{h.chat_path}\nScore: {h.score} (FTS: {h.fts_score}, Stem: {h.stem_score}, Semantic: {h.semantic_score})")
                it.setData(Qt.ItemDataRole.UserRole, (h.chat_path, "log"))
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
            index_hits = self._index.search(q, role=role, thoughts=thoughts, kind=kind, limit=300)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, str(ex))
            return

        if not index_hits:
            it = QListWidgetItem(self.tr("search_no_results"))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.search_results.addItem(it)
            return

        for h in index_hits:
            icon = "📄" if h.kind == "txt" else ("💭" if h.is_thought else ("👤" if h.role == "user" else "🤖"))
            it = QListWidgetItem(f"{icon} {h.title}  ·  {h.model or '—'}  ·  #{h.msg_num}\n{h.snippet}")
            it.setToolTip(h.path)
            it.setData(Qt.ItemDataRole.UserRole, (h.path, h.kind))
            self.search_results.addItem(it)

        self.statusBar().showMessage(self.tr("search_results_n", n=len(index_hits)), 5000)

    def _open_search_hit(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        path, kind = data if isinstance(data, tuple) else (data, "log")
        if not Path(path).exists():
            QMessageBox.warning(self, APP_NAME, f"File not found: {path}")
            return
        if kind == "txt":
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            return
        self.load_paths([path], select_path=path)
        self.tabs.setCurrentIndex(0)

    def _focus_search(self):
        if self.tabs.currentIndex() == 2:  # reader tab
            self.reader_view.focus_search()
        else:
            self.tabs.setCurrentIndex(4)
            self.ed_query.setFocus()
            self.ed_query.selectAll()

    def _quick_search(self):
        q, ok = QInputDialog.getText(self, "Quick Search", "Query (search in loaded chats):")
        if not ok or not q.strip():
            return
        self.ed_query.setText(q)
        self.cmb_search_where.setCurrentIndex(1)
        self.tabs.setCurrentIndex(4)
        self.do_search()
