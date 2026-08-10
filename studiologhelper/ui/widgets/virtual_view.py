# -*- coding: utf-8 -*-
"""Полная виртуализация списка сообщений — QListView + QStyledItemDelegate + Model.

Решение для 10k+ сообщений: создает виджеты только для видимых элементов.
Рендер через QTextDocument с аппаратной точностью QRectF и кэшированием.
"""

from __future__ import annotations

import html as _html
from typing import List, Set

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt, QSize, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFontMetrics, QTextDocument, QPalette, QFont
from PyQt6.QtWidgets import QListView, QStyledItemDelegate, QMenu, QStyle, QApplication

from ...core.models import ChatLog, Message
from ...core.markdown import markdown_to_html


class MessageListModel(QAbstractListModel):
    MessageRole = Qt.ItemDataRole.UserRole + 1
    ExpandedRole = Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages: List[Message] = []
        self.chat_title: str = ""
        self.model_name: str = ""
        self.expanded: Set[int] = set()
        self.collapsed_all: bool = False
        self.preview_chars: int = 5000

    def set_chat(self, chat: ChatLog | None, collapse_long: bool = True, preview_chars: int = 5000):
        self.beginResetModel()
        if chat is None:
            self.messages = []
            self.chat_title = ""
            self.model_name = ""
        else:
            self.messages = list(chat.messages)
            self.chat_title = chat.title
            self.model_name = chat.model
        self.preview_chars = preview_chars
        self.expanded.clear()
        if not collapse_long:
            self.expanded = set(range(len(self.messages)))
        self.collapsed_all = collapse_long
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.messages)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self.messages):
            return None
        msg = self.messages[row]
        if role == self.MessageRole:
            return msg
        if role == self.ExpandedRole:
            return row in self.expanded
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"#{row+1} {msg.role} — {len(msg.text)} chars"
        return None

    def toggle_expanded(self, row: int):
        if row in self.expanded:
            self.expanded.remove(row)
        else:
            self.expanded.add(row)
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [self.ExpandedRole])

    def set_all_collapsed(self, collapsed: bool):
        self.collapsed_all = collapsed
        if collapsed:
            self.expanded.clear()
        else:
            self.expanded = set(range(len(self.messages)))
        if self.messages:
            self.dataChanged.emit(self.index(0), self.index(len(self.messages) - 1), [self.ExpandedRole])

    def is_expanded(self, row: int) -> bool:
        return row in self.expanded


