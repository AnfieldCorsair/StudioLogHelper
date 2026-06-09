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
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QToolButton, QMenu,
    QFileDialog, QMessageBox, QTabWidget, QPlainTextEdit, QScrollArea,
    QFrame, QDialog, QDialogButtonBox, QCheckBox, QComboBox, QGroupBox,
    QFormLayout, QLineEdit, QStatusBar, QSizePolicy, QProgressDialog,
)

import core


APP_NAME = "AI Studio Log Parser"
ORG = "ArenaTools"

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
        "sel": "#2d4368",
    },
    "light": {
        "bg": "#f4f5f7", "panel": "#eceef1", "card": "#ffffff",
        "card_user": "#e8f0fe", "text": "#1c1e21", "muted": "#65676b",
        "border": "#d8dadf", "accent": "#1a73e8", "user": "#1a73e8",
        "model": "#188038", "thought": "#b06000", "thought_bg": "#fef7e0",
        "code_bg": "#f0f2f5", "btn": "#e4e6eb", "btn_text": "#1c1e21",
        "sel": "#cfe0fc",
    },
}


def build_stylesheet(t: dict) -> str:
    return f"""
    QMainWindow, QDialog {{ background: {t['bg']}; }}
    QWidget {{ color: {t['text']}; font-size: 13px; }}
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
        padding: 6px 14px; font-weight: 600;
    }}
    QPushButton:hover, QToolButton:hover {{ border-color: {t['accent']}; }}
    QPushButton:disabled, QToolButton:disabled {{ color: {t['muted']}; }}
    QToolButton::menu-indicator {{ subcontrol-position: right center; }}
    QPushButton#accent {{
        background: {t['accent']}; border: none;
        color: {'#0b1325' if t is THEMES['dark'] else '#ffffff'};
    }}
    QPlainTextEdit {{
        background: {t['code_bg']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 8px;
        font-family: Consolas, "Courier New", monospace; font-size: 12.5px;
        selection-background-color: {t['sel']};
    }}
    QTabWidget::pane {{ border: 1px solid {t['border']}; border-radius: 8px; }}
    QTabBar::tab {{
        background: {t['panel']}; color: {t['muted']};
        padding: 7px 18px; border: 1px solid {t['border']};
        border-bottom: none; border-top-left-radius: 7px;
        border-top-right-radius: 7px; margin-right: 2px; font-weight: 600;
    }}
    QTabBar::tab:selected {{ background: {t['card']}; color: {t['text']}; }}
    QScrollArea {{ border: 1px solid {t['border']}; border-radius: 8px;
        background: {t['bg']}; }}
    QScrollBar:vertical {{ background: transparent; width: 11px; }}
    QScrollBar::handle:vertical {{ background: {t['border']};
        border-radius: 5px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; }}
    QScrollBar::handle:horizontal {{ background: {t['border']};
        border-radius: 5px; min-width: 30px; }}
    QComboBox, QLineEdit {{
        background: {t['panel']}; border: 1px solid {t['border']};
        border-radius: 6px; padding: 5px 8px;
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
    QFrame#thoughtBox {{ background: {t['thought_bg']};
        border: 1px solid {t['border']}; border-radius: 8px; }}
    """


# ----------------------------------------------------------------------------
# Диалог настроек экспорта
# ----------------------------------------------------------------------------

