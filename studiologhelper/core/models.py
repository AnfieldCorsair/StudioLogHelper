# -*- coding: utf-8 -*-
"""Чистые модели данных — без зависимости от i18n / Qt."""

from __future__ import annotations

import html
from dataclasses import dataclass, field, replace, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote as _urlquote

# Эти константы теперь тут, а не в exporters, чтобы избежать циркулярности
COPY_ALL = "all"
COPY_PROMPTS = "prompts"
COPY_ANSWERS = "answers"
COPY_THOUGHTS = "thoughts"


# Локализационные ключи вложений (без привязки к tr — просто ключи)
ATTACHMENT_KINDS = {
    "driveImage": "att_image",
    "driveDocument": "att_document",
    "driveVideo": "att_video",
    "driveAudio": "att_audio",
    "driveFile": "att_file",
    "youtubeVideo": "att_youtube",
}


@dataclass(slots=True)
class Attachment:
    kind: str
    drive_id: str = ""
    # label теперь вычисляется снаружи через translator, но оставляем fallback
    _label_fallback: str = "Attachment"

    @property
    def label_key(self) -> str:
        return ATTACHMENT_KINDS.get(self.kind, "att_generic")

    @property
    def url(self) -> str:
        if not self.drive_id:
            return ""
        safe_id = _urlquote(self.drive_id, safe="")
        if self.kind == "youtubeVideo":
            return f"https://www.youtube.com/watch?v={safe_id}"
        return f"https://drive.google.com/file/d/{safe_id}/view"


@dataclass(slots=True)
class Message:
    role: str
    text: str = ""
    thoughts: list[str] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    token_count: int = 0
    create_time: str = ""
    finish_reason: str = ""

    @property
    def is_user(self) -> bool:
        return self.role == "user"

    @property
    def has_thoughts(self) -> bool:
        return bool(self.thoughts)

    def time_str(self) -> str:
        if not self.create_time:
            return ""
        try:
            dt = datetime.fromisoformat(self.create_time.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%d.%m.%Y %H:%M:%S")
        except (ValueError, OSError):
            return self.create_time


@dataclass(slots=True)
class ChatLog:
    path: str = ""
    title: str = ""
    model: str = ""
    source_format: str = ""  # json | text
    raw_text: str = ""
    run_settings: dict = field(default_factory=dict)
    system_instruction: str = ""
    messages: list[Message] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def user_count(self) -> int:
        return sum(1 for m in self.messages if m.is_user)

    @property
    def model_count(self) -> int:
        return sum(1 for m in self.messages if m.role == "model")

    @property
    def thought_count(self) -> int:
        return sum(len(m.thoughts) for m in self.messages)


# --- ExportOptions + Project-related structs вынесены в exporters.base,
#     но для удобства backward compat clipboard helpers тут внизу
#     с отложенным импортом чтобы избежать циркулярной зависимости

def chat_to_clipboard_text(chat: ChatLog, which: str = COPY_ALL, opts=None) -> str:
    """Делегирует в exporters для избежания дублирования."""
    from .exporters.base import ExportOptions, CONTENT_ALL, THOUGHTS_INCLUDE, THOUGHTS_EXCLUDE
    from .exporters.txt import TxtExporter

    if opts is None:
        opts = ExportOptions(fmt="txt", metadata=False, system_instruction=False)

    if which == COPY_ALL:
        o = replace(opts, fmt="txt", content=CONTENT_ALL)
        exporter = TxtExporter()
        main, _ = exporter.export(chat, o)
        return main

    # Определяем labels
    user_label = getattr(opts, "user_label", "USER")
    model_label = getattr(opts, "model_label", "MODEL")
    if getattr(opts, "auto_model_label", False) and chat.model:
        model_label = chat.model

    out = []
    for num, msg in enumerate(chat.messages, 1):
        if which == COPY_PROMPTS and not msg.is_user:
            continue
        if which == COPY_ANSWERS and msg.is_user:
            continue
        if which == COPY_THOUGHTS and not msg.has_thoughts:
            continue
        chunk = []
        if getattr(opts, "numbering", True):
            who = user_label if msg.is_user else model_label
            if msg.role not in ("user", "model"):
                who = msg.role.upper()
            chunk.append(f"--- #{num} {who} ---")
        if which == COPY_THOUGHTS:
            chunk.extend(t.strip() for t in msg.thoughts)
            out.append("\n".join(chunk))
            continue
        if msg.has_thoughts and getattr(opts, "thoughts", THOUGHTS_EXCLUDE) == THOUGHTS_INCLUDE:
            chunk.append("[Thoughts]")
            chunk.extend(t.strip() for t in msg.thoughts)
            chunk.append("[/Thoughts]")
        if getattr(opts, "attachments", True) and msg.attachments:
            for a in msg.attachments:
                if a.url:
                    chunk.append(f"[Attachment: {a.label_key}] {a.url}")
                else:
                    chunk.append(f"[Attachment: {a.label_key}]")
        if msg.text.strip():
            chunk.append(msg.text.strip())
        if len(chunk) > (1 if getattr(opts, "numbering", True) else 0):
            out.append("\n".join(chunk))
    return "\n\n".join(out).strip() + ("\n" if out else "")


def message_copy_text(msg: Message, include_thoughts: bool = False, thoughts_only: bool = False) -> str:
    if thoughts_only:
        return "\n\n".join(t.strip() for t in msg.thoughts)
    parts = []
    if include_thoughts and msg.has_thoughts:
        parts.append("[Thoughts]")
        parts.extend(t.strip() for t in msg.thoughts)
        parts.append("[/Thoughts]")
    for a in msg.attachments:
        if a.url:
            parts.append(f"[Attachment: {a.label_key}] {a.url}")
        else:
            parts.append(f"[Attachment: {a.label_key}]")
    if msg.text.strip():
        parts.append(msg.text.strip())
    return "\n".join(parts)
