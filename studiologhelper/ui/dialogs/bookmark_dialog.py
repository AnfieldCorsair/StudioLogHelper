# -*- coding: utf-8 -*-
"""BookmarkDialog — надёжное управление закладками и цитатами-маркерами по UUID."""

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
        self.resize(880, 540)

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
        all_items = self.project_ctrl.get_all_bookmarks_and_highlights()
        self.table.setRowCount(len(all_items))
        self.lbl_count.setText(f"Всего закладок и цитат: {len(all_items)}")

        for row, item in enumerate(all_items):
            path = item.get("path", "")
            num = item.get("block_num", 1)
            role = item.get("role", "")
            note = item.get("note", "")
            quote = item.get("quote", "")
            snippet = item.get("snippet", "")
            color = item.get("color", "")
            item_id = item.get("id", "")
            is_highlight = item.get("is_highlight", False)

            type_label = f"🖍 {HIGHLIGHT_COLORS.get(color, {}).get('name', 'Цитата')}" if is_highlight else "🔖 Закладка"

            it_num = QTableWidgetItem(f"#{num}")
            it_num.setData(Qt.ItemDataRole.UserRole, (path, num, is_highlight, item_id))
            it_type = QTableWidgetItem(type_label)
            it_path = QTableWidgetItem(item.get("title") or (path.split("/")[-1] if path else "—"))
            it_role = QTableWidgetItem(role or "—")
            it_note = QTableWidgetItem(note or "—")

            display_text = f"«{quote}»" if is_highlight else snippet.replace("\n", " ")[:120]
            it_snip = QTableWidgetItem(display_text)

            self.table.setItem(row, 0, it_num)
            self.table.setItem(row, 1, it_type)
            self.table.setItem(row, 2, it_path)
            self.table.setItem(row, 3, it_role)
            self.table.setItem(row, 4, it_note)
            self.table.setItem(row, 5, it_snip)

    def _get_selected_data(self) -> Optional[Tuple[str, int, bool, str]]:
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
            path, num, _, _ = data
            self.jumpToBookmark.emit(path, num)
            self.accept()

    def _on_item_double_clicked(self, item):
        self._jump_selected()

    def _delete_selected(self):
        data = self._get_selected_data()
        if not data:
            return
        path, num, is_highlight, item_id = data
        if is_highlight:
            self.project_ctrl.remove_highlight_by_id(path, item_id)
        else:
            self.project_ctrl.remove_bookmark_by_id(path, item_id)
        self._refresh()

    def _edit_note(self):
        data = self._get_selected_data()
        if not data:
            return
        path, num, is_highlight, item_id = data

        cur_note = ""
        if is_highlight:
            for h in self.project_ctrl.get_highlights(path):
                if h.get("id") == item_id:
                    cur_note = h.get("note", "")
                    break
        else:
            for b in self.project_ctrl.get_bookmarks(path):
                if b.get("id") == item_id:
                    cur_note = b.get("note", "")
                    break

        text, ok = QInputDialog.getText(self, "Заметка", self._tr("bookmark_note_prompt"), text=cur_note)
        if ok:
            if is_highlight:
                self.project_ctrl.update_highlight_note(path, item_id, text.strip())
            else:
                self.project_ctrl.update_bookmark_note(path, item_id, text.strip())
            self._refresh()

    def _copy_markdown_summary(self):
        all_items = self.project_ctrl.get_all_bookmarks_and_highlights()
        if not all_items:
            return
        lines = ["# Дайджест закладок и цитат проекта\n"]
        for item in all_items:
            is_hl = item.get("is_highlight", False)
            header_type = "Цитата" if is_hl else "Закладка"
            lines.append(f"### #{item.get('block_num')} [{header_type}] — {item.get('title', item.get('path', ''))}")
            if is_hl:
                lines.append(f"> 🖍 **Цитата:** «{item.get('quote')}»")
            if item.get("note"):
                lines.append(f"> 📝 **Заметка:** {item.get('note')}")
            if item.get("snippet") and not is_hl:
                lines.append(f"```\n{item.get('snippet')}\n```")
            lines.append("")
        from PyQt6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "Закладки и цитаты", "Дайджест скопирован в буфер в формате Markdown!")