class ExportDialog(QDialog):
    def __init__(self, parent, settings: QSettings, batch_count: int = 1):
        super().__init__(parent)
        self.setWindowTitle("Настройки экспорта")
        self.setMinimumWidth(440)
        self._s = settings

        lay = QVBoxLayout(self)

        gb_fmt = QGroupBox("Формат")
        f = QFormLayout(gb_fmt)
        self.cmb_fmt = QComboBox()
        self.cmb_fmt.addItem("TXT — чистый текст", "txt")
        self.cmb_fmt.addItem("HTML — красивый просмотр в браузере", "html")
        self.cmb_fmt.addItem("Markdown (.md)", "md")
        f.addRow("Формат файла:", self.cmb_fmt)
        lay.addWidget(gb_fmt)

        gb_opt = QGroupBox("Содержимое")
        v = QVBoxLayout(gb_opt)
        self.chk_num = QCheckBox("Нумерация сообщений (#1, #2, …)")
        self.chk_time = QCheckBox("Метки времени сообщений")
        self.chk_meta = QCheckBox("Шапка: модель, параметры, статистика")
        self.chk_sys = QCheckBox("Системная инструкция (если есть)")
        self.chk_att = QCheckBox("Вложения: плейсхолдер + ссылка на Google Drive")
        self.chk_md = QCheckBox("HTML: рендерить Markdown (код, жирный, списки)")
        for w in (self.chk_num, self.chk_time, self.chk_meta,
                  self.chk_sys, self.chk_att, self.chk_md):
            v.addWidget(w)

        f2 = QFormLayout()
        self.cmb_th = QComboBox()
        self.cmb_th.addItem("Не включать", core.THOUGHTS_EXCLUDE)
        self.cmb_th.addItem("Включать в сообщения", core.THOUGHTS_INCLUDE)
        self.cmb_th.addItem("Отдельным файлом (*_thoughts)", core.THOUGHTS_SEPARATE)
        f2.addRow("Размышления модели:", self.cmb_th)
        v.addLayout(f2)
        lay.addWidget(gb_opt)

        gb_lbl = QGroupBox("Подписи ролей")
        fl = QFormLayout(gb_lbl)
        self.ed_user = QLineEdit()
        self.ed_model = QLineEdit()
        fl.addRow("Пользователь:", self.ed_user)
        fl.addRow("Модель:", self.ed_model)
        lay.addWidget(gb_lbl)

        if batch_count > 1:
            note = QLabel(f"Будет экспортировано файлов: {batch_count}")
            note.setObjectName("muted")
            lay.addWidget(note)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Экспортировать")
        bb.button(QDialogButtonBox.Cancel).setText("Отмена")
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
        self.cmb_th.setCurrentIndex(idx(self.cmb_th, s.value("exp/thoughts",
                                                             core.THOUGHTS_EXCLUDE)))
        self.chk_num.setChecked(s.value("exp/num", "true") == "true")
        self.chk_time.setChecked(s.value("exp/time", "false") == "true")
        self.chk_meta.setChecked(s.value("exp/meta", "true") == "true")
        self.chk_sys.setChecked(s.value("exp/sys", "true") == "true")
        self.chk_att.setChecked(s.value("exp/att", "true") == "true")
        self.chk_md.setChecked(s.value("exp/md", "true") == "true")
        self.ed_user.setText(s.value("exp/user_label", core.USER_LABEL))
        self.ed_model.setText(s.value("exp/model_label", core.MODEL_LABEL))

    def options(self) -> core.ExportOptions:
        s = self._s
        opts = core.ExportOptions(
            fmt=self.cmb_fmt.currentData(),
            numbering=self.chk_num.isChecked(),
            thoughts=self.cmb_th.currentData(),
            timestamps=self.chk_time.isChecked(),
            metadata=self.chk_meta.isChecked(),
            attachments=self.chk_att.isChecked(),
            system_instruction=self.chk_sys.isChecked(),
            render_markdown=self.chk_md.isChecked(),
            user_label=self.ed_user.text().strip() or core.USER_LABEL,
            model_label=self.ed_model.text().strip() or core.MODEL_LABEL,
        )
        s.setValue("exp/fmt", opts.fmt)
        s.setValue("exp/thoughts", opts.thoughts)
        s.setValue("exp/num", "true" if opts.numbering else "false")
        s.setValue("exp/time", "true" if opts.timestamps else "false")
        s.setValue("exp/meta", "true" if opts.metadata else "false")
        s.setValue("exp/sys", "true" if opts.system_instruction else "false")
        s.setValue("exp/att", "true" if opts.attachments else "false")
        s.setValue("exp/md", "true" if opts.render_markdown else "false")
        s.setValue("exp/user_label", opts.user_label)
        s.setValue("exp/model_label", opts.model_label)
        return opts


# ----------------------------------------------------------------------------
# Карточка сообщения
# ----------------------------------------------------------------------------

