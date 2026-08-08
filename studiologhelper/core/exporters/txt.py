# -*- coding: utf-8 -*-
from __future__ import annotations

from ..models import Message
from .base import CONTENT_THOUGHTS, THOUGHTS_INCLUDE, THOUGHTS_SEPARATE


def _txt_header(chat, opts) -> str:
    lines = []
    bar = "=" * 70
    lines.append(bar)
    lines.append(f"  Chat: {chat.title}")
    if chat.model:
        lines.append(f"  Model: {chat.model}")
    rs = chat.run_settings
    extra = []
    for k in ("temperature", "topP", "topK", "maxOutputTokens"):
        if k in rs:
            extra.append(f"{k}={rs[k]}")
    if extra:
        lines.append(f"  Params: {', '.join(extra)}")
    lines.append(f"  Messages: {len(chat.messages)} (prompts: {chat.user_count}, answers: {chat.model_count})")
    lines.append(bar)
    return "\n".join(lines)


def _msg_label(msg: Message, num, opts, labels) -> str:
    user_l, model_l = labels
    base = user_l if msg.is_user else model_l
    if msg.role not in ("user", "model"):
        base = msg.role.upper()
    parts = []
    if num is not None:
        parts.append(f"#{num}")
    parts.append(base)
    if opts.timestamps and msg.time_str():
        parts.append(f"[{msg.time_str()}]")
    return " ".join(parts)


def _attachment_lines(msg: Message) -> list[str]:
    out = []
    for a in msg.attachments:
        if a.url:
            out.append(f"[Attachment: {a.label_key}] {a.url}")
        else:
            out.append(f"[Attachment: {a.label_key}]")
    return out


def _iter_export_messages(chat, opts):
    for num, msg in enumerate(chat.messages, 1):
        if opts.content == "prompts" and not msg.is_user:
            continue
        if opts.content == "answers" and msg.is_user:
            continue
        if opts.content == "thoughts" and not msg.has_thoughts:
            continue
        yield num, msg


class TxtExporter:
    def export(self, chat, opts):
        out: list[str] = []
        thoughts_out: list[str] = []
        labels = opts.effective_labels(chat)
        only_thoughts = opts.content == CONTENT_THOUGHTS

        if opts.metadata:
            out.append(_txt_header(chat, opts))
            out.append("")

        if opts.system_instruction and chat.system_instruction and opts.content == "all":
            out.append("--- SYSTEM INSTRUCTION " + "-" * 44)
            out.append(chat.system_instruction)
            out.append("")

        for num, msg in _iter_export_messages(chat, opts):
            label = _msg_label(msg, num if opts.numbering else None, opts, labels)
            out.append(f"--- {label} " + "-" * max(3, 66 - len(label)))

            if only_thoughts:
                for t in msg.thoughts:
                    out.append(t.strip())
                out.append("")
                continue

            if msg.has_thoughts and opts.thoughts == THOUGHTS_INCLUDE:
                out.append("[Thoughts]")
                for t in msg.thoughts:
                    out.append(t.strip())
                out.append("[/Thoughts]")
                out.append("")
            if msg.has_thoughts and opts.thoughts == THOUGHTS_SEPARATE:
                head = f"=== {label} ==="
                thoughts_out.append(head)
                for t in msg.thoughts:
                    thoughts_out.append(t.strip())
                thoughts_out.append("")

            if opts.attachments and msg.attachments:
                out.extend(_attachment_lines(msg))

            text = msg.text.strip()
            if text:
                out.append(text)
            elif not msg.attachments and not msg.has_thoughts:
                out.append("[empty message]")
            out.append("")

        main = "\n".join(out).rstrip() + "\n"
        sep = None
        if not only_thoughts and opts.thoughts == THOUGHTS_SEPARATE and thoughts_out:
            head = f"MODEL THOUGHTS — {chat.title}\n" + "=" * 70 + "\n"
            sep = head + "\n".join(thoughts_out).rstrip() + "\n"
        return main, sep
