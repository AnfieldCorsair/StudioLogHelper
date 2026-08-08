# -*- coding: utf-8 -*-
"""MessageCard — оптимизированный, реиспользует QLabel, минимизирует перерисовку."""

from __future__ import annotations

import html as _html
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QToolButton, QMenu, QSizePolicy
)

from ...core.models import Message
from ...core.markdown import markdown_to_html

ASSET_DIR = Path(__file__).resolve().parents[3] / "assets" / "icons"
LONG_PREVIEW = 5000

_ICON_CACHE = {}
_PIXMAP_CACHE = {}


def load_icon(name: str) -> QIcon:
    if name in _ICON_CACHE:
        return _ICON_CACHE[name]
    p = ASSET_DIR / name
    ic = QIcon(str(p)) if p.exists() else QIcon()
    _ICON_CACHE[name] = ic
    return ic


def load_pixmap(name: str, size: int = 18) -> QPixmap:
    key = (name, size)
    if key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[key]
    p = ASSET_DIR / name
    out = QPixmap()
    if p.exists():
        pix = QPixmap(str(p))
        if not pix.isNull():
            out = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    _PIXMAP_CACHE[key] = out
    return out


class MessageCard(QFrame):
    def __init__(self, msg: Message, num: int, theme: dict, render_md: bool, show_thoughts: bool, status_cb, model_name: str = "", collapse_long: bool = True, preview_chars: int = LONG_PREVIEW, tr_func=None):
        super().__init__()
        self.msg = msg
        self._status = status_cb
        self._tr = tr_func or (lambda k, **kw: k)
        self._preview_chars = max(200, int(preview_chars or LONG_PREVIEW))
        self._auto_collapse = collapse_long
        self.setObjectName("msgCardUser" if msg.is_user else "msgCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        if msg.is_user:
            who = self._tr("user")
        else:
            who = model_name or self._tr("model")
        if msg.role not in ("user", "model"):
            who = msg.role.upper()
        color = theme["user"] if msg.is_user else theme["model"]
        pix = load_pixmap("user.png" if msg.is_user else "model.png", 18)
        prefix = ""
        if not pix.isNull():
            il = QLabel()
            il.setPixmap(pix)
            hdr.addWidget(il)
        else:
            prefix = "👤 " if msg.is_user else "🤖 "
        lbl = QLabel(f"<b style='color:{color}'>#{num} {prefix}{_html.escape(who)}</b>")
        lbl.setTextFormat(Qt.TextFormat.RichText)
        hdr.addWidget(lbl)
        if msg.time_str():
            tl = QLabel(msg.time_str())
            tl.setObjectName("muted")
            hdr.addWidget(tl)
        if msg.token_count:
            tk = QLabel(f"{msg.token_count} {self._tr('tokens_short')}")
            tk.setObjectName("muted")
            hdr.addWidget(tk)
        hdr.addStretch(1)

        btn = QPushButton(self._tr("copy"))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._copy)
        hdr.addWidget(btn)

        if show_thoughts and msg.has_thoughts:
            more = QToolButton()
            more.setText(self._tr("copy_more"))
            more.setCursor(Qt.CursorShape.PointingHandCursor)
            more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            m = QMenu(more)
            m.addAction(self._tr("copy_with_thoughts"), self._copy_with_thoughts)
            m.addAction(self._tr("copy_only_thoughts"), self._copy_thoughts_only)
            more.setMenu(m)
            hdr.addWidget(more)
        lay.addLayout(hdr)

        if show_thoughts and msg.has_thoughts:
            box = QFrame()
            box.setObjectName("thoughtBox")
            box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            bl = QVBoxLayout(box)
            bl.setContentsMargins(10, 8, 10, 8)
            cap = QLabel(f"<b style='color:{theme['thought']}'>{self._tr('thoughts_n', n=len(msg.thoughts))}</b>")
            cap.setTextFormat(Qt.TextFormat.RichText)
            bl.addWidget(cap)
            body = self._make_body("\n\n".join(t.strip() for t in msg.thoughts), render_md)
            bl.addWidget(body)
            lay.addWidget(box)

        for a in msg.attachments:
            al = QLabel(
                f"📎 <a href='{_html.escape(a.url, quote=True)}'>{_html.escape(a.label_key)} (Drive)</a>" if a.url else f"📎 {_html.escape(a.label_key)}"
            )
            al.setTextFormat(Qt.TextFormat.RichText)
            al.setOpenExternalLinks(True)
            al.setObjectName("muted")
            lay.addWidget(al)

        text = msg.text.strip()
        self._body = None
        self._toggle_btn = None
        self._full_text = text
        self._rich = render_md and not msg.is_user
        self._collapsed = False
        if text:
            if self._auto_collapse and len(text) > self._preview_chars:
                self._collapsed = True
                body = self._make_body(self._preview_text(text), False)
                self._body = body
                lay.addWidget(body)
                self._toggle_btn = QPushButton(self._tr("expand_message"))
                self._toggle_btn.clicked.connect(self._toggle_collapsed)
                lay.addWidget(self._toggle_btn)
            else:
                body = self._make_body(text, self._rich)
                lay.addWidget(body)
        elif not msg.attachments and not msg.has_thoughts:
            e = QLabel(self._tr("empty_message"))
            e.setObjectName("muted")
            lay.addWidget(e)

    def _preview_text(self, text: str) -> str:
        return text[: self._preview_chars].rstrip() + f"\n\n… {self._tr('collapsed_tail', n=len(text) - self._preview_chars)}"

    def _set_body_text(self, text: str, rich: bool):
        if self._body is None:
            return
        if rich:
            self._body.setTextFormat(Qt.TextFormat.RichText)
            self._body.setText(markdown_to_html(text))
        else:
            self._body.setTextFormat(Qt.TextFormat.PlainText)
            self._body.setText(text)

    def _toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool):
        if self._toggle_btn is None or not self._full_text:
            return
        self._collapsed = collapsed
        if self._collapsed:
            self._set_body_text(self._preview_text(self._full_text), False)
            self._toggle_btn.setText(self._tr("expand_message"))
        else:
            self._set_body_text(self._full_text, self._rich)
            self._toggle_btn.setText(self._tr("collapse_message"))

    def is_long_card(self) -> bool:
        return self._toggle_btn is not None

    def _make_body(self, text: str, rich: bool) -> QLabel:
        body = QLabel()
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        body.setOpenExternalLinks(True)
        if rich:
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setText(markdown_to_html(text))
        else:
            body.setTextFormat(Qt.TextFormat.PlainText)
            body.setText(text)
        body.setMinimumWidth(0)
        body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        return body

    def _copy(self):
        from PyQt6.QtGui import QGuiApplication
        from ...core.models import message_copy_text

        QGuiApplication.clipboard().setText(message_copy_text(self.msg, include_thoughts=False))
        self._status(self._tr("msg_copied"))

    def _copy_with_thoughts(self):
        from PyQt6.QtGui import QGuiApplication
        from ...core.models import message_copy_text

        QGuiApplication.clipboard().setText(message_copy_text(self.msg, include_thoughts=True))
        self._status(self._tr("msg_copied"))

    def _copy_thoughts_only(self):
        from PyQt6.QtGui import QGuiApplication
        from ...core.models import message_copy_text

        QGuiApplication.clipboard().setText(message_copy_text(self.msg, thoughts_only=True))
        self._status(self._tr("thoughts_copied"))