class MessageCard(QFrame):
    def __init__(self, msg: core.Message, num: int, theme: dict,
                 render_md: bool, show_thoughts: bool, status_cb):
        super().__init__()
        self.msg = msg
        self._status = status_cb
        self.setObjectName("msgCardUser" if msg.is_user else "msgCard")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(6)

        # шапка
        hdr = QHBoxLayout()
        who = "ПОЛЬЗОВАТЕЛЬ" if msg.is_user else "МОДЕЛЬ"
        if msg.role not in ("user", "model"):
            who = msg.role.upper()
        color = theme["user"] if msg.is_user else theme["model"]
        lbl = QLabel(f"<b style='color:{color}'>#{num} {who}</b>")
        hdr.addWidget(lbl)
        if msg.time_str():
            tl = QLabel(msg.time_str())
            tl.setObjectName("muted")
            hdr.addWidget(tl)
        if msg.token_count:
            tk = QLabel(f"{msg.token_count} ток.")
            tk.setObjectName("muted")
            hdr.addWidget(tk)
        hdr.addStretch(1)

        btn = QPushButton("Копировать")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(26)
        btn.clicked.connect(self._copy)
        hdr.addWidget(btn)
        lay.addLayout(hdr)

        # размышления
        if show_thoughts and msg.has_thoughts:
            box = QFrame()
            box.setObjectName("thoughtBox")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(10, 8, 10, 8)
            cap = QLabel(f"<b style='color:{theme['thought']}'>💭 Размышления "
                         f"({len(msg.thoughts)})</b>")
            bl.addWidget(cap)
            body = QLabel()
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextSelectableByMouse)
            joined = "\n\n".join(t.strip() for t in msg.thoughts)
            if render_md:
                body.setTextFormat(Qt.RichText)
                body.setText(core.markdown_to_html(joined))
            else:
                body.setTextFormat(Qt.PlainText)
                body.setText(joined)
            bl.addWidget(body)
            lay.addWidget(box)

        # вложения
        for a in msg.attachments:
            al = QLabel(
                f"📎 <a href='{a.url}'>{a.label} (Google Drive)</a>"
                if a.url else f"📎 {a.label}"
            )
            al.setOpenExternalLinks(True)
            al.setObjectName("muted")
            lay.addWidget(al)

        # текст
        text = msg.text.strip()
        if text:
            body = QLabel()
            body.setWordWrap(True)
            body.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
            body.setOpenExternalLinks(True)
            if render_md and not msg.is_user:
                body.setTextFormat(Qt.RichText)
                body.setText(core.markdown_to_html(text))
            else:
                body.setTextFormat(Qt.PlainText)
                body.setText(text)
            body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            lay.addWidget(body)
        elif not msg.attachments and not msg.has_thoughts:
            e = QLabel("[пустое сообщение]")
            e.setObjectName("muted")
            lay.addWidget(e)

    def _copy(self):
        QGuiApplication.clipboard().setText(
            core.message_copy_text(self.msg, include_thoughts=False))
        self._status("Сообщение скопировано в буфер обмена")


