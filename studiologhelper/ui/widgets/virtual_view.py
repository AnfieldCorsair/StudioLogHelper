# -*- coding: utf-8 -*-
"""Полная виртуализация списка сообщений — QListView + QStyledItemDelegate + Model.

Это решение для 10k+ сообщений: создает виджеты только для видимых элементов.
Рендер через QTextDocument для поддержки markdown и rich text, но быстро.
"""

from __future__ import annotations

import html as _html
from typing import List, Set

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt, QSize, QRect, pyqtSignal
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
        self.expanded: Set[int] = set()  # indexes that are expanded (long messages)
        self.collapsed_all: bool = False

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
            # all expanded
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
        key = (hash(text[:500]), rich, width, text[:50])
        # simple cache
        if key in self._doc_cache:
            return self._doc_cache[key]
        doc = QTextDocument()
        doc.setDefaultFont(QApplication.font())
        doc.setTextWidth(width)
        if rich:
            doc.setHtml(markdown_to_html(text))
        else:
            doc.setPlainText(text)
        # limit cache size
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
        bg_color = QColor(self.theme["card_user"] if msg.is_user else self.theme["card"])
        border_color = QColor(self.theme["border"])
        # selection
        if option.state & QStyle.StateFlag.State_Selected:
            bg_color = QColor(self.theme["sel"])

        rect = option.rect.adjusted(8, 6, -8, -6)
        painter.setBrush(bg_color)
        painter.setPen(border_color)
        painter.drawRoundedRect(rect, 8, 8)

        # Header
        header_rect = QRect(rect.x() + 12, rect.y() + 8, rect.width() - 24, 22)
        who = self.tr("user") if msg.is_user else (self.theme.get("model_name", "") or self.tr("model"))
        # Use model name if available from model
        # Color
        who_color = QColor(self.theme["user"] if msg.is_user else self.theme["model"])
        painter.setPen(who_color)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(header_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"#{row+1} {who}")

        # Reset font
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(self.theme["muted"]))

        # token count etc.
        extra_x = header_rect.x() + 120
        if msg.token_count:
            painter.drawText(QRect(extra_x, header_rect.y(), 80, header_rect.height()), Qt.AlignmentFlag.AlignLeft, f"{msg.token_count} {self.tr('tokens_short')}")
            extra_x += 80
        if msg.time_str():
            painter.drawText(QRect(extra_x, header_rect.y(), 140, header_rect.height()), Qt.AlignmentFlag.AlignLeft, msg.time_str())

        y = header_rect.bottom() + 8

        # Thoughts
        if self.show_thoughts and msg.has_thoughts:
            thought_bg = QColor(self.theme["thought_bg"])
            thought_rect = QRect(rect.x() + 12, y, rect.width() - 24, 28)
            painter.setBrush(thought_bg)
            painter.setPen(border_color)
            painter.drawRoundedRect(thought_rect, 6, 6)
            painter.setPen(QColor(self.theme["thought"]))
            painter.drawText(thought_rect.adjusted(8, 0, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.tr("thoughts_n", n=len(msg.thoughts)))
            y = thought_rect.bottom() + 6
            # Draw first thought preview if expanded? For virtual we show placeholder
            if not is_expanded and self.show_thoughts:
                # show count only
                pass
            else:
                # show thoughts text truncated
                thought_text = "\n\n".join(msg.thoughts)[:1000]
                doc = self._get_doc(thought_text, False, rect.width() - 40)
                thought_doc_rect = QRect(rect.x() + 18, y, rect.width() - 36, int(doc.size().height()))
                painter.save()
                painter.translate(thought_doc_rect.topLeft())
                doc.drawContents(painter)
                painter.restore()
                y = thought_doc_rect.bottom() + 6

        # Attachments
        if msg.attachments:
            for att in msg.attachments:
                att_rect = QRect(rect.x() + 12, y, rect.width() - 24, 20)
                painter.setPen(QColor(self.theme["muted"]))
                painter.drawText(att_rect, Qt.AlignmentFlag.AlignLeft, f"📎 {att.label_key} {att.url[:40] if att.url else ''}")
                y += 20
            y += 4

        # Body text
        full_text = msg.text.strip()
        if full_text:
            is_long = len(full_text) > self.preview_chars
            display_text = full_text
            if is_long and not is_expanded:
                display_text = full_text[: self.preview_chars].rstrip() + f"\n\n… {self.tr('collapsed_tail', n=len(full_text)-self.preview_chars)} [click to expand]"

            rich = self.render_md and not msg.is_user
            # Limit doc width
            doc_width = rect.width() - 24
            doc = self._get_doc(display_text, rich, doc_width)
            doc_rect = QRect(rect.x() + 12, y, doc_width, int(doc.size().height()))
            painter.save()
            painter.setPen(QColor(self.theme["text"]))
            painter.translate(doc_rect.topLeft())
            # Clip to not overflow
            doc.drawContents(painter, QRect(0, 0, doc_width, doc_rect.height()))
            painter.restore()
            y = doc_rect.bottom() + 6

            if is_long:
                # Draw expand/collapse hint
                hint_rect = QRect(rect.x() + 12, y, 160, 22)
                painter.setPen(QColor(self.theme["accent"]))
                label = self.tr("collapse_message") if is_expanded else self.tr("expand_message")
                painter.drawText(hint_rect, Qt.AlignmentFlag.AlignLeft, f"[{label}]")
        else:
            # empty
            empty_rect = QRect(rect.x() + 12, y, rect.width() - 24, 20)
            painter.setPen(QColor(self.theme["muted"]))
            painter.drawText(empty_rect, Qt.AlignmentFlag.AlignLeft, self.tr("empty_message"))

        painter.restore()

    def sizeHint(self, option, index):
        msg: Message = index.data(MessageListModel.MessageRole)
        if not msg:
            return QSize(400, 60)

        is_expanded = index.data(MessageListModel.ExpandedRole)
        # Cache key
        key = (index.row(), is_expanded, option.rect.width(), msg.text[:100])
        if key in self._size_cache:
            return self._size_cache[key]

        # Estimate height
        width = option.rect.width() if option.rect.width() > 100 else 800
        content_width = width - 40  # margins

        h = 6 + 22 + 8  # header

        if self.show_thoughts and msg.has_thoughts:
            h += 28 + 6
            if is_expanded:
                # thoughts height
                txt = "\n\n".join(msg.thoughts)[:1000]
                doc = QTextDocument()
                doc.setTextWidth(content_width - 16)
                doc.setPlainText(txt)
                h += int(doc.size().height()) + 6

        if msg.attachments:
            h += len(msg.attachments) * 20 + 4

        if msg.text.strip():
            txt = msg.text.strip()
            is_long = len(txt) > self.preview_chars
            if is_long and not is_expanded:
                txt = txt[: self.preview_chars] + "\n\n…"
            # doc height
            doc = QTextDocument()
            doc.setDefaultFont(QApplication.font())
            doc.setTextWidth(content_width)
            if self.render_md and not msg.is_user:
                doc.setHtml(markdown_to_html(txt))
            else:
                doc.setPlainText(txt)
            h += int(doc.size().height()) + 6
            if len(msg.text) > self.preview_chars:
                h += 22  # expand hint
        else:
            h += 20

        h += 12  # bottom margin
        h = max(h, 60)
        # Cap max height to avoid huge
        h = min(h, 1200)

        size = QSize(width, h)
        # keep cache limited
        if len(self._size_cache) > 500:
            self._size_cache.clear()
        self._size_cache[key] = size
        return size

    def clear_cache(self):
        self._size_cache.clear()
        self._doc_cache.clear()


class VirtualMessageListView(QListView):
    """QListView with virtualized messages."""

    requestCopy = pyqtSignal(int, str)  # row, mode: "normal", "with_thoughts", "thoughts_only"
    requestToggleExpand = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setUniformItemSizes(False)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.setWordWrap(True)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        # If long message, toggle expand on click
        msg: Message = index.data(MessageListModel.MessageRole)
        if msg and len(msg.text) > 5000:  # or use delegate preview_chars
            # Check if click near expand hint — for simplicity toggle on any click if long
            # We'll emit to model
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
        menu.addAction("Copy", lambda: self.requestCopy.emit(index.row(), "normal"))
        if msg.has_thoughts:
            menu.addAction("Copy with thoughts", lambda: self.requestCopy.emit(index.row(), "with_thoughts"))
            menu.addAction("Copy thoughts only", lambda: self.requestCopy.emit(index.row(), "thoughts_only"))
        if len(msg.text) > 1000:
            menu.addSeparator()
            is_exp = index.data(MessageListModel.ExpandedRole)
            label = "Collapse" if is_exp else "Expand"
            menu.addAction(label, lambda: self.model().toggle_expanded(index.row()) if isinstance(self.model(), MessageListModel) else None)
        menu.exec(self.mapToGlobal(pos))