class MessageDelegate(QStyledItemDelegate):
    copyRequested = pyqtSignal(int, bool)  # row, with_thoughts
    copyThoughtsOnly = pyqtSignal(int)
    toggleExpand = pyqtSignal(int)

    def __init__(self, theme: dict, render_md: bool, show_thoughts: bool, preview_chars: int = 5000, tr_func=None, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.render_md = render_md
        self.show_thoughts = show_thoughts
        self.preview_chars = preview_chars
        self.tr = tr_func or (lambda k, **kw: k)
        self._size_cache = {}
        self._doc_cache = {}

    def _get_doc(self, text: str, rich: bool, width: int) -> QTextDocument:
        key = (hash(text[:400]), rich, width, len(text))
        if key in self._doc_cache:
            return self._doc_cache[key]
        doc = QTextDocument()
        font = QApplication.font()
        doc.setDefaultFont(font)
        doc.setTextWidth(float(width))
        if rich:
            doc.setHtml(markdown_to_html(text))
        else:
            doc.setPlainText(text)
        if len(self._doc_cache) > 200:
            self._doc_cache.clear()
        self._doc_cache[key] = doc
        return doc

    def paint(self, painter: QPainter, option, index):
        msg: Message = index.data(MessageListModel.MessageRole)
        if not msg:
            return super().paint(painter, option, index)

        is_expanded = index.data(MessageListModel.ExpandedRole)
        row = index.row()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Card background
        bg_color = QColor(self.theme.get("card_user", "#1f2b3e") if msg.is_user else self.theme.get("card", "#242526"))
        border_color = QColor(self.theme.get("border", "#3e4042"))
        if option.state & QStyle.StateFlag.State_Selected:
            bg_color = QColor(self.theme.get("sel", "#2d4368"))

        rect = option.rect.adjusted(8, 6, -8, -6)
        painter.setBrush(bg_color)
        painter.setPen(border_color)
        painter.drawRoundedRect(rect, 8, 8)

        # Header
        header_rect = QRect(rect.x() + 12, rect.y() + 8, rect.width() - 24, 22)
        who = self.tr("user") if msg.is_user else (self.theme.get("model_name", "") or self.tr("model"))
        if msg.role not in ("user", "model") and msg.role:
            who = msg.role.upper()

        who_color = QColor(self.theme.get("user", "#8ab4f8") if msg.is_user else self.theme.get("model", "#81c995"))
        painter.setPen(who_color)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(header_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"#{row+1} {who}")

        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(self.theme.get("muted", "#9a9da3")))

        extra_x = header_rect.x() + 130
        if msg.token_count:
            painter.drawText(QRect(extra_x, header_rect.y(), 80, header_rect.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{msg.token_count} {self.tr('tokens_short')}")
            extra_x += 80
        if msg.time_str():
            painter.drawText(QRect(extra_x, header_rect.y(), 140, header_rect.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, msg.time_str())

        y = header_rect.bottom() + 8

        # Thoughts
        if self.show_thoughts and msg.has_thoughts:
            thought_bg = QColor(self.theme.get("thought_bg", "#332b14"))
            thought_rect = QRect(rect.x() + 12, y, rect.width() - 24, 26)
            painter.setBrush(thought_bg)
            painter.setPen(border_color)
            painter.drawRoundedRect(thought_rect, 6, 6)
            painter.setPen(QColor(self.theme.get("thought", "#fdd663")))
            painter.drawText(thought_rect.adjusted(8, 0, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.tr("thoughts_n", n=len(msg.thoughts)))
            y = thought_rect.bottom() + 6

            if is_expanded:
                thought_text = "\n\n".join(msg.thoughts)[:2000]
                doc = self._get_doc(thought_text, False, rect.width() - 40)
                doc_h = float(doc.size().height())
                painter.save()
                painter.translate(rect.x() + 18, y)
                doc.drawContents(painter, QRectF(0.0, 0.0, float(rect.width() - 40), doc_h))
                painter.restore()
                y += int(doc_h) + 6

        # Attachments
        if msg.attachments:
            for att in msg.attachments:
                att_rect = QRect(rect.x() + 12, y, rect.width() - 24, 20)
                painter.setPen(QColor(self.theme.get("muted", "#9a9da3")))
                painter.drawText(att_rect, Qt.AlignmentFlag.AlignLeft, f"📎 {att.label_key}")
                y += 20
            y += 4

        # Body text
        full_text = msg.text.strip()
        if full_text:
            is_long = len(full_text) > self.preview_chars
            display_text = full_text
            if is_long and not is_expanded:
                display_text = full_text[: self.preview_chars].rstrip() + f"\n\n… {self.tr('collapsed_tail', n=len(full_text)-self.preview_chars)} [нажмите для раскрытия]"

            rich = self.render_md and not msg.is_user
            doc_width = max(100, rect.width() - 24)
            doc = self._get_doc(display_text, rich, doc_width)
            doc_h = float(doc.size().height())

            painter.save()
            painter.setPen(QColor(self.theme.get("text", "#e4e6eb")))
            painter.translate(rect.x() + 12, y)
            # ВНИМАНИЕ: QRectF обязателен для PyQt6!
            doc.drawContents(painter, QRectF(0.0, 0.0, float(doc_width), doc_h))
            painter.restore()
            y += int(doc_h) + 6

            if is_long:
                hint_rect = QRect(rect.x() + 12, y, 220, 22)
                painter.setPen(QColor(self.theme.get("accent", "#8ab4f8")))
                label = self.tr("collapse_message") if is_expanded else self.tr("expand_message")
                painter.drawText(hint_rect, Qt.AlignmentFlag.AlignLeft, f"[{label}]")
        else:
            empty_rect = QRect(rect.x() + 12, y, rect.width() - 24, 20)
            painter.setPen(QColor(self.theme.get("muted", "#9a9da3")))
            painter.drawText(empty_rect, Qt.AlignmentFlag.AlignLeft, self.tr("empty_message"))

        painter.restore()

    def sizeHint(self, option, index):
        msg: Message = index.data(MessageListModel.MessageRole)
        if not msg:
            return QSize(400, 60)

        is_expanded = index.data(MessageListModel.ExpandedRole)
        width = option.rect.width() if option.rect.width() > 100 else 800
        key = (index.row(), is_expanded, width, len(msg.text))
        if key in self._size_cache:
            return self._size_cache[key]

        content_width = max(100, width - 40)
        h = 6 + 22 + 8  # header

        if self.show_thoughts and msg.has_thoughts:
            h += 26 + 6
            if is_expanded:
                txt = "\n\n".join(msg.thoughts)[:2000]
                doc = self._get_doc(txt, False, content_width - 16)
                h += int(doc.size().height()) + 6

        if msg.attachments:
            h += len(msg.attachments) * 20 + 4

        if msg.text.strip():
            txt = msg.text.strip()
            is_long = len(txt) > self.preview_chars
            if is_long and not is_expanded:
                txt = txt[: self.preview_chars] + "\n\n…"
            rich = self.render_md and not msg.is_user
            doc = self._get_doc(txt, rich, content_width)
            h += int(doc.size().height()) + 6
            if is_long:
                h += 22
        else:
            h += 20

        h += 12  # bottom margin
        h = max(h, 55)

        size = QSize(width, h)
        if len(self._size_cache) > 500:
            self._size_cache.clear()
        self._size_cache[key] = size
        return size

    def clear_cache(self):
        self._size_cache.clear()
        self._doc_cache.clear()


class VirtualMessageListView(QListView):
    """QListView с виртуализацией сообщений."""

    requestCopy = pyqtSignal(int, str)
    requestToggleExpand = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setUniformItemSizes(False)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.setWordWrap(True)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        msg: Message = index.data(MessageListModel.MessageRole)
        if msg and len(msg.text) > 1000:
            model = self.model()
            if isinstance(model, MessageListModel):
                model.toggle_expanded(index.row())

    def _show_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return
        msg: Message = index.data(MessageListModel.MessageRole)
        if not msg:
            return

        menu = QMenu(self)
        menu.addAction("Копировать", lambda: self.requestCopy.emit(index.row(), "normal"))
        if msg.has_thoughts:
            menu.addAction("Копировать с размышлениями", lambda: self.requestCopy.emit(index.row(), "with_thoughts"))
            menu.addAction("Копировать только размышления", lambda: self.requestCopy.emit(index.row(), "thoughts_only"))
        if len(msg.text) > 1000:
            menu.addSeparator()
            is_exp = index.data(MessageListModel.ExpandedRole)
            label = "Свернуть" if is_exp else "Развернуть"
            menu.addAction(label, lambda: self.model().toggle_expanded(index.row()) if isinstance(self.model(), MessageListModel) else None)
        menu.exec(self.mapToGlobal(pos))