# ----------------------------------------------------------------------------
# Главное окно
# ----------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1240, 800)
        self.setAcceptDrops(True)

        self.settings = QSettings(ORG, APP_NAME)
        self.theme_name = self.settings.value("ui/theme", "dark")
        self.render_md = self.settings.value("ui/render_md", "true") == "true"
        self.show_thoughts = self.settings.value("ui/show_thoughts", "true") == "true"

        self.chats: list = []          # list[core.ChatLog]
        self.current: core.ChatLog | None = None

        self._build_ui()
        self.apply_theme()
        self.statusBar().showMessage(
            "Откройте файл лога или перетащите файлы/папку в окно")

    # ---------- UI ----------

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)

        # верхняя панель
        top = QHBoxLayout()
        b_open = QPushButton("📄 Открыть файл(ы)")
        b_open.clicked.connect(self.open_files)
        b_folder = QPushButton("📁 Открыть папку")
        b_folder.clicked.connect(self.open_folder)
        top.addWidget(b_open)
        top.addWidget(b_folder)

        self.btn_copy = QToolButton()
        self.btn_copy.setText("📋 Копировать ▾")
        self.btn_copy.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self.btn_copy)
        m.addAction("Весь чат", lambda: self.copy_chat(core.COPY_ALL))
        m.addAction("Только промты", lambda: self.copy_chat(core.COPY_PROMPTS))
        m.addAction("Только ответы", lambda: self.copy_chat(core.COPY_ANSWERS))
        self.btn_copy.setMenu(m)
        top.addWidget(self.btn_copy)

        self.btn_export = QPushButton("💾 Экспорт текущего…")
        self.btn_export.setObjectName("accent")
        self.btn_export.clicked.connect(self.export_current)
        self.btn_export_all = QPushButton("💾 Экспорт всех…")
        self.btn_export_all.clicked.connect(self.export_all)
        top.addWidget(self.btn_export)
        top.addWidget(self.btn_export_all)

        top.addStretch(1)

        self.chk_view_md = QCheckBox("Markdown")
        self.chk_view_md.setChecked(self.render_md)
        self.chk_view_md.toggled.connect(self._toggle_md)
        self.chk_view_th = QCheckBox("Размышления")
        self.chk_view_th.setChecked(self.show_thoughts)
        self.chk_view_th.toggled.connect(self._toggle_thoughts)
        top.addWidget(self.chk_view_md)
        top.addWidget(self.chk_view_th)

        self.btn_theme = QPushButton("🌙" if self.theme_name == "dark" else "☀️")
        self.btn_theme.setFixedWidth(44)
        self.btn_theme.setToolTip("Переключить тему")
        self.btn_theme.clicked.connect(self.toggle_theme)
        top.addWidget(self.btn_theme)
        root.addLayout(top)

        # сплиттер: список файлов | контент
        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        cap = QLabel("Загруженные логи")
        cap.setObjectName("muted")
        ll.addWidget(cap)
        self.file_list = QListWidget()
        self.file_list.currentRowChanged.connect(self._select_chat)
        ll.addWidget(self.file_list)
        b_clear = QPushButton("Очистить список")
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
        self.scroll_host = QWidget()
        self.scroll_lay = QVBoxLayout(self.scroll_host)
        self.scroll_lay.setContentsMargins(10, 10, 10, 10)
        self.scroll_lay.setSpacing(10)
        self.scroll_lay.addStretch(1)
        self.scroll.setWidget(self.scroll_host)
        self.tabs.addTab(self.scroll, "Чистый вид")

        # вкладка «Исходный JSON»
        raw_tab = QWidget()
        rt = QVBoxLayout(raw_tab)
        rt.setContentsMargins(6, 6, 6, 6)
        raw_bar = QHBoxLayout()
        b_copy_raw = QPushButton("Копировать JSON")
        b_copy_raw.clicked.connect(self.copy_raw)
        raw_bar.addWidget(b_copy_raw)
        raw_bar.addStretch(1)
        rt.addLayout(raw_bar)
        self.raw_view = QPlainTextEdit()
        self.raw_view.setReadOnly(True)
        rt.addWidget(self.raw_view)
        self.tabs.addTab(raw_tab, "Исходный JSON")

        rl.addWidget(self.tabs)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 940])
        root.addWidget(split)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

        # горячие клавиши
        act_open = QAction(self)
        act_open.setShortcut(QKeySequence.Open)
        act_open.triggered.connect(self.open_files)
        self.addAction(act_open)

    # ---------- темы ----------

    def apply_theme(self):
        t = THEMES[self.theme_name]
        self.setStyleSheet(build_stylesheet(t))
        self.btn_theme.setText("🌙" if self.theme_name == "dark" else "☀️")
        self._rebuild_view()

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.settings.setValue("ui/theme", self.theme_name)
        self.apply_theme()

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
            self, "Выберите файлы логов AI Studio", last,
            "Все файлы (*);;JSON (*.json)")
        if files:
            self.settings.setValue("ui/last_dir", str(Path(files[0]).parent))
            self.load_paths(files)

    def open_folder(self):
        last = self.settings.value("ui/last_dir", str(Path.home()))
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку с логами", last)
        if not folder:
            return
        self.settings.setValue("ui/last_dir", folder)
        files = core.scan_folder(folder)
        if not files:
            QMessageBox.information(
                self, APP_NAME,
                "В папке (и подпапках) не найдено файлов, похожих на логи "
                "AI Studio.\nИскал JSON с ключами chunkedPrompt / runSettings.")
            return
        self.load_paths(files)

    def load_paths(self, paths):
        if not paths:
            return
        loaded, errors = 0, []
        existing = {c.path for c in self.chats}
        prog = None
        if len(paths) > 10:
            prog = QProgressDialog("Загрузка логов…", "Отмена", 0,
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
            item = QListWidgetItem(
                f"{chat.title}\n   {chat.model or '—'} · "
                f"{len(chat.messages)} сообщ.")
            item.setToolTip(chat.path)
            self.file_list.addItem(item)
            loaded += 1
        if prog:
            prog.setValue(len(paths))

        if loaded:
            self.file_list.setCurrentRow(self.file_list.count() - 1)
        msg = f"Загружено: {loaded}"
        if errors:
            msg += f", ошибок: {len(errors)}"
            QMessageBox.warning(
                self, "Не все файлы загружены",
                "Эти файлы не распознаны как логи AI Studio:\n\n"
                + "\n".join(errors[:12])
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
            info.append(f"модель: {_html.escape(chat.model)}")
        info.append(f"сообщений: {len(chat.messages)} "
                    f"(промтов {chat.user_count} / ответов {chat.model_count})")
        if chat.thought_count:
            info.append(f"размышлений: {chat.thought_count}")
        if chat.warnings:
            info.append(f"⚠ {'; '.join(chat.warnings)}")
        self.info_label.setText(" · ".join(info))

        if chat.system_instruction:
            box = QFrame()
            box.setObjectName("msgCard")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(14, 10, 14, 12)
            cap = QLabel("<b>СИСТЕМНАЯ ИНСТРУКЦИЯ</b>")
            cap.setObjectName("muted")
            bl.addWidget(cap)
            lab = QLabel(chat.system_instruction)
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            bl.addWidget(lab)
            self.scroll_lay.insertWidget(self.scroll_lay.count() - 1, box)

        status = lambda s: self.statusBar().showMessage(s, 4000)
        for i, msg in enumerate(chat.messages, 1):
            card = MessageCard(msg, i, t, self.render_md,
                               self.show_thoughts, status)
            self.scroll_lay.insertWidget(self.scroll_lay.count() - 1, card)

        try:
            self.raw_view.setPlainText(
                json.dumps(chat.raw, ensure_ascii=False, indent=2))
        except (TypeError, ValueError):
            self.raw_view.setPlainText("<не удалось отобразить JSON>")

        QTimer.singleShot(0, lambda:
                          self.scroll.verticalScrollBar().setValue(0))

    # ---------- копирование ----------

    def _need_chat(self) -> bool:
        if self.current is None:
            QMessageBox.information(self, APP_NAME, "Сначала откройте лог.")
            return False
        return True

    def copy_chat(self, which):
        if not self._need_chat():
            return
        opts = core.ExportOptions(
            fmt="txt", metadata=False, system_instruction=False,
            thoughts=core.THOUGHTS_INCLUDE if (
                self.show_thoughts and which != core.COPY_PROMPTS)
            else core.THOUGHTS_EXCLUDE,
        )
        text = core.chat_to_clipboard_text(self.current, which, opts)
        QGuiApplication.clipboard().setText(text)
        names = {core.COPY_ALL: "Весь чат", core.COPY_PROMPTS: "Промты",
                 core.COPY_ANSWERS: "Ответы"}
        self.statusBar().showMessage(
            f"{names[which]}: скопировано {len(text)} символов", 5000)

    def copy_raw(self):
        if not self._need_chat():
            return
        QGuiApplication.clipboard().setText(self.raw_view.toPlainText())
        self.statusBar().showMessage("Исходный JSON скопирован", 4000)

    # ---------- экспорт ----------

    def export_current(self):
        if not self._need_chat():
            return
        self._export([self.current])

    def export_all(self):
        if not self.chats:
            QMessageBox.information(self, APP_NAME, "Список логов пуст.")
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
            self, "Папка для сохранения", last)
        if not out_dir:
            return
        self.settings.setValue("ui/export_dir", out_dir)

        created, errors = [], []
        for chat in chats:
            try:
                created.extend(core.export_to_files(chat, opts, out_dir))
            except (OSError, ValueError) as ex:
                errors.append(f"{chat.title}: {ex}")

        msg = f"Создано файлов: {len(created)}\nПапка: {out_dir}"
        if errors:
            msg += "\n\nОшибки:\n" + "\n".join(errors[:10])
        QMessageBox.information(self, "Экспорт завершён", msg)
        self.statusBar().showMessage(
            f"Экспортировано файлов: {len(created)}", 6000)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG)
    f = app.font()
    f.setPointSize(10)
    app.setFont(f)
    win = MainWindow()
    win.show()
    # файлы можно передать аргументами командной строки
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
