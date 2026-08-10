# -*- coding: utf-8 -*-
"""reader_view.py — Режим чтения («Книга») для очищенных TXT/MD и чат-логов.

Включает:
  - Палитры для длительного чтения (тёплая бумага #fdf6e3, сепия #f4ecd8, ночная #191a21)
  - Типографику: шрифты с засечками (Georgia/Noto Serif), настраиваемый интерлиньяж (1.6-1.8), масштаб
  - Навигацию: оглавление/блоки, быстрый переход, прогресс чтения, Ctrl+Up/Down
  - Умный поиск по смыслу и словоформам (стемминг Портера RU/EN, "фразы", префиксы)
  - Закладки (Ctrl+B) с сохранением в .slh.json проекте
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPoint, QRect, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QKeySequence, QPalette, QTextCursor, QTextDocument
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core.markdown import markdown_to_html
from ...core.models import ChatLog, Message
from ...core.parsers.parser import parse_file
from ...core.parsers.text_parser import parse_text_log
from ...indexer.stemmer import match_stemmed_query
from ..controllers.project_controller import ProjectController
from ..themes import THEMES, build_palette


@dataclass
class ReaderBlock:
    num: int
    role: str
    is_user: bool
    model: str
    text: str
    thoughts: List[str] = field(default_factory=list)
    time_str: str = ""
    token_count: int = 0
    attachments: List[str] = field(default_factory=list)
    is_bookmarked: bool = False
    widget: Optional[QFrame] = None


class ReaderBlockCard(QFrame):
    """Карточка одного блока в книжном представлении."""

    bookmarkToggled = pyqtSignal(int)  # block_num
    copyRequested = pyqtSignal(int)  # block_num

    def __init__(
        self,
        block: ReaderBlock,
        palette_theme: dict,
        font_family: str,
        font_size_pt: float,
        line_height_multiplier: float,
        render_md: bool,
        show_thoughts: bool,
        tr_func: Callable,
    ):
        super().__init__()
        self.block = block
        self._palette = palette_theme
        self._font_family = font_family
        self._font_size_pt = font_size_pt
        self._line_height = line_height_multiplier
        self._render_md = render_md
        self._show_thoughts = show_thoughts
        self._tr = tr_func

        self.setObjectName("readerCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(8)

        # Header bar
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        role_color = self._palette["user"] if self.block.is_user else self._palette["model"]
        role_label = self._tr("user") if self.block.is_user else (self.block.model or self._tr("model"))
        if self.block.role not in ("user", "model") and self.block.role:
            role_label = self.block.role.upper()

        lbl_hdr = QLabel(f"<span style='color:{role_color}; font-weight: bold;'>#{self.block.num} · {role_label}</span>")
        lbl_hdr.setTextFormat(Qt.TextFormat.RichText)
        hdr.addWidget(lbl_hdr)

        if self.block.token_count:
            tk = QLabel(f"{self.block.token_count} {self._tr('tokens_short')}")
            tk.setObjectName("muted")
            hdr.addWidget(tk)

        if self.block.time_str:
            tm = QLabel(self.block.time_str)
            tm.setObjectName("muted")
            hdr.addWidget(tm)

        hdr.addStretch(1)

        # Bookmark button
        self.btn_bm = QPushButton("🔖" if self.block.is_bookmarked else "☆")
        self.btn_bm.setToolTip(self._tr("bookmark_toggle"))
        self.btn_bm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bm.setFixedWidth(30)
        self._update_bm_style()
        self.btn_bm.clicked.connect(lambda: self.bookmarkToggled.emit(self.block.num))
        hdr.addWidget(self.btn_bm)

        # Copy button
        btn_copy = QPushButton(self._tr("copy"))
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(lambda: self.copyRequested.emit(self.block.num))
        hdr.addWidget(btn_copy)

        lay.addLayout(hdr)

        # Thoughts block if any
        if self._show_thoughts and self.block.thoughts:
            tbox = QFrame()
            tbox.setObjectName("thoughtBox")
            tbox.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            tl = QVBoxLayout(tbox)
            tl.setContentsMargins(12, 10, 12, 10)
            tl.setSpacing(6)

            tcap = QLabel(
                f"<b style='color:{self._palette['thought']}'>{self._tr('thoughts_n', n=len(self.block.thoughts))}</b>"
            )
            tcap.setTextFormat(Qt.TextFormat.RichText)
            tl.addWidget(tcap)

            thought_text = "\n\n".join(t.strip() for t in self.block.thoughts)
            t_body = QLabel(thought_text)
            t_body.setWordWrap(True)
            t_body.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
            tl.addWidget(t_body)
            lay.addWidget(tbox)

        # Attachments if any
        for att in self.block.attachments:
            al = QLabel(f"📎 {_html.escape(att)}")
            al.setObjectName("muted")
            lay.addWidget(al)

        # Main text body
        text = self.block.text.strip()
        if text:
            self.body_label = QLabel()
            self.body_label.setWordWrap(True)
            self.body_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
            self.body_label.setOpenExternalLinks(True)
            self._update_body_text()
            lay.addWidget(self.body_label)
        else:
            e = QLabel(self._tr("empty_message"))
            e.setObjectName("muted")
            lay.addWidget(e)

    def _update_bm_style(self):
        bm_color = self._palette.get("bookmark", "#f57c00")
        if self.block.is_bookmarked:
            self.btn_bm.setText("🔖")
            self.btn_bm.setStyleSheet(
                f"QPushButton {{ background: {bm_color}; color: #ffffff; font-weight: bold; border-radius: 5px; }}"
            )
        else:
            self.btn_bm.setText("☆")
            self.btn_bm.setStyleSheet("")

    def set_bookmarked(self, is_bm: bool):
        self.block.is_bookmarked = is_bm
        self._update_bm_style()

    def _update_body_text(self):
        if not hasattr(self, "body_label") or not self.block.text:
            return

        # Typography styling via inline HTML
        line_height_em = f"{self._line_height:.2f}em"
        font_family_css = self._font_family
        font_size_pt = f"{self._font_size_pt:.1f}pt"
        text_color = self._palette["text"]

        if self._render_md and not self.block.is_user:
            raw_html = markdown_to_html(self.block.text)
            styled_html = f"""
            <div style="font-family: {font_family_css}; font-size: {font_size_pt}; line-height: {line_height_em}; color: {text_color};">
                {raw_html}
            </div>
            """
            self.body_label.setTextFormat(Qt.TextFormat.RichText)
            self.body_label.setText(styled_html)
        else:
            escaped = _html.escape(self.block.text).replace("\n", "<br/>")
            styled_html = f"""
            <div style="font-family: {font_family_css}; font-size: {font_size_pt}; line-height: {line_height_em}; color: {text_color}; white-space: pre-wrap;">
                {escaped}
            </div>
            """
            self.body_label.setTextFormat(Qt.TextFormat.RichText)
            self.body_label.setText(styled_html)

    def highlight_matches(self, spans: List[Tuple[int, int]]):
        """Подсвечивает совпадения поиска в тексте блока."""
        if not hasattr(self, "body_label") or not self.block.text:
            return
        text = self.block.text
        if not spans:
            self._update_body_text()
            return

        hl_color = self._palette.get("sel", "#ffcc00")
        hl_text_color = "#000000" if "light" in self._palette.get("name_ru", "").lower() or "warm" in self._palette.get("name_ru", "").lower() else "#ffffff"

        pieces = []
        last_idx = 0
        for start, end in spans:
            pieces.append(_html.escape(text[last_idx:start]))
            match_str = _html.escape(text[start:end])
            pieces.append(f"<span style='background-color: {hl_color}; color: {hl_text_color}; font-weight: bold; padding: 1px 3px; border-radius: 3px;'>{match_str}</span>")
            last_idx = end
        pieces.append(_html.escape(text[last_idx:]))

        highlighted_html = "".join(pieces).replace("\n", "<br/>")
        font_family_css = self._font_family
        font_size_pt = f"{self._font_size_pt:.1f}pt"
        line_height_em = f"{self._line_height:.2f}em"
        text_color = self._palette["text"]

        styled_html = f"""
        <div style="font-family: {font_family_css}; font-size: {font_size_pt}; line-height: {line_height_em}; color: {text_color};">
            {highlighted_html}
        </div>
        """
        self.body_label.setTextFormat(Qt.TextFormat.RichText)
        self.body_label.setText(styled_html)


class ReaderView(QWidget):
    """Полноценный книжный режим чтения с навигацией, стемминг-поиском и закладками."""

    bookmarkJump = pyqtSignal(str, int)  # path, block_num

    def __init__(
        self,
        settings: QSettings,
        project_controller: ProjectController,
        tr_func: Callable,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.settings = settings
        self.project_ctrl = project_controller
        self._tr = tr_func

        self.current_chat: Optional[ChatLog] = None
        self.current_file_path: str = ""
        self.blocks: List[ReaderBlock] = []
        self.cards: List[ReaderBlockCard] = []

        # Reading preferences
        self.reader_theme_name = self.settings.value("reader/theme", "reading_warm")
        self.font_preset = self.settings.value("reader/font_family", "serif")
        try:
            self.font_size_pt = float(self.settings.value("reader/font_size", 12.5))
        except (ValueError, TypeError):
            self.font_size_pt = 12.5
        try:
            self.line_height = float(self.settings.value("reader/line_height", 1.7))
        except (ValueError, TypeError):
            self.line_height = 1.7
        self.content_width_mode = self.settings.value("reader/width_mode", "medium")
        self.render_md = self.settings.value("ui/render_md", "true") == "true"
        self.show_thoughts = self.settings.value("ui/show_thoughts", "true") == "true"

        # Search state
        self._search_matches: List[int] = []  # block numbers that matched
        self._search_cur_match_idx: int = -1

        self._build_ui()
        self.project_ctrl.bookmarksChanged.connect(self._on_bookmarks_changed)

    def _get_font_family_string(self) -> str:
        if self.font_preset == "serif":
            return 'Georgia, "Noto Serif", "Merriweather", "PT Serif", "Times New Roman", serif'
        elif self.font_preset == "mono":
            return 'Consolas, "Fira Code", "Courier New", monospace'
        return '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif'

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 1. Top Reading Toolbar
        tb = QFrame()
        tb.setObjectName("readerToolbar")
        tb.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tbl = QHBoxLayout(tb)
        tbl.setContentsMargins(10, 6, 10, 6)
        tbl.setSpacing(6)

        # Open external file button
        b_open_ext = QPushButton(self._tr("reader_open_file"))
        b_open_ext.clicked.connect(self.open_external_file)
        tbl.addWidget(b_open_ext)

        # Theme combo
        tbl.addWidget(QLabel(self._tr("reader_theme")))
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItem("📜 Тёплая бумага (Solarized)", "reading_warm")
        self.cmb_theme.addItem("🕰 Винтажная сепия", "reading_sepia")
        self.cmb_theme.addItem("🌙 Ночное чтение", "reading_dark")
        self.cmb_theme.addItem("☀️ Светлая", "light")
        self.cmb_theme.addItem("🌑 Тёмная", "dark")
        i = self.cmb_theme.findData(self.reader_theme_name)
        self.cmb_theme.setCurrentIndex(i if i >= 0 else 0)
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_changed)
        tbl.addWidget(self.cmb_theme)

        # Font family combo
        tbl.addWidget(QLabel("Шрифт:"))
        self.cmb_font = QComboBox()
        self.cmb_font.addItem("Serif (Georgia)", "serif")
        self.cmb_font.addItem("Sans (Системный)", "sans")
        self.cmb_font.addItem("Mono (Код)", "mono")
        fi = self.cmb_font.findData(self.font_preset)
        self.cmb_font.setCurrentIndex(fi if fi >= 0 else 0)
        self.cmb_font.currentIndexChanged.connect(self._on_font_changed)
        tbl.addWidget(self.cmb_font)

        # Font size buttons
        b_fs_dec = QPushButton("A−")
        b_fs_dec.setFixedWidth(32)
        b_fs_dec.clicked.connect(lambda: self._change_font_size(-1.0))
        b_fs_inc = QPushButton("A+")
        b_fs_inc.setFixedWidth(32)
        b_fs_inc.clicked.connect(lambda: self._change_font_size(1.0))
        self.lbl_fs = QLabel(f"{self.font_size_pt:.0f}pt")
        self.lbl_fs.setFixedWidth(36)
        self.lbl_fs.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tbl.addWidget(b_fs_dec)
        tbl.addWidget(self.lbl_fs)
        tbl.addWidget(b_fs_inc)

        # Line spacing combo
        tbl.addWidget(QLabel("Интервал:"))
        self.cmb_lh = QComboBox()
        self.cmb_lh.addItem("1.4x", 1.4)
        self.cmb_lh.addItem("1.7x", 1.7)
        self.cmb_lh.addItem("2.0x", 2.0)
        lhi = self.cmb_lh.findData(self.line_height)
        self.cmb_lh.setCurrentIndex(lhi if lhi >= 0 else 1)
        self.cmb_lh.currentIndexChanged.connect(self._on_lh_changed)
        tbl.addWidget(self.cmb_lh)

        # Width mode combo
        tbl.addWidget(QLabel("Ширина:"))
        self.cmb_width = QComboBox()
        self.cmb_width.addItem("740px", "compact")
        self.cmb_width.addItem("920px", "medium")
        self.cmb_width.addItem("100%", "full")
        wi = self.cmb_width.findData(self.content_width_mode)
        self.cmb_width.setCurrentIndex(wi if wi >= 0 else 1)
        self.cmb_width.currentIndexChanged.connect(self._on_width_changed)
        tbl.addWidget(self.cmb_width)

        tbl.addStretch(1)

        # Bookmark toggle for active block
        self.btn_tb_bm = QPushButton(self._tr("bookmark_toggle"))
        self.btn_tb_bm.clicked.connect(self._toggle_current_bookmark)
        tbl.addWidget(self.btn_tb_bm)

        # Navigation buttons
        b_prev = QPushButton(self._tr("reader_prev_block"))
        b_prev.clicked.connect(self.prev_block)
        b_next = QPushButton(self._tr("reader_next_block"))
        b_next.clicked.connect(self.next_block)
        tbl.addWidget(b_prev)
        tbl.addWidget(b_next)

        root.addWidget(tb)

        # 2. Embedded Smart Search Bar
        self.search_bar_widget = QFrame()
        self.search_bar_widget.setObjectName("readerToolbar")
        sbl = QHBoxLayout(self.search_bar_widget)
        sbl.setContentsMargins(10, 4, 10, 4)
        sbl.setSpacing(6)

        sbl.addWidget(QLabel("🔎 Поиск по смыслу:"))
        self.ed_reader_search = QLineEdit()
        self.ed_reader_search.setPlaceholderText(self._tr("reader_find_placeholder"))
        self.ed_reader_search.returnPressed.connect(self._do_smart_search)
        self.ed_reader_search.textChanged.connect(self._on_search_text_changed)
        sbl.addWidget(self.ed_reader_search, 1)

        b_find = QPushButton(self._tr("search_btn"))
        b_find.setObjectName("accent")
        b_find.clicked.connect(self._do_smart_search)
        sbl.addWidget(b_find)

        self.lbl_search_count = QLabel("")
        self.lbl_search_count.setObjectName("muted")
        sbl.addWidget(self.lbl_search_count)

        b_prev_match = QPushButton("▲")
        b_prev_match.setToolTip("Предыдущее совпадение")
        b_prev_match.setFixedWidth(28)
        b_prev_match.clicked.connect(self._prev_search_match)
        b_next_match = QPushButton("▼")
        b_next_match.setToolTip("Следующее совпадение")
        b_next_match.setFixedWidth(28)
        b_next_match.clicked.connect(self._next_search_match)
        sbl.addWidget(b_prev_match)
        sbl.addWidget(b_next_match)

        root.addWidget(self.search_bar_widget)

        # 3. Main content area: Splitter with Sidebar (TOC / Bookmarks) and Reading Canvas
        split = QSplitter(Qt.Orientation.Horizontal)

        # Left TOC / Bookmarks sidebar
        toc_widget = QWidget()
        tl = QVBoxLayout(toc_widget)
        tl.setContentsMargins(8, 8, 8, 8)
        tl.setSpacing(6)

        toc_hdr = QHBoxLayout()
        self.lbl_toc_title = QLabel(self._tr("reader_toc"))
        self.lbl_toc_title.setStyleSheet("font-weight: bold;")
        toc_hdr.addWidget(self.lbl_toc_title)
        toc_hdr.addStretch(1)

        self.btn_toc_mode = QPushButton("Все / 🔖 Закладки")
        self.btn_toc_mode.setCheckable(True)
        self.btn_toc_mode.toggled.connect(self._refresh_toc)
        toc_hdr.addWidget(self.btn_toc_mode)
        tl.addLayout(toc_hdr)

        self.toc_list = QListWidget()
        self.toc_list.itemClicked.connect(self._on_toc_item_clicked)
        tl.addWidget(self.toc_list, 1)

        split.addWidget(toc_widget)

        # Right reading canvas (scroll area with constrained max width centered)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setObjectName("readerScroll")

        self.scroll_host = QWidget()
        self.scroll_host.setObjectName("scrollHost")
        self.scroll_lay = QVBoxLayout(self.scroll_host)
        self.scroll_lay.setContentsMargins(20, 16, 20, 20)
        self.scroll_lay.setSpacing(16)
        self.scroll_lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Container for max-width constraint
        self.canvas_container = QWidget()
        self.canvas_lay = QVBoxLayout(self.canvas_container)
        self.canvas_lay.setContentsMargins(0, 0, 0, 0)
        self.canvas_lay.setSpacing(16)

        self._update_container_width()
        self.scroll_lay.addWidget(self.canvas_container)
        self.scroll_lay.addStretch(1)

        self.scroll.setWidget(self.scroll_host)
        split.addWidget(self.scroll)

        split.setSizes([260, 840])
        root.addWidget(split, 1)

        # 4. Bottom progress / block indicator bar
        bot = QFrame()
        bot.setObjectName("readerToolbar")
        bot.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bl = QHBoxLayout(bot)
        bl.setContentsMargins(12, 4, 12, 4)

        self.lbl_progress = QLabel(self._tr("reader_block_info", cur=0, total=0))
        bl.addWidget(self.lbl_progress)
        bl.addStretch(1)

        b_exp_clean = QPushButton(self._tr("reader_export_clean"))
        b_exp_clean.clicked.connect(self._export_clean_reader_text)
        bl.addWidget(b_exp_clean)

        root.addWidget(bot)

    def _update_container_width(self):
        if self.content_width_mode == "compact":
            self.canvas_container.setMaximumWidth(740)
        elif self.content_width_mode == "medium":
            self.canvas_container.setMaximumWidth(920)
        else:
            self.canvas_container.setMaximumWidth(16777215)  # full width

    # ---- Setting Callbacks ----
    def _on_theme_changed(self):
        self.reader_theme_name = self.cmb_theme.currentData()
        self.settings.setValue("reader/theme", self.reader_theme_name)
        self.rebuild_view()

    def _on_font_changed(self):
        self.font_preset = self.cmb_font.currentData()
        self.settings.setValue("reader/font_family", self.font_preset)
        self.rebuild_view()

    def _change_font_size(self, delta: float):
        self.font_size_pt = max(9.0, min(32.0, self.font_size_pt + delta))
        self.settings.setValue("reader/font_size", self.font_size_pt)
        self.lbl_fs.setText(f"{self.font_size_pt:.0f}pt")
        self.rebuild_view()

    def _on_lh_changed(self):
        self.line_height = float(self.cmb_lh.currentData() or 1.7)
        self.settings.setValue("reader/line_height", self.line_height)
        self.rebuild_view()

    def _on_width_changed(self):
        self.content_width_mode = self.cmb_width.currentData()
        self.settings.setValue("reader/width_mode", self.content_width_mode)
        self._update_container_width()

    # ---- Loading content ----
    def set_chat(self, chat: Optional[ChatLog]):
        self.current_chat = chat
        self.current_file_path = chat.path if chat else ""
        self._search_matches.clear()
        self._search_cur_match_idx = -1
        self.lbl_search_count.setText("")
        self._load_blocks_from_chat()
        self.rebuild_view()

    def open_external_file(self):
        last_dir = self.settings.value("ui/last_dir", str(Path.home()))
        fn, _ = QFileDialog.getOpenFileName(
            self,
            self._tr("reader_open_file"),
            last_dir,
            "Clean Text & Markdown (*.txt *.md *.log);;JSON (*.json);;All Files (*)",
        )
        if not fn:
            return
        self.settings.setValue("ui/last_dir", str(Path(fn).parent))
        self.load_file(fn)

    def load_file(self, file_path: str):
        p = Path(file_path)
        if not p.exists():
            return
        try:
            chat = parse_file(str(p))
            self.set_chat(chat)
        except Exception as ex:
            # Fallback to plain text split
            raw = p.read_text(encoding="utf-8", errors="replace")
            chat = parse_text_log(raw, filename=p.name)
            chat.path = str(p)
            self.set_chat(chat)

    def _load_blocks_from_chat(self):
        self.blocks.clear()
        if not self.current_chat:
            return

        path = self.current_chat.path
        bms = {b.get("block_num") for b in self.project_ctrl.get_bookmarks(path)}

        # System instruction block as block #0 if present
        if self.current_chat.system_instruction:
            self.blocks.append(
                ReaderBlock(
                    num=0,
                    role="system",
                    is_user=False,
                    model=self.current_chat.model,
                    text=f"**{self._tr('system_instruction')}:**\n\n{self.current_chat.system_instruction}",
                    is_bookmarked=(0 in bms),
                )
            )

        for i, msg in enumerate(self.current_chat.messages, 1):
            att_labels = [a.label_key for a in msg.attachments]
            self.blocks.append(
                ReaderBlock(
                    num=i,
                    role=msg.role,
                    is_user=msg.is_user,
                    model=self.current_chat.model,
                    text=msg.text,
                    thoughts=list(msg.thoughts),
                    time_str=msg.time_str(),
                    token_count=msg.token_count,
                    attachments=att_labels,
                    is_bookmarked=(i in bms),
                )
            )

    def rebuild_view(self):
        # Clear existing cards
        while self.canvas_lay.count():
            item = self.canvas_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.cards.clear()

        if not self.blocks:
            self.lbl_progress.setText(self._tr("reader_block_info", cur=0, total=0))
            self._refresh_toc()
            return

        theme = THEMES.get(self.reader_theme_name, THEMES["reading_warm"])
        font_family = self._get_font_family_string()

        for b in self.blocks:
            card = ReaderBlockCard(
                block=b,
                palette_theme=theme,
                font_family=font_family,
                font_size_pt=self.font_size_pt,
                line_height_multiplier=self.line_height,
                render_md=self.render_md,
                show_thoughts=self.show_thoughts,
                tr_func=self._tr,
            )
            card.bookmarkToggled.connect(self._on_card_bookmark_toggled)
            card.copyRequested.connect(self._on_card_copy_requested)
            b.widget = card
            self.cards.append(card)
            self.canvas_lay.addWidget(card)

        self.lbl_progress.setText(self._tr("reader_block_info", cur=1, total=len(self.blocks)))
        self._refresh_toc()

    def _refresh_toc(self):
        self.toc_list.clear()
        only_bookmarks = self.btn_toc_mode.isChecked()

        for b in self.blocks:
            if only_bookmarks and not b.is_bookmarked:
                continue

            icon = "🔖 " if b.is_bookmarked else ("👤 " if b.is_user else "🤖 ")
            role_txt = self._tr("user") if b.is_user else (b.model or self._tr("model"))
            snippet = b.text.strip().replace("\n", " ")[:60]
            if not snippet:
                snippet = self._tr("empty_message")

            item = QListWidgetItem(f"{icon}#{b.num} {role_txt}\n   {snippet}")
            item.setData(Qt.ItemDataRole.UserRole, b.num)
            self.toc_list.addItem(item)

        if only_bookmarks and self.toc_list.count() == 0:
            it = QListWidgetItem(self._tr("bookmarks_empty"))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.toc_list.addItem(it)

    def _on_toc_item_clicked(self, item: QListWidgetItem):
        num = item.data(Qt.ItemDataRole.UserRole)
        if num is not None:
            self.jump_to_block(num)

    def jump_to_block(self, block_num: int):
        target_card = None
        for card in self.cards:
            if card.block.num == block_num:
                target_card = card
                break
        if target_card:
            self.scroll.ensureWidgetVisible(target_card, 0, 50)
            self.lbl_progress.setText(self._tr("reader_block_info", cur=block_num, total=len(self.blocks)))

    # ---- Navigation ----
    def prev_block(self):
        cur_val = self.scroll.verticalScrollBar().value()
        for card in reversed(self.cards):
            card_top = card.mapTo(self.scroll_host, QPoint(0, 0)).y()
            if card_top < cur_val - 30:
                self.jump_to_block(card.block.num)
                return
        if self.cards:
            self.jump_to_block(self.cards[0].block.num)

    def next_block(self):
        cur_val = self.scroll.verticalScrollBar().value()
        for card in self.cards:
            card_top = card.mapTo(self.scroll_host, QPoint(0, 0)).y()
            if card_top > cur_val + 30:
                self.jump_to_block(card.block.num)
                return
        if self.cards:
            self.jump_to_block(self.cards[-1].block.num)

    # ---- Bookmarks Handling ----
    def _on_card_bookmark_toggled(self, block_num: int):
        if not self.current_chat:
            return
        path = self.current_chat.path
        target_block = next((b for b in self.blocks if b.num == block_num), None)
        if not target_block:
            return

        is_now_bm = not target_block.is_bookmarked
        if is_now_bm:
            note, ok = QInputDialog.getText(
                self,
                self._tr("bookmark_add"),
                self._tr("bookmark_note_prompt"),
                text="",
            )
            if not ok:
                return
            self.project_ctrl.add_bookmark(
                path=path,
                block_num=block_num,
                role=target_block.role,
                title=self.current_chat.title,
                note=note.strip(),
                snippet=target_block.text[:200],
            )
        else:
            self.project_ctrl.remove_bookmark(path, block_num)

        target_block.is_bookmarked = is_now_bm
        for card in self.cards:
            if card.block.num == block_num:
                card.set_bookmarked(is_now_bm)
        self._refresh_toc()

    def _toggle_current_bookmark(self):
        # find currently visible top block
        cur_val = self.scroll.verticalScrollBar().value()
        visible_card = self.cards[0] if self.cards else None
        for card in self.cards:
            card_top = card.mapTo(self.scroll_host, QPoint(0, 0)).y()
            if card_top >= cur_val - 20:
                visible_card = card
                break
        if visible_card:
            self._on_card_bookmark_toggled(visible_card.block.num)

    def _on_bookmarks_changed(self, path: str):
        if self.current_chat and self.current_chat.path == path:
            bms = {b.get("block_num") for b in self.project_ctrl.get_bookmarks(path)}
            for b in self.blocks:
                b.is_bookmarked = (b.num in bms)
            for card in self.cards:
                card.set_bookmarked(card.block.num in bms)
            self._refresh_toc()

    def _on_card_copy_requested(self, block_num: int):
        target = next((b for b in self.blocks if b.num == block_num), None)
        if target and target.text:
            QGuiApplication.clipboard().setText(target.text)
            if self.parent() and hasattr(self.parent(), "statusBar"):
                self.parent().statusBar().showMessage(self._tr("msg_copied"), 3000)

    # ---- Smart Stemmed Search ----
    def _on_search_text_changed(self, txt: str):
        if not txt.strip():
            self._search_matches.clear()
            self._search_cur_match_idx = -1
            self.lbl_search_count.setText("")
            for card in self.cards:
                card.highlight_matches([])

    def _do_smart_search(self):
        query = self.ed_reader_search.text().strip()
        if not query:
            return

        self._search_matches.clear()
        for card in self.cards:
            matched, score, spans = match_stemmed_query(query, card.block.text)
            if matched:
                self._search_matches.append(card.block.num)
                card.highlight_matches(spans)
            else:
                card.highlight_matches([])

        if not self._search_matches:
            self.lbl_search_count.setText(self._tr("reader_no_matches"))
            self._search_cur_match_idx = -1
            return

        self._search_cur_match_idx = 0
        self.lbl_search_count.setText(
            self._tr("reader_matches_n", cur=1, total=len(self._search_matches))
        )
        self.jump_to_block(self._search_matches[0])

    def _next_search_match(self):
        if not self._search_matches:
            return
        self._search_cur_match_idx = (self._search_cur_match_idx + 1) % len(self._search_matches)
        num = self._search_matches[self._search_cur_match_idx]
        self.lbl_search_count.setText(
            self._tr("reader_matches_n", cur=self._search_cur_match_idx + 1, total=len(self._search_matches))
        )
        self.jump_to_block(num)

    def _prev_search_match(self):
        if not self._search_matches:
            return
        self._search_cur_match_idx = (self._search_cur_match_idx - 1) % len(self._search_matches)
        num = self._search_matches[self._search_cur_match_idx]
        self.lbl_search_count.setText(
            self._tr("reader_matches_n", cur=self._search_cur_match_idx + 1, total=len(self._search_matches))
        )
        self.jump_to_block(num)

    def focus_search(self):
        self.ed_reader_search.setFocus()
        self.ed_reader_search.selectAll()

    # ---- Export Clean Reader Text ----
    def _export_clean_reader_text(self):
        if not self.blocks:
            return
        lines = []
        for b in self.blocks:
            role_label = self._tr("user") if b.is_user else (b.model or self._tr("model"))
            lines.append(f"--- #{b.num} {role_label} ---")
            if b.text.strip():
                lines.append(b.text.strip())
            lines.append("")

        text = "\n\n".join(lines)
        last_dir = self.settings.value("ui/export_dir", str(Path.home()))
        fn, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("reader_export_clean"),
            str(Path(last_dir) / "reading_export.md"),
            "Markdown (*.md);;Text (*.txt)",
        )
        if fn:
            Path(fn).write_text(text, encoding="utf-8")
            QMessageBox.information(self, "Экспорт", f"Книга сохранена: {fn}")
