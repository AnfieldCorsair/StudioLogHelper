# -*- coding: utf-8 -*-
"""CopyService — сервисный слой для копирования сообщений, логов и фрагментов в буфер обмена."""

from __future__ import annotations

import json
from typing import Any, Optional

from ...core.exporters.base import (
    CONTENT_ALL,
    CONTENT_ANSWERS,
    CONTENT_PROMPTS,
    CONTENT_THOUGHTS,
    THOUGHTS_EXCLUDE,
    THOUGHTS_INCLUDE,
    ExportOptions,
)
from ...core.models import (
    COPY_ALL,
    COPY_ANSWERS,
    COPY_PROMPTS,
    COPY_THOUGHTS,
    ChatLog,
    Message,
    chat_to_clipboard_text,
    message_copy_text,
)
from ...i18n.translator import Translator


class CopyService:
    """Сервис форматирования и копирования данных в буфер обмена."""

    @staticmethod
    def get_separator(settings: Any) -> str:
        mode = settings.value("copy/separator", "blank") if hasattr(settings, "value") else "blank"
        if mode == "double":
            return "\n\n\n"
        if mode == "long":
            return "\n\n" + "—" * 70 + "\n\n"
        if mode == "custom":
            raw = (
                settings.value("copy/custom_separator", "\n---\n")
                if hasattr(settings, "value")
                else "\n---\n"
            )
            return raw.replace("\\n", "\n")
        return "\n\n"

    @staticmethod
    def copy_to_clipboard(text: str):
        try:
            from PyQt6.QtGui import QGuiApplication
            clip = QGuiApplication.clipboard()
            if clip:
                clip.setText(text)
        except Exception:
            pass

    @classmethod
    def clean_copy_text(cls, chat: ChatLog, which: Any, settings: Any) -> str:
        sep = cls.get_separator(settings)
        parts = []
        is_prompts = which in (CONTENT_PROMPTS, COPY_PROMPTS, "prompts", 1)
        is_answers = which in (CONTENT_ANSWERS, COPY_ANSWERS, "answers", 2)
        is_thoughts = which in (CONTENT_THOUGHTS, COPY_THOUGHTS, "thoughts", 3)

        for msg in chat.messages:
            if is_prompts and not msg.is_user:
                continue
            if is_answers and msg.is_user:
                continue
            if is_thoughts:
                if msg.has_thoughts:
                    parts.extend(t.strip() for t in msg.thoughts if t.strip())
                continue
            if msg.text.strip():
                parts.append(msg.text.strip())
        return sep.join(parts).strip() + ("\n" if parts else "")

    @classmethod
    def copy_chat(
        cls,
        chat: ChatLog,
        which: Any,
        settings: Any,
        translator: Translator,
        show_thoughts: bool = True,
    ) -> str:
        inc_service = (
            (settings.value("copy/include_service", "true") == "true")
            if hasattr(settings, "value")
            else True
        )
        if not inc_service:
            text = cls.clean_copy_text(chat, which, settings)
        else:
            is_prompts = which in (CONTENT_PROMPTS, COPY_PROMPTS, "prompts", 1)
            which_str = (
                COPY_PROMPTS
                if is_prompts
                else (
                    COPY_ANSWERS
                    if which in (CONTENT_ANSWERS, COPY_ANSWERS, "answers", 2)
                    else (COPY_THOUGHTS if which in (CONTENT_THOUGHTS, COPY_THOUGHTS, "thoughts", 3) else COPY_ALL)
                )
            )
            opts = ExportOptions(
                fmt="txt",
                metadata=False,
                system_instruction=False,
                auto_model_label=True,
                user_label=translator.tr("user"),
                model_label=translator.tr("model"),
                thoughts=THOUGHTS_INCLUDE if (show_thoughts and not is_prompts) else THOUGHTS_EXCLUDE,
            )
            text = chat_to_clipboard_text(chat, which_str, opts)

        cls.copy_to_clipboard(text)
        return text

    @classmethod
    def copy_raw(cls, chat: ChatLog) -> str:
        if chat.source_format == "text":
            text = chat.raw_text or ""
        else:
            text = json.dumps(chat.raw, ensure_ascii=False, indent=2)
        cls.copy_to_clipboard(text)
        return text

    @classmethod
    def copy_message(cls, msg: Message, mode: str = "normal") -> str:
        if mode == "with_thoughts":
            text = message_copy_text(msg, include_thoughts=True)
        elif mode == "thoughts_only":
            text = message_copy_text(msg, thoughts_only=True)
        else:
            text = message_copy_text(msg, include_thoughts=False)
        cls.copy_to_clipboard(text)
        return text
