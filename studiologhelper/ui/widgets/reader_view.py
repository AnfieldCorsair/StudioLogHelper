# -*- coding: utf-8 -*-
"""reader_view.py — Высокопроизводительный режим чтения («Книга») с маркерами/цитатами."""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PyQt6.QtCore import QPoint, QRect, QSettings, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QKeySequence,
    QPalette,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
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
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core.markdown import markdown_to_html
from ...core.models import ChatLog, Message
from ...core.parsers.parser import parse_file
from ...core.parsers.text_parser import parse_text_log
from ...core.project import HIGHLIGHT_COLORS, compute_text_hash
from ...indexer.stemmer import match_stemmed_query
from ..controllers.project_controller import ProjectController
from ..themes import THEMES


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
    highlights: List[Dict[str, Any]] = field(default_factory=list)


ReaderBlockCard = ReaderBlock  # Alias for backward compatibility


def _window_bounds(total: int, center_idx: int, size: int) -> Tuple[int, int]:
    """Окно блоков [start, end) вокруг center_idx для виртуализации «Книги».

    Чистая функция — тестируется без Qt. Окно никогда не выходит за границы,
    при малом total покрывает все блоки.
    """
    if total <= 0:
        return (0, 0)
    size = max(1, min(size, total))
    center_idx = max(0, min(center_idx, total - 1))
    start = max(0, center_idx - size // 2)
    end = min(total, start + size)
    start = max(0, end - size)
    return (start, end)


class ReaderView(QWidget):
    """Высокопроизводительный книжный режим чтения с маркерами цитат."""

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
        self._current_block_num: int = 1
        self._dirty: bool = True

        # Кэш body-HTML блоков: markdown/escape/highlights не зависят от темы и
        # шрифта — переиспользуются при смене настроек (A+/A−, тема, интервал).
        self._body_cache: Dict[Tuple, str] = {}
        # Debounce перерисовки: быстрые клики A+/A− не строят HTML на каждый клик
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(120)
        self._rebuild_timer.timeout.connect(self.rebuild_view)

        # Виртуализация «Книги»: рендерится только окно блоков вокруг позиции
        # чтения, остальное подгружается по скроллу/ссылкам «показать ещё».
        try:
            self.window_init = int(self.settings.value("reader/window_init", 40))
        except (ValueError, TypeError):
            self.window_init = 40
        try:
            self.window_grow = int(self.settings.value("reader/window_grow", 30))
        except (ValueError, TypeError):
            self.window_grow = 30
        self._win_start = 0
        self._win_end = 0
        self._suspend_scroll = False
        self._simple_mode = False
        self._typo_widgets: List[QWidget] = []

        # Reader Settings
        self.reader_theme_name = self.settings.value("reader/theme", "reading_warm")
        self.font_preset = self.settings.value("reader/font_family", "serif")
        try:
            self.font_size_pt = float(self.settings.value("reader/font_size", 13.0))
        except (ValueError, TypeError):
            self.font_size_pt = 13.0
        try:
            self.line_height = float(self.settings.value("reader/line_height", 1.7))
        except (ValueError, TypeError):
            self.line_height = 1.7
        self.content_width_mode = self.settings.value("reader/width_mode", "medium")
        self.render_md = self.settings.value("ui/render_md", "true") == "true"
        self.show_thoughts = self.settings.value("ui/show_thoughts", "true") == "true"

        # Search state
        self._search_matches: List[int] = []
        self._search_cur_match_idx: int = -1

        self._build_ui()
        self.project_ctrl.bookmarksChanged.connect(self._on_bookmarks_changed)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 1. Top Reading Toolbar
        tb = QFrame()
        tb.setObjectName("readerToolbar")
        tb.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tbl = QHBoxLayout(tb)
        tbl.setContentsMargins(8, 6, 8, 6)
        tbl.setSpacing(8)

        b_open_ext = QPushButton(self._tr("reader_open_file"))
        b_open_ext.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        b_open_ext.clicked.connect(self.open_external_file)
        tbl.addWidget(b_open_ext)

        tbl.addWidget(QLabel(self._tr("reader_theme")))
        self.cmb_theme = QComboBox()
        self.cmb_theme.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.cmb_theme.addItem("📜 Тёплая бумага (Solarized)", "reading_warm")
        self.cmb_theme.addItem("🕰 Винтажная сепия", "reading_sepia")
        self.cmb_theme.addItem("🌙 Ночное чтение", "reading_dark")
        self.cmb_theme.addItem("☀️ Светлая", "light")
        self.cmb_theme.addItem("🌑 Тёмная", "dark")
        i = self.cmb_theme.findData(self.reader_theme_name)
        self.cmb_theme.setCurrentIndex(i if i >= 0 else 0)
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_changed)
        tbl.addWidget(self.cmb_theme)

        self.lbl_font = QLabel("Шрифт:")
        tbl.addWidget(self.lbl_font)
        self.cmb_font = QComboBox()
        self.cmb_font.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.cmb_font.addItem("Serif (Georgia / Noto)", "serif")
        self.cmb_font.addItem("Sans (Системный)", "sans")
        self.cmb_font.addItem("Mono (Код)", "mono")
        fi = self.cmb_font.findData(self.font_preset)
        self.cmb_font.setCurrentIndex(fi if fi >= 0 else 0)
        self.cmb_font.currentIndexChanged.connect(self._on_font_changed)
        tbl.addWidget(self.cmb_font)

        b_fs_dec = QPushButton("A−")
        b_fs_dec.setMinimumWidth(28)
        b_fs_dec.clicked.connect(lambda: self._change_font_size(-1.0))
        b_fs_inc = QPushButton("A+")
        b_fs_inc.setMinimumWidth(28)
        b_fs_inc.clicked.connect(lambda: self._change_font_size(1.0))
        self.lbl_fs = QLabel(f"{self.font_size_pt:.0f}pt")
        self.lbl_fs.setMinimumWidth(32)
        self.lbl_fs.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tbl.addWidget(b_fs_dec)
        tbl.addWidget(self.lbl_fs)
        tbl.addWidget(b_fs_inc)

        self.lbl_lh = QLabel("Интервал:")
        tbl.addWidget(self.lbl_lh)
        self.cmb_lh = QComboBox()
        self.cmb_lh.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.cmb_lh.addItem("1.4x", 1.4)
        self.cmb_lh.addItem("1.7x", 1.7)
        self.cmb_lh.addItem("2.0x", 2.0)
        lhi = self.cmb_lh.findData(self.line_height)
        self.cmb_lh.setCurrentIndex(lhi if lhi >= 0 else 1)
        self.cmb_lh.currentIndexChanged.connect(self._on_lh_changed)
        tbl.addWidget(self.cmb_lh)

        self.lbl_width = QLabel("Ширина:")
        tbl.addWidget(self.lbl_width)
        self.cmb_width = QComboBox()
        self.cmb_width.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.cmb_width.addItem("740px", "compact")
        self.cmb_width.addItem("920px", "medium")
        self.cmb_width.addItem("100%", "full")
        wi = self.cmb_width.findData(self.content_width_mode)
        self.cmb_width.setCurrentIndex(wi if wi >= 0 else 1)
        self.cmb_width.currentIndexChanged.connect(self._on_width_changed)
        tbl.addWidget(self.cmb_width)

        # Виджеты типографики — скрываются в простом режиме UI
        self._typo_widgets = [self.lbl_font, self.cmb_font, self.lbl_lh, self.cmb_lh, self.lbl_width, self.cmb_width]

        tbl.addStretch(1)

        # Выделить цитату маркером (меню быстрых цветов)
        self.btn_highlight = QToolButton()
        self.btn_highlight.setText("🖍 Маркер ▾")
        self.btn_highlight.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        hm = QMenu(self.btn_highlight)
        hm.addAction("🟡 Жёлтый маркер", lambda: self.highlight_selection("yellow"))
        hm.addAction("🟢 Зелёный маркер", lambda: self.highlight_selection("green"))
        hm.addAction("🌸 Розовый маркер", lambda: self.highlight_selection("pink"))
        hm.addAction("🔵 Голубой маркер", lambda: self.highlight_selection("blue"))
        hm.addSeparator()
        hm.addAction("🗑 Снять выделение", self.clear_selected_highlight)
        self.btn_highlight.setMenu(hm)
        tbl.addWidget(self.btn_highlight)

        self.btn_tb_bm = QPushButton(self._tr("bookmark_toggle"))
        self.btn_tb_bm.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.btn_tb_bm.clicked.connect(self._toggle_current_bookmark)
        tbl.addWidget(self.btn_tb_bm)

        b_prev = QPushButton(self._tr("reader_prev_block"))
        b_prev.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        b_prev.clicked.connect(self.prev_block)
        b_next = QPushButton(self._tr("reader_next_block"))
        b_next.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        b_next.clicked.connect(self.next_block)
        tbl.addWidget(b_prev)
        tbl.addWidget(b_next)

        root.addWidget(tb)

        # 2. Smart Search Bar
        self.search_bar_widget = QFrame()
        self.search_bar_widget.setObjectName("readerToolbar")
        sbl = QHBoxLayout(self.search_bar_widget)
        sbl.setContentsMargins(8, 4, 8, 4)
        sbl.setSpacing(6)

        sbl.addWidget(QLabel("🔎 Поиск по смыслу:"))
        self.ed_reader_search = QLineEdit()
        self.ed_reader_search.setPlaceholderText(self._tr("reader_find_placeholder"))
        self.ed_reader_search.returnPressed.connect(self._do_smart_search)
        self.ed_reader_search.textChanged.connect(self._on_search_text_changed)
        sbl.addWidget(self.ed_reader_search, 1)

        b_find = QPushButton(self._tr("search_btn"))
        b_find.setObjectName("accent")
        b_find.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        b_find.clicked.connect(self._do_smart_search)
        sbl.addWidget(b_find)

        self.lbl_search_count = QLabel("")
        self.lbl_search_count.setObjectName("muted")
        sbl.addWidget(self.lbl_search_count)

        b_prev_match = QPushButton("▲")
        b_prev_match.setToolTip("Предыдущее совпадение")
        b_prev_match.setMinimumWidth(26)
        b_prev_match.clicked.connect(self._prev_search_match)
        b_next_match = QPushButton("▼")
        b_next_match.setToolTip("Следующее совпадение")
        b_next_match.setMinimumWidth(26)
        b_next_match.clicked.connect(self._next_search_match)
        sbl.addWidget(b_prev_match)
        sbl.addWidget(b_next_match)

        root.addWidget(self.search_bar_widget)

        # 3. Splitter: Left TOC/Quotes, Right Browser
        split = QSplitter(Qt.Orientation.Horizontal)

        toc_widget = QWidget()
        tl = QVBoxLayout(toc_widget)
        tl.setContentsMargins(6, 6, 6, 6)
        tl.setSpacing(6)

        toc_hdr = QHBoxLayout()
        self.lbl_toc_title = QLabel(self._tr("reader_toc"))
        self.lbl_toc_title.setStyleSheet("font-weight: bold;")
        toc_hdr.addWidget(self.lbl_toc_title)
        toc_hdr.addStretch(1)

        self.btn_toc_mode = QPushButton("Все / 🔖 Закладки и Цитаты")
        self.btn_toc_mode.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.btn_toc_mode.setCheckable(True)
        self.btn_toc_mode.toggled.connect(self._refresh_toc)
        toc_hdr.addWidget(self.btn_toc_mode)
        tl.addLayout(toc_hdr)

        self.toc_list = QListWidget()
        self.toc_list.itemClicked.connect(self._on_toc_item_clicked)
        tl.addWidget(self.toc_list, 1)

        split.addWidget(toc_widget)

        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._on_anchor_clicked)
        self.browser.verticalScrollBar().valueChanged.connect(self._on_browser_scroll)
        self.browser.setReadOnly(True)
        self.browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.browser.customContextMenuRequested.connect(self._show_browser_context_menu)
        split.addWidget(self.browser)

        split.setSizes([260, 880])
        root.addWidget(split, 1)

        # 4. Bottom status bar
        bot = QFrame()
        bot.setObjectName("readerToolbar")
        bot.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bl = QHBoxLayout(bot)
        bl.setContentsMargins(10, 4, 10, 4)

        self.lbl_progress = QLabel(self._tr("reader_block_info", cur=0, total=0))
        bl.addWidget(self.lbl_progress)
        bl.addStretch(1)

        b_exp_clean = QPushButton(self._tr("reader_export_clean"))
        b_exp_clean.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        b_exp_clean.clicked.connect(self._export_clean_reader_text)
        bl.addWidget(b_exp_clean)

        root.addWidget(bot)

    def _get_font_family_css(self) -> str:
        if self.font_preset == "serif":
            return 'Georgia, "Noto Serif", "Merriweather", "PT Serif", "Times New Roman", serif'
        elif self.font_preset == "mono":
            return 'Consolas, "Fira Code", "Courier New", monospace'
        return '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif'

    def _get_max_width_css(self) -> str:
        if self.content_width_mode == "compact":
            return "740px"
        elif self.content_width_mode == "medium":
            return "920px"
        return "100%"

    def _on_anchor_clicked(self, url: QUrl):
        url_str = url.toString()
        if url_str.startswith("#") or url.hasFragment():
            frag = url.fragment() or url_str.lstrip("#")
            # Ссылки виртуализации: догрузка блоков выше/ниже окна
            if frag in ("more_up", "more_down"):
                self._grow_window(down=(frag == "more_down"))
                return
            self.browser.scrollToAnchor(frag)
            m = re.search(r"block_(\d+)", frag)
            if m:
                self._current_block_num = int(m.group(1))
                self.lbl_progress.setText(
                    self._tr("reader_block_info", cur=self._current_block_num, total=len(self.blocks))
                )
        else:
            QDesktopServices.openUrl(url)

    def set_chat(self, chat: Optional[ChatLog]):
        self.current_chat = chat
        self.current_file_path = chat.path if chat else ""
        self._search_matches.clear()
        self._search_cur_match_idx = -1
        self.lbl_search_count.setText("")
        self._load_blocks_from_chat()
        self._dirty = True
        # Новый чат — окно виртуализации от начала
        self._win_start, self._win_end = _window_bounds(len(self.blocks), 0, self.window_init)
        if self.blocks:
            self._current_block_num = self.blocks[0].num
        self.rebuild_view(scroll_mode="top")

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
        except Exception:
            raw = p.read_text(encoding="utf-8", errors="replace")
            chat = parse_text_log(raw, filename=p.name)
            chat.path = str(p)
            self.set_chat(chat)

    def _load_blocks_from_chat(self):
        self.blocks.clear()
        self._body_cache.clear()  # тексты/цитаты изменились — кэш body недействителен
        if not self.current_chat:
            return

        path = self.current_chat.path
        bms = self.project_ctrl.get_bookmarks(path)
        hls = self.project_ctrl.get_highlights(path)

        # O(n+m) через карты вместо линейного сканирования на каждый блок
        bm_nums = {b.get("block_num") for b in bms}
        hl_map: Dict[int, List[Dict[str, Any]]] = {}
        for h in hls:
            hl_map.setdefault(h.get("block_num"), []).append(h)

        def get_block_highlights(num: int) -> List[Dict[str, Any]]:
            return hl_map.get(num, [])

        def is_block_bm(num: int) -> bool:
            return num in bm_nums

        if self.current_chat.system_instruction:
            self.blocks.append(
                ReaderBlock(
                    num=0,
                    role="system",
                    is_user=False,
                    model=self.current_chat.model,
                    text=self.current_chat.system_instruction,
                    is_bookmarked=is_block_bm(0),
                    highlights=get_block_highlights(0),
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
                    is_bookmarked=is_block_bm(i),
                    highlights=get_block_highlights(i),
                )
            )

    def _apply_highlights_to_text(self, text: str, highlights: List[Dict[str, Any]], is_markdown: bool) -> str:
        """
        Применяет маркеры к тексту с гарантией HTML-экранирования всех фрагментов
        и предотвращением конфликтов между разными цитатами.
        """
        if not highlights or not text:
            return markdown_to_html(text) if is_markdown else _html.escape(text).replace("\n", "<br/>")

        # 1. Поиск точных непересекающихся диапазонов в тексте
        resolved_spans: List[Tuple[int, int, str, str, str]] = []  # start, end, color_key, note, quote
        occupied_indices: Set[int] = set()

        for h in highlights:
            quote = h.get("quote", "").strip()
            if not quote:
                continue
            color_key = h.get("color", "yellow")
            note = h.get("note", "")
            start = h.get("start", 0)
            end = h.get("end", 0)

            # Проверяем совпадение по сохранённым start/end
            if 0 <= start < end <= len(text) and text[start:end] == quote:
                span_range = set(range(start, end))
                if not (span_range & occupied_indices):
                    resolved_spans.append((start, end, color_key, note, quote))
                    occupied_indices.update(span_range)
                    continue

            # Иначе ищем первое свободное вхождение
            search_start = 0
            while True:
                pos = text.find(quote, search_start)
                if pos < 0:
                    break
                candidate_range = set(range(pos, pos + len(quote)))
                if not (candidate_range & occupied_indices):
                    resolved_spans.append((pos, pos + len(quote), color_key, note, quote))
                    occupied_indices.update(candidate_range)
                    break
                search_start = pos + 1

        # Сортируем диапазоны по возрастанию начальной позиции
        resolved_spans.sort(key=lambda s: s[0])

        if not is_markdown:
            # Plain-text режим: сегментная сборка с полным HTML-экранированием
            pieces: List[str] = []
            last_idx = 0
            for s_start, s_end, color_key, note, quote in resolved_spans:
                if s_start > last_idx:
                    pieces.append(_html.escape(text[last_idx:s_start]))
                c_info = HIGHLIGHT_COLORS.get(color_key, HIGHLIGHT_COLORS["yellow"])
                bg_hex = c_info["hex"]
                fg_hex = c_info["text"]
                note_attr = f' title="{_html.escape(note)}"' if note else ""
                mark_text = _html.escape(text[s_start:s_end])
                pieces.append(f'<mark style="background-color: {bg_hex}; color: {fg_hex}; padding: 2px 4px; border-radius: 4px; font-weight: 500;"{note_attr}>{mark_text}</mark>')
                last_idx = s_end
            if last_idx < len(text):
                pieces.append(_html.escape(text[last_idx:]))
            return "".join(pieces).replace("\n", "<br/>")

        else:
            # Markdown режим: получаем безопасный HTML и производим однозначную токенизированную замену
            html_out = markdown_to_html(text)
            for _, _, color_key, note, quote in resolved_spans:
                c_info = HIGHLIGHT_COLORS.get(color_key, HIGHLIGHT_COLORS["yellow"])
                bg_hex = c_info["hex"]
                fg_hex = c_info["text"]
                note_attr = f' title="{_html.escape(note)}"' if note else ""
                escaped_quote = _html.escape(quote)
                tag = f'<mark style="background-color: {bg_hex}; color: {fg_hex}; padding: 2px 4px; border-radius: 4px; font-weight: 500;"{note_attr}>{escaped_quote}</mark>'
                # Заменяем только первое совпадение
                if escaped_quote in html_out:
                    html_out = html_out.replace(escaped_quote, tag, 1)
            return html_out

    def _render_body(self, b: ReaderBlock, is_md: bool) -> str:
        """HTML тела блока с кэшированием (не зависит от темы/шрифта)."""
        if not b.text:
            return f"<i>{self._tr('empty_message')}</i>"

        if b.highlights:
            hl_sig = tuple(
                (h.get("color"), h.get("note"), h.get("start"), h.get("end"), h.get("quote"))
                for h in b.highlights
            )
        else:
            hl_sig = ()

        # id(text) стабилен: blocks держат ссылки, кэш очищается при _load_blocks_from_chat
        key = (id(b.text), len(b.text), is_md, hl_sig)
        cached = self._body_cache.get(key)
        if cached is not None:
            return cached

        if b.highlights:
            body = self._apply_highlights_to_text(b.text, b.highlights, is_md)
        elif is_md:
            body = markdown_to_html(b.text)
        else:
            body = _html.escape(b.text).replace("\n", "<br/>")

        if len(self._body_cache) > 400:
            self._body_cache.clear()
        self._body_cache[key] = body
        return body

    def _schedule_rebuild(self):
        """Debounce перерисовки: серия кликов A+/A−/тема собирается в одну."""
        self._rebuild_timer.start()

    def rebuild_view(self, scroll_mode: str = "ratio"):
        """Пересобрать видимое окно «Книги».

        scroll_mode: "ratio" — сохранить относительную позицию (смена настроек),
        "keep" — сохранить абсолютный сдвиг (догрузка вниз),
        "grow_up" — компенсировать добавленный сверху контент, "top" — с начала.
        """
        self._rebuild_timer.stop()  # отменяем отложенную перерисовку, если она была
        if not self.blocks:
            self._suspend_scroll = True
            try:
                self.browser.setHtml(
                    f"<div style='text-align:center; padding: 40px; color: #888888;'><h3>{self._tr('list_empty')}</h3></div>"
                )
            finally:
                self._suspend_scroll = False
            self.lbl_progress.setText(self._tr("reader_block_info", cur=0, total=0))
            self._refresh_toc()
            return

        # Валидация окна виртуализации
        total = len(self.blocks)
        self._win_start = max(0, min(self._win_start, total))
        self._win_end = max(self._win_start, min(self._win_end, total))
        if self._win_end - self._win_start >= total:
            self._win_start, self._win_end = 0, total
        elif self._win_end == self._win_start:
            self._win_start, self._win_end = _window_bounds(total, 0, self.window_init)

        theme = THEMES.get(self.reader_theme_name, THEMES["reading_warm"])
        font_family = self._get_font_family_css()
        max_width = self._get_max_width_css()
        font_size = f"{self.font_size_pt:.1f}pt"
        line_height = f"{self.line_height:.2f}em"

        bg_color = theme.get("bg", "#fdf6e3")
        card_bg = theme.get("card", "#fbf1c7")
        card_user_bg = theme.get("card_user", "#e8e1cb")
        text_color = theme.get("text", "#43525a")
        muted_color = theme.get("muted", "#839496")
        border_color = theme.get("border", "#d5ceb8")
        accent_color = theme.get("accent", "#b58900")
        user_color = theme.get("user", "#268bd2")
        model_color = theme.get("model", "#2aa198")
        thought_color = theme.get("thought", "#cb4b16")
        thought_bg = theme.get("thought_bg", "#faecc5")
        code_bg = theme.get("code_bg", "#eee8d5")
        bm_color = theme.get("bookmark", "#d33682")

        css = f"""
        <style>
            body {{
                background-color: {bg_color};
                color: {text_color};
                font-family: {font_family};
                font-size: {font_size};
                line-height: {line_height};
                margin: 0;
                padding: 16px 8px;
            }}
            .book-container {{
                max-width: {max_width};
                margin: 0 auto;
            }}
            .card {{
                background-color: {card_bg};
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 16px 20px;
                margin-bottom: 20px;
            }}
            .card-user {{
                background-color: {card_user_bg};
            }}
            .card-header {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 11pt;
                font-weight: bold;
                margin-bottom: 10px;
                padding-bottom: 6px;
                border-bottom: 1px solid {border_color};
            }}
            .role-user {{ color: {user_color}; }}
            .role-model {{ color: {model_color}; }}
            .role-sys {{ color: {muted_color}; }}
            .meta {{
                font-size: 9.5pt;
                color: {muted_color};
                font-weight: normal;
                margin-left: 10px;
            }}
            .bm-tag {{
                background-color: {bm_color};
                color: #ffffff;
                font-size: 8.5pt;
                padding: 2px 6px;
                border-radius: 4px;
                margin-left: 8px;
            }}
            .hl-tag {{
                background-color: #fff176;
                color: #333333;
                font-size: 8.5pt;
                padding: 2px 6px;
                border-radius: 4px;
                margin-left: 8px;
            }}
            .thought-box {{
                background-color: {thought_bg};
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 10px 14px;
                margin-bottom: 12px;
                font-size: 11pt;
            }}
            .thought-title {{
                color: {thought_color};
                font-weight: bold;
                margin-bottom: 6px;
            }}
            .card-body {{
                word-wrap: break-word;
            }}
            pre {{
                background-color: {code_bg};
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 10px;
                font-family: Consolas, "Courier New", monospace;
                font-size: 10pt;
                overflow-x: auto;
            }}
            code {{
                background-color: {code_bg};
                padding: 2px 4px;
                border-radius: 3px;
                font-family: Consolas, monospace;
            }}
            blockquote {{
                border-left: 4px solid {accent_color};
                margin: 8px 0;
                padding-left: 12px;
                color: {muted_color};
            }}
            a {{ color: {accent_color}; text-decoration: none; }}
        </style>
        """

        html_blocks = [f"<!DOCTYPE html><html><head>{css}</head><body><div class='book-container'>"]

        # Виртуализация: ссылки догрузки + рендер только окна блоков
        if self._win_start > 0:
            html_blocks.append(
                "<div style='text-align:center; margin: 12px;'>"
                f"<a href='#more_up'>↑ Показать предыдущие {self._win_start} блок(ов)</a></div>"
            )

        for b in self.blocks[self._win_start : self._win_end]:
            is_user = b.is_user
            card_cls = "card card-user" if is_user else "card"
            role_cls = "role-user" if is_user else ("role-model" if b.role == "model" else "role-sys")
            role_title = (
                self._tr("user")
                if is_user
                else (self._tr("system_instruction") if b.role == "system" else (b.model or self._tr("model")))
            )

            bm_html = f"<span class='bm-tag'>🔖 {self._tr('reader_bookmarks')}</span>" if b.is_bookmarked else ""
            if b.highlights:
                bm_html += f" <span class='hl-tag'>🖍 Цитат: {len(b.highlights)}</span>"

            meta_parts = []
            if b.token_count:
                meta_parts.append(f"{b.token_count} {self._tr('tokens_short')}")
            if b.time_str:
                meta_parts.append(b.time_str)
            meta_html = f"<span class='meta'>{' · '.join(meta_parts)}</span>" if meta_parts else ""

            # Thoughts HTML
            thought_html = ""
            if self.show_thoughts and b.thoughts:
                t_joined = _html.escape("\n\n".join(t.strip() for t in b.thoughts)).replace("\n", "<br/>")
                thought_html = f"""
                <div class='thought-box'>
                    <div class='thought-title'>💭 {self._tr('thoughts_n', n=len(b.thoughts))}</div>
                    {t_joined}
                </div>
                """

            # Attachments
            att_html = ""
            if b.attachments:
                att_items = "".join(f"<div>📎 {_html.escape(a)}</div>" for a in b.attachments)
                att_html = f"<div style='color:{muted_color}; margin-bottom:8px; font-size:10pt;'>{att_items}</div>"

            # Body text with Highlights (кэшируется: markdown/escape не зависят
            # от темы и шрифта — пересобирается только при смене блоков/цитат)
            is_md = self.render_md and not is_user
            body_content = self._render_body(b, is_md)

            block_html = f"""
            <div class='{card_cls}'>
                <a name='block_{b.num}'></a>
                <div class='card-header'>
                    <span class='{role_cls}'>#{b.num} · {role_title}</span>
                    {meta_html}
                    {bm_html}
                </div>
                {thought_html}
                {att_html}
                <div class='card-body'>
                    {body_content}
                </div>
            </div>
            """
            html_blocks.append(block_html)

        if self._win_end < total:
            html_blocks.append(
                "<div style='text-align:center; margin: 12px;'>"
                f"<a href='#more_down'>↓ Показать следующие {total - self._win_end} блок(ов)</a></div>"
            )

        html_blocks.append("</div></body></html>")
        full_html = "".join(html_blocks)

        # Сохранение позиции чтения при пересборке окна
        sb = self.browser.verticalScrollBar()
        old_val, old_max = sb.value(), sb.maximum()
        self._suspend_scroll = True
        try:
            self.browser.setHtml(full_html)
            new_max = sb.maximum()
            if scroll_mode == "keep":
                sb.setValue(min(old_val, new_max))
            elif scroll_mode == "grow_up":
                sb.setValue(min(old_val + max(0, new_max - old_max), new_max))
            elif scroll_mode == "ratio" and old_max > 0 and new_max > 0:
                sb.setValue(int(new_max * old_val / old_max))
            # "top" — оставляем начало документа
        finally:
            self._suspend_scroll = False

        self.lbl_progress.setText(
            self._tr("reader_block_info", cur=self._current_block_num, total=len(self.blocks))
        )
        self._refresh_toc()
        self._dirty = False

    def _refresh_toc(self):
        self.toc_list.clear()
        only_bms = self.btn_toc_mode.isChecked()

        for b in self.blocks:
            has_bm_or_hl = b.is_bookmarked or bool(b.highlights)
            if only_bms and not has_bm_or_hl:
                continue

            icon = "🔖 " if b.is_bookmarked else ("🖍 " if b.highlights else ("👤 " if b.is_user else "🤖 "))
            role_txt = (
                self._tr("user")
                if b.is_user
                else (self._tr("system_instruction") if b.role == "system" else (b.model or self._tr("model")))
            )

            if b.highlights:
                quote_preview = b.highlights[0].get("quote", "")[:45]
                item_label = f"{icon}#{b.num} {role_txt} · «{quote_preview}…»"
            else:
                snippet = b.text.strip().replace("\n", " ")[:45]
                if not snippet:
                    snippet = self._tr("empty_message")
                item_label = f"{icon}#{b.num} {role_txt}\n   {snippet}"

            item = QListWidgetItem(item_label)
            item.setData(Qt.ItemDataRole.UserRole, b.num)
            self.toc_list.addItem(item)

        if only_bms and self.toc_list.count() == 0:
            it = QListWidgetItem("Нет закладок или цитат. Выделите текст и нажмите 'Маркер'.")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.toc_list.addItem(it)

    def _on_toc_item_clicked(self, item: QListWidgetItem):
        num = item.data(Qt.ItemDataRole.UserRole)
        if num is not None:
            self.jump_to_block(num)

    def jump_to_block(self, block_num: int):
        self._current_block_num = block_num
        # Если блок вне окна виртуализации — расширяем окно вокруг него
        idx = self._block_index(block_num)
        if idx >= 0 and not (self._win_start <= idx < self._win_end):
            self._win_start, self._win_end = _window_bounds(len(self.blocks), idx, self.window_init)
            self.rebuild_view(scroll_mode="top")
        self.browser.scrollToAnchor(f"block_{block_num}")
        self.lbl_progress.setText(
            self._tr("reader_block_info", cur=block_num, total=len(self.blocks))
        )

    def _block_index(self, block_num: int) -> int:
        """Индекс блока в self.blocks по его num (или -1)."""
        for i, b in enumerate(self.blocks):
            if b.num == block_num:
                return i
        return -1

    def _on_browser_scroll(self, value: int):
        """Автодогрузка блоков при приближении к краю видимого окна."""
        if self._suspend_scroll or not self.blocks:
            return
        sb = self.browser.verticalScrollBar()
        if sb.maximum() <= 0:
            return  # весь документ помещается — догружать некуда/не нужно
        if value >= sb.maximum() - 220 and self._win_end < len(self.blocks):
            self._grow_window(down=True)
        elif value <= 220 and self._win_start > 0:
            self._grow_window(down=False)

    def _grow_window(self, down: bool):
        """Расширить окно виртуализации на window_grow блоков вниз/вверх."""
        if self._suspend_scroll:
            return
        if down and self._win_end >= len(self.blocks):
            return
        if not down and self._win_start <= 0:
            return
        n = self.window_grow
        if down:
            self._win_end = min(len(self.blocks), self._win_end + n)
            self.rebuild_view(scroll_mode="keep")
        else:
            self._win_start = max(0, self._win_start - n)
            self.rebuild_view(scroll_mode="grow_up")

    def set_simple_mode(self, on: bool):
        """Простой режим UI: скрыть настройки типографики (шрифт/интервал/ширина)."""
        self._simple_mode = on
        for w in self._typo_widgets:
            w.setVisible(not on)

    def prev_block(self):
        if not self.blocks:
            return
        target = max(self.blocks[0].num, self._current_block_num - 1)
        self.jump_to_block(target)

    def next_block(self):
        if not self.blocks:
            return
        target = min(self.blocks[-1].num, self._current_block_num + 1)
        self.jump_to_block(target)

    # ---- Highlighter & Quotes ----
    def highlight_selection(self, color: str = "yellow"):
        cursor = self.browser.textCursor()
        if not cursor.hasSelection():
            QMessageBox.information(self, "Маркер цитат", "Сначала выделите текст в окне чтения мышью.")
            return

        quote = cursor.selectedText().strip()
        if not quote:
            return

        if not self.current_chat or not self.blocks:
            return

        path = self.current_chat.path
        target_num = self._current_block_num
        target_block = next((b for b in self.blocks if b.num == target_num), None)
        source_text = target_block.text if target_block else ""

        # Вычисляем относительные координаты внутри текста целевого блока
        rel_pos = source_text.find(quote)
        start = rel_pos if rel_pos >= 0 else 0
        end = (rel_pos + len(quote)) if rel_pos >= 0 else len(quote)

        note, ok = QInputDialog.getText(
            self,
            "Цитата / Маркер",
            f"Заметка к цитате ({HIGHLIGHT_COLORS.get(color, {}).get('name', color)} маркер):",
            text="",
        )
        if not ok:
            return

        self.project_ctrl.add_highlight(
            path=path,
            block_num=target_num,
            quote=quote,
            color=color,
            start=start,
            end=end,
            title=self.current_chat.title,
            note=note.strip(),
            source_text=source_text,
        )

        self._load_blocks_from_chat()
        self.rebuild_view()
        self.jump_to_block(target_num)

    def clear_selected_highlight(self):
        cursor = self.browser.textCursor()
        quote = cursor.selectedText().strip()
        if not quote or not self.current_chat:
            return
        self.project_ctrl.remove_highlight_by_quote(self.current_chat.path, self._current_block_num, quote)
        self._load_blocks_from_chat()
        self.rebuild_view()
        self.jump_to_block(self._current_block_num)

    # ---- Bookmarks ----
    def _toggle_current_bookmark(self):
        if not self.current_chat or not self.blocks:
            return
        target_num = self._current_block_num
        target_block = next((b for b in self.blocks if b.num == target_num), None)
        if not target_block:
            target_block = self.blocks[0]
            target_num = target_block.num

        path = self.current_chat.path
        is_now_bm = not target_block.is_bookmarked

        if is_now_bm:
            note, ok = QInputDialog.getText(
                self, self._tr("bookmark_add"), self._tr("bookmark_note_prompt"), text=""
            )
            if not ok:
                return
            self.project_ctrl.add_bookmark(
                path=path,
                block_num=target_num,
                role=target_block.role,
                title=self.current_chat.title,
                note=note.strip(),
                snippet=target_block.text[:200],
            )
        else:
            self.project_ctrl.remove_bookmark(path, target_num)

        self._load_blocks_from_chat()
        self.rebuild_view()
        self.jump_to_block(target_num)

    def _on_bookmarks_changed(self, path: str):
        if self.current_chat and self.current_chat.path == path:
            self._load_blocks_from_chat()
            self.rebuild_view()

    # ---- Setting Callbacks ----
    def _on_theme_changed(self):
        self.reader_theme_name = self.cmb_theme.currentData()
        self.settings.setValue("reader/theme", self.reader_theme_name)
        self._schedule_rebuild()

    def _on_font_changed(self):
        self.font_preset = self.cmb_font.currentData()
        self.settings.setValue("reader/font_family", self.font_preset)
        self._schedule_rebuild()

    def _change_font_size(self, delta: float):
        self.font_size_pt = max(9.0, min(32.0, self.font_size_pt + delta))
        self.settings.setValue("reader/font_size", self.font_size_pt)
        self.lbl_fs.setText(f"{self.font_size_pt:.0f}pt")
        self._schedule_rebuild()

    def _on_lh_changed(self):
        self.line_height = float(self.cmb_lh.currentData() or 1.7)
        self.settings.setValue("reader/line_height", self.line_height)
        self._schedule_rebuild()

    def _on_width_changed(self):
        self.content_width_mode = self.cmb_width.currentData()
        self.settings.setValue("reader/width_mode", self.content_width_mode)
        self._schedule_rebuild()

    # ---- Smart Stemmed Search ----
    def _on_search_text_changed(self, txt: str):
        if not txt.strip():
            self._search_matches.clear()
            self._search_cur_match_idx = -1
            self.lbl_search_count.setText("")
            self.browser.setExtraSelections([])

    def _do_smart_search(self):
        query = self.ed_reader_search.text().strip()
        if not query:
            return

        self._search_matches.clear()
        for b in self.blocks:
            matched, score, spans = match_stemmed_query(query, b.text)
            if matched:
                self._search_matches.append(b.num)

        if not self._search_matches:
            self.lbl_search_count.setText(self._tr("reader_no_matches"))
            self._search_cur_match_idx = -1
            return

        self._search_cur_match_idx = 0
        self.lbl_search_count.setText(
            self._tr("reader_matches_n", cur=1, total=len(self._search_matches))
        )
        self.jump_to_block(self._search_matches[0])
        self.browser.find(query)

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

    def _show_browser_context_menu(self, pos):
        menu = self.browser.createStandardContextMenu()
        menu.addSeparator()

        hl_sub = menu.addMenu("🖍 Выделить цитату маркером")
        hl_sub.addAction("🟡 Жёлтый маркер", lambda: self.highlight_selection("yellow"))
        hl_sub.addAction("🟢 Зелёный маркер", lambda: self.highlight_selection("green"))
        hl_sub.addAction("🌸 Розовый маркер", lambda: self.highlight_selection("pink"))
        hl_sub.addAction("🔵 Голубой маркер", lambda: self.highlight_selection("blue"))
        hl_sub.addSeparator()
        hl_sub.addAction("🗑 Снять выделение", self.clear_selected_highlight)

        menu.addAction("🔖 Закладка на блок (Ctrl+B)", self._toggle_current_bookmark)
        menu.exec(self.browser.mapToGlobal(pos))

    # ---- Export Clean Text ----
    def _export_clean_reader_text(self):
        if not self.blocks:
            return
        lines = []
        for b in self.blocks:
            role_label = self._tr("user") if b.is_user else (b.model or self._tr("model"))
            lines.append(f"--- #{b.num} {role_label} ---")
            if b.highlights:
                for h in b.highlights:
                    q = h.get("quote", "")
                    n = h.get("note", "")
                    lines.append(f"> 🖍 Цитата: {q}" + (f" ({n})" if n else ""))
            if b.text.strip():
                lines.append(b.text.strip())
            lines.append("")

        text = "\n\n".join(lines)
        last_dir = self.settings.value("ui/export_dir", str(Path.home()))
        fn, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("reader_export_clean"),
            str(Path(last_dir) / "reading_book.md"),
            "Markdown (*.md);;Text (*.txt)",
        )
        if fn:
            Path(fn).write_text(text, encoding="utf-8")
            QMessageBox.information(self, "Экспорт", f"Книга сохранена: {fn}")
