# -*- coding: utf-8 -*-
"""BookmarkDialog — диалог управления закладками и цитатами-маркерами проекта."""

from __future__ import annotations

import html as _html
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.models import ChatLog, Message
from ...core.project import HIGHLIGHT_COLORS
from ...i18n.translator import Translator
from ..controllers.project_controller import ProjectController


class BookmarkDialog(QDialog):
    """Диалог просмотра, редактирования и перехода по закладкам и цитатам."""

    jumpToBookmark = pyqtSignal(str, int)  # chat_path, block_num

    def __init__(
        self,
        parent: QWidget,
        project_ctrl: ProjectController,
        current_chat: Optional[ChatLog],
        translator: Translator,
    ):
        super().__init__(parent)
        self.project_ctrl = project_ctrl
        self.current_chat = current_chat
        self._tr = translator.tr
        self.setWindowTitle(self._tr("reader_bookmarks") + " и Цитаты")
        self.resize(860, 540)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        top_bar = QHBoxLayout()
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("font-weight: bold;")
        top_bar.addWidget(self.lbl_count)
        top_bar.addStretch(1)

        b_del = QPushButton(self._tr("bookmark_remove"))
        b_del.clicked.connect(self._delete_selected)
        top_bar.addWidget(b_del)

        b_edit_note = QPushButton(self._tr("project_note"))
        b_edit_note.clicked.connect(self._edit_note)
        top_bar.addWidget(b_edit_note)

        b_export = QPushButton("📋 Скопировать дайджест (MD)")
        b_export.clicked.connect(self._copy_markdown_summary)
        top_bar.addWidget(b_export)

        lay.addLayout(top_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "#",
            "Тип",
            self._tr("category_label"),
            self._tr("user"),
            self._tr("note_label"),
            "Цитата / Текст",
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        lay.addWidget(self.table, 1)

        bottom_bar = QHBoxLayout()
        hint = QLabel("💡 Двойной клик по строке переходит к блоку в режиме чтения")
        hint.setObjectName("muted")
        bottom_bar.addWidget(hint)
        bottom_bar.addStretch(1)

        b_jump = QPushButton("Перейти")
        b_jump.setObjectName("accent")
        b_jump.clicked.connect(self._jump_selected)
        bottom_bar.addWidget(b_jump)

        b_close = QPushButton(self._tr("cancel"))
        b_close.clicked.connect(self.close)
        bottom_bar.addWidget(b_close)
        lay.addLayout(bottom_bar)

        self._refresh()

    def _refresh(self):
        all_bms = self.project_ctrl.get_all_bookmarks()
        self.table.setRowCount(len(all_bms))
        self.lbl_count.setText(f"Всего закладок и цитат: {len(all_bms)}")

        for row, bm in enumerate(all_bms):
            path = bm.get("path", "")
            num = bm.get("block_num", 1)
            role = bm.get("role", "")
            note = bm.get("note", "")
            quote = bm.get("quote", "")
            snippet = bm.get("snippet", "")
            color = bm.get("color", "")

            type_label = "🖍 Цитата" if quote else "🔖 Закладка"

            it_num = QTableWidgetItem(f"#{num}")
            it_num.setData(Qt.ItemDataRole.UserRole, (path, num, quote))
            it_type = QTableWidgetItem(type_label)
            it_path = QTableWidgetItem(bm.get("title") or (path.split("/")[-1] if path else "—"))
            it_role = QTableWidgetItem(role or "—")
            it_note = QTableWidgetItem(note or "—")

            display_text = f"«{quote}»" if quote else snippet.replace("\n", " ")[:120]
            it_snip = QTableWidgetItem(display_text)

            self.table.setItem(row, 0, it_num)
            self.table.setItem(row, 1, it_type)
            self.table.setItem(row, 2, it_path)
            self.table.setItem(row, 3, it_role)
            self.table.setItem(row, 4, it_note)
            self.table.setItem(row, 5, it_snip)

    def _get_selected_data(self) -> Optional[Tuple[str, int, str]]:
        row = self.table.currentRow()
        if row < 0:
            return None
        it = self.table.item(row, 0)
        if not it:
            return None
        return it.data(Qt.ItemDataRole.UserRole)

    def _jump_selected(self):
        data = self._get_selected_data()
        if data:
            path, num, quote = data
            self.jumpToBookmark.emit(path, num)
            self.accept()

    def _on_item_double_clicked(self, item):
        self._jump_selected()

    def _delete_selected(self):
        data = self._get_selected_data()
        if not data:
            return
        path, num, quote = data
        if quote:
            self.project_ctrl.remove_highlight(path, num, quote)
        else:
            self.project_ctrl.remove_bookmark(path, num)
        self._refresh()

    def _edit_note(self):
        data = self._get_selected_data()
        if not data:
            return
        path, num, quote = data
        bms = self.project_ctrl.get_bookmarks(path)
        cur_note = ""
        for b in bms:
            if b.get("block_num") == num and b.get("quote") == quote:
                cur_note = b.get("note", "")
                break
        text, ok = QInputDialog.getText(self, "Заметка", self._tr("bookmark_note_prompt"), text=cur_note)
        if ok:
            if quote:
                self.project_ctrl.add_highlight(path, num, quote=quote, note=text.strip())
            else:
                self.project_ctrl.add_bookmark(path, num, note=text.strip())
            self._refresh()

    def _copy_markdown_summary(self):
        all_bms = self.project_ctrl.get_all_bookmarks()
        if not all_bms:
            return
        lines = ["# Дайджест закладок и цитат проекта\n"]
        for b in all_bms:
            header_type = "Цитата" if b.get("quote") else "Закладка"
            lines.append(f"### #{b.get('block_num')} [{header_type}] — {b.get('title', b.get('path', ''))}")
            if b.get("quote"):
                lines.append(f"> 🖍 **Цитата:** «{b.get('quote')}»")
            if b.get("note"):
                lines.append(f"> 📝 **Заметка:** {b.get('note')}")
            if b.get("snippet") and not b.get("quote"):
                lines.append(f"```\n{b.get('snippet')}\n```")
            lines.append("")
        from PyQt6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "Закладки и цитаты", "Дайджест скопирован в буфер в формате Markdown!")
