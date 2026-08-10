# -*- coding: utf-8 -*-
"""MessageRenderer — рендеринг карточек сообщений, служебных блоков и предпросмотра."""

from __future__ import annotations

import html as _html
import json
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QLayout, QVBoxLayout, QWidget

from ...core.models import ChatLog, Message
from ..controllers.project_controller import ProjectController
from ..widgets.message_card import MessageCard

VIEW_BATCH = 25
RAW_PREVIEW_LIMIT = 1_500_000


class MessageRenderer:
    """Рендерер карточек сообщений и служебной информации."""

    @staticmethod
    def format_info_header(
        chat: ChatLog | None,
        project_ctrl: ProjectController,
        show_diagnostics: bool,
        show_extensions: bool,
        tr_func: Callable,
    ) -> str:
        if chat is None:
            return ""

        info: List[str] = [f"<b>{_html.escape(chat.title)}</b>"]
        cat = project_ctrl.get_category(chat)
        if cat:
            info.append(f"{tr_func('category_label')}: {_html.escape(cat)}")

        tags = project_ctrl.get_tags(chat)
        if tags:
            info.append(f"{tr_func('tags_label')}: " + " ".join("#" + _html.escape(t) for t in tags))

        note = project_ctrl.get_note(chat)
        if note:
            info.append(f"{tr_func('note_label')}: {_html.escape(note[:160])}")

        if show_diagnostics:
            p = Path(chat.path) if chat.path else Path("")
            ext = p.suffix.lower().lstrip(".") or tr_func("no_extension")
            kind = "JSON" if chat.source_format == "json" else "TXT"
            diag = f"{kind} · {ext} · {chat.path}"
            info.append(f"{tr_func('diagnostics_label')}: {_html.escape(diag)}")

        if chat.model:
            info.append(f"{tr_func('info_model')}: {_html.escape(chat.model)}")

        info.append(tr_func("info_msgs", n=len(chat.messages), u=chat.user_count, m=chat.model_count))
        if chat.thought_count:
            info.append(tr_func("info_thoughts", n=chat.thought_count))
        if chat.warnings:
            info.append(f"⚠ {'; '.join(chat.warnings)}")

        bms = project_ctrl.get_bookmarks(chat.path)
        if bms:
            info.append(f"🔖 {_html.escape(tr_func('reader_bookmarks'))}: {len(bms)}")

        return " · ".join(info)

    @staticmethod
    def create_system_instruction_card(chat: ChatLog, tr_func: Callable) -> QWidget:
        box = QFrame()
        box.setObjectName("msgCard")
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(14, 10, 14, 12)
        cap = QLabel(f"<b>{tr_func('system_instruction')}</b>")
        cap.setObjectName("muted")
        bl.addWidget(cap)
        lab = QLabel(chat.system_instruction)
        lab.setWordWrap(True)
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bl.addWidget(lab)
        return box

    @staticmethod
    def create_message_card(
        msg: Message,
        num: int,
        chat: ChatLog,
        theme: dict,
        render_md: bool,
        show_thoughts: bool,
        status_cb: Callable[[str], None],
        project_ctrl: ProjectController,
        collapse_long: bool,
        preview_chars: int,
        tr_func: Callable,
        bookmark_cb: Optional[Callable[[Message, int], None]] = None,
    ) -> MessageCard:
        is_bm = project_ctrl.is_bookmarked(chat.path, num)
        return MessageCard(
            msg=msg,
            num=num,
            theme=theme,
            render_md=render_md,
            show_thoughts=show_thoughts,
            status_cb=status_cb,
            model_name=chat.model,
            collapse_long=collapse_long,
            preview_chars=preview_chars,
            tr_func=tr_func,
            is_bookmarked=is_bm,
            bookmark_cb=bookmark_cb,
        )

    @staticmethod
    def format_raw_content(chat: ChatLog | None, tr_func: Callable) -> Tuple[str, str, str]:
        """Возвращает (raw_text, tab_title, copy_btn_text)."""
        if chat is None:
            return "", tr_func("source_json"), tr_func("copy_source_json")

        if chat.source_format == "json":
            title = tr_func("source_json")
            btn_txt = tr_func("copy_source_json")
            try:
                raw = json.dumps(chat.raw, ensure_ascii=False, indent=2)
                if len(raw) > RAW_PREVIEW_LIMIT:
                    raw = raw[:RAW_PREVIEW_LIMIT] + tr_func(
                        "raw_preview_truncated", shown=RAW_PREVIEW_LIMIT, total=len(raw)
                    )
            except Exception:
                raw = "<JSON?>"
        else:
            title = tr_func("source_text")
            btn_txt = tr_func("copy_source_text")
            raw = chat.raw_text or ""
            if len(raw) > RAW_PREVIEW_LIMIT:
                raw = raw[:RAW_PREVIEW_LIMIT] + tr_func(
                    "raw_preview_truncated", shown=RAW_PREVIEW_LIMIT, total=len(raw)
                )

        return raw, title, btn_txt
