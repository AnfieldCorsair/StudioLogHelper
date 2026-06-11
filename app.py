# -*- coding: utf-8 -*-
"""
AI Studio Log Parser — десктоп-приложение (PySide6) для парсинга логов
чатов Google AI Studio (JSON с Google Drive, в т.ч. файлы без расширения).

Запуск:  python app.py
"""

from __future__ import annotations

import json
import sys
import html as _html
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QToolButton, QMenu,
    QFileDialog, QMessageBox, QTabWidget, QPlainTextEdit, QScrollArea,
    QFrame, QDialog, QDialogButtonBox, QCheckBox, QComboBox, QGroupBox,
    QFormLayout, QLineEdit, QStatusBar, QSizePolicy, QProgressDialog,
)

import core
import i18n
from i18n import tr

APP_NAME = "AI Studio Log Parser"
ORG = "ArenaTools"

ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 70, 200, 10
BASE_FONT_PT = 10.0

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
    QPlainTextEdit {{
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
    QProgressDialog {{ background: {t['panel']}; }}
    """


# ----------------------------------------------------------------------------
# Диалог настроек экспорта
# ----------------------------------------------------------------------------

class ExportDialog(QDialog):
    def __init__(self, parent, settings: QSettings, batch_count: int = 1):
        super().__init__(parent)
        self.setWindowTitle(tr("exp_title"))
        self.setMinimumWidth(460)
        self._s = settings

        lay = QVBoxLayout(self)

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
        lbl = QLabel(f"<b style='color:{color}'>#{num} {_html.escape(who)}</b>")
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

        self.settings = QSettings(ORG, APP_NAME)
        self.theme_name = self.settings.value("ui/theme", "dark")
        self.render_md = self.settings.value("ui/render_md", "true") == "true"
        self.show_thoughts = self.settings.value("ui/show_thoughts", "true") == "true"
        try:
            self.zoom = int(self.settings.value("ui/zoom", 100))
        except (TypeError, ValueError):
            self.zoom = 100
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom))
        i18n.set_lang(self.settings.value("ui/lang", "ru"))

        self.chats: list = []
        self.current: core.ChatLog | None = None
        self._index = None       # ленивый SearchIndex

        self._build_ui()
        self.apply_theme()
        self.statusBar().showMessage(tr("status_hint"))

    # ---------- UI ----------

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
        b_folder = QPushButton(tr("open_folder"))
        b_folder.clicked.connect(self.open_folder)
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
        self.btn_copy.setMenu(m)
        top.addWidget(self.btn_copy)

        self.btn_export = QPushButton(tr("export_current"))
        self.btn_export.setObjectName("accent")
        self.btn_export.clicked.connect(self.export_current)
        self.btn_export_all = QPushButton(tr("export_all"))
        self.btn_export_all.clicked.connect(self.export_all)
        top.addWidget(self.btn_export)
        top.addWidget(self.btn_export_all)

        top.addStretch(1)

        self.chk_view_md = QCheckBox(tr("view_markdown"))
        self.chk_view_md.setChecked(self.render_md)
        self.chk_view_md.toggled.connect(self._toggle_md)
        self.chk_view_th = QCheckBox(tr("view_thoughts"))
        self.chk_view_th.setChecked(self.show_thoughts)
        self.chk_view_th.toggled.connect(self._toggle_thoughts)
        top.addWidget(self.chk_view_md)
        top.addWidget(self.chk_view_th)

        b_zout = QPushButton("A−")
        b_zout.setFixedWidth(40)
        b_zout.setToolTip(tr("zoom_out_tip"))
        b_zout.clicked.connect(lambda: self.set_zoom(self.zoom - ZOOM_STEP))
        b_zin = QPushButton("A+")
        b_zin.setFixedWidth(40)
        b_zin.setToolTip(tr("zoom_in_tip"))
        b_zin.clicked.connect(lambda: self.set_zoom(self.zoom + ZOOM_STEP))
        top.addWidget(b_zout)
        top.addWidget(b_zin)

        self.cmb_lang = QComboBox()
        for code, name in i18n.LANGS.items():
            self.cmb_lang.addItem(name, code)
        self.cmb_lang.setCurrentIndex(
            max(0, self.cmb_lang.findData(i18n.get_lang())))
        self.cmb_lang.setToolTip(tr("lang_tip"))
        self.cmb_lang.currentIndexChanged.connect(self._change_lang)
        top.addWidget(self.cmb_lang)

        self.btn_theme = QPushButton("🌙" if self.theme_name == "dark" else "☀️")
        self.btn_theme.setFixedWidth(44)
        self.btn_theme.setToolTip(tr("theme_tip"))
        self.btn_theme.clicked.connect(self.toggle_theme)
        top.addWidget(self.btn_theme)
        root.addLayout(top)

        # сплиттер: список файлов | контент
        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        cap = QLabel(tr("loaded_logs"))
        cap.setObjectName("muted")
        ll.addWidget(cap)
        self.file_list = QListWidget()
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
        self.tabs.addTab(self.scroll, tr("tab_clean"))

        # вкладка «Исходный JSON»
        raw_tab = QWidget()
        rt = QVBoxLayout(raw_tab)
        rt.setContentsMargins(6, 6, 6, 6)
        raw_bar = QHBoxLayout()
        b_copy_raw = QPushButton(tr("copy_json"))
        b_copy_raw.clicked.connect(self.copy_raw)
        raw_bar.addWidget(b_copy_raw)
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
        self.cmb_scope = QComboBox()
        self.cmb_scope.addItem(tr("search_scope_all"), "all")
        self.cmb_scope.addItem(tr("search_scope_user"), "user")
        self.cmb_scope.addItem(tr("search_scope_model"), "model")
        self.cmb_scope.addItem(tr("search_scope_thoughts"), "thoughts")
        self.cmb_scope.addItem(tr("search_scope_txt"), "txt")
        row1.addWidget(self.cmb_scope)
        b_search = QPushButton(tr("search_btn"))
        b_search.setObjectName("accent")
        b_search.clicked.connect(self.do_search)
        row1.addWidget(b_search)
        v.addLayout(row1)

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

    def apply_theme(self):
        t = THEMES[self.theme_name]
        scale = self.zoom / 100.0
        self.setStyleSheet(build_stylesheet(t, scale))
        f = QApplication.instance().font()
        f.setPointSizeF(BASE_FONT_PT * scale)
        QApplication.instance().setFont(f)
        self.btn_theme.setText("🌙" if self.theme_name == "dark" else "☀️")
        self._rebuild_view()
        self._update_index_stats()

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.settings.setValue("ui/theme", self.theme_name)
        self.apply_theme()

    def set_zoom(self, z: int):
        z = max(ZOOM_MIN, min(ZOOM_MAX, z))
        if z == self.zoom:
            return
        self.zoom = z
        self.settings.setValue("ui/zoom", z)
        self.apply_theme()
        self.statusBar().showMessage(f"Zoom: {z}%", 2000)

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

    def _add_list_item(self, chat: core.ChatLog):
        item = QListWidgetItem(
            f"{chat.title}\n   {chat.model or '—'} · "
            f"{len(chat.messages)} {tr('messages_short')}")
        item.setToolTip(chat.path)
        self.file_list.addItem(item)

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
                chat = core.parse_file(p)
            except (core.ParseError, OSError, ValueError) as ex:
                errors.append(f"{Path(p).name}: {ex}")
                continue
            self.chats.append(chat)
            self._add_list_item(chat)
            loaded += 1
        if prog:
            prog.setValue(len(paths))

        if select_path:
            for i, c in enumerate(self.chats):
                if c.path == select_path:
                    self.file_list.setCurrentRow(i)
                    break
        elif loaded:
            self.file_list.setCurrentRow(self.file_list.count() - 1)

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
        if row < 0 or row >= len(self.chats):
            self.current = None
            return
        self.current = self.chats[row]
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

        status = lambda s: self.statusBar().showMessage(s, 4000)
        for i, msg in enumerate(chat.messages, 1):
            card = MessageCard(msg, i, t, self.render_md,
                               self.show_thoughts, status,
                               model_name=chat.model)
            self.scroll_lay.insertWidget(self.scroll_lay.count() - 1, card)

        try:
            self.raw_view.setPlainText(
                json.dumps(chat.raw, ensure_ascii=False, indent=2))
        except (TypeError, ValueError):
            self.raw_view.setPlainText("<JSON?>")

        QTimer.singleShot(0, lambda:
                          self.scroll.verticalScrollBar().setValue(0))

    # ---------- копирование ----------

    def _need_chat(self) -> bool:
        if self.current is None:
            QMessageBox.information(self, APP_NAME, tr("open_first"))
            return False
        return True

    def copy_chat(self, which):
        if not self._need_chat():
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
        self.statusBar().showMessage(tr("json_copied"), 4000)

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
        try:
            st = self._get_index().stats()
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

    def do_search(self):
        q = self.ed_query.text().strip()
        self.search_results.clear()
        if not q:
            return
        scope = self.cmb_scope.currentData()
        role, thoughts, kind = None, None, None
        if scope == "user":
            role, thoughts = "user", False
        elif scope == "model":
            role, thoughts = "model", False
        elif scope == "thoughts":
            thoughts = True
        elif scope == "txt":
            kind = "txt"
        try:
            hits = self._get_index().search(q, role=role, thoughts=thoughts,
                                            kind=kind, limit=200)
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
