# -*- coding: utf-8 -*-
from __future__ import annotations

from .base import CONTENT_THOUGHTS, THOUGHTS_INCLUDE, THOUGHTS_SEPARATE
from .txt import _iter_export_messages, _msg_label


class MdExporter:
    def export(self, chat, opts):
        out: list[str] = []
        thoughts_out: list[str] = []
        labels = opts.effective_labels(chat)
        only_thoughts = opts.content == CONTENT_THOUGHTS

        if opts.metadata:
            out.append(f"# {chat.title}")
            meta = []
            if chat.model:
                meta.append(f"**Model:** `{chat.model}`")
            meta.append(f"**Messages: {len(chat.messages)} (prompts: {chat.user_count}, answers: {chat.model_count})**")
            out.append("  \n".join(meta))
            out.append("")

        if opts.system_instruction and chat.system_instruction and opts.content == "all":
            out.append("## System instruction")
            out.append(chat.system_instruction)
            out.append("")

        for num, msg in _iter_export_messages(chat, opts):
            label = _msg_label(msg, num if opts.numbering else None, opts, labels)
            out.append(f"## {label}")

            if only_thoughts:
                for t in msg.thoughts:
                    out.append(t.strip())
                out.append("")
                continue

            if msg.has_thoughts and opts.thoughts == THOUGHTS_INCLUDE:
                for t in msg.thoughts:
                    out.append("> **Thoughts:**")
                    for ln in t.strip().split("\n"):
                        out.append(f"> {ln}")
                    out.append("")
            if msg.has_thoughts and opts.thoughts == THOUGHTS_SEPARATE:
                thoughts_out.append(f"## {label}")
                for t in msg.thoughts:
                    thoughts_out.append(t.strip())
                thoughts_out.append("")

            if opts.attachments and msg.attachments:
                for a in msg.attachments:
                    if a.url:
                        out.append(f"*[Attachment: {a.label_key}]({a.url})*")
                    else:
                        out.append(f"*[Attachment: {a.label_key}]*")
                out.append("")

            if msg.text.strip():
                out.append(msg.text.strip())
            out.append("")

        main = "\n".join(out).rstrip() + "\n"
        sep = None
        if not only_thoughts and opts.thoughts == THOUGHTS_SEPARATE and thoughts_out:
            sep = f"# Model thoughts — {chat.title}\n\n" + "\n".join(thoughts_out).rstrip() + "\n"
        return main, sep
