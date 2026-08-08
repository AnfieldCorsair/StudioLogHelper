# -*- coding: utf-8 -*-
from __future__ import annotations

import json

from .base import CONTENT_THOUGHTS, THOUGHTS_EXCLUDE, THOUGHTS_SEPARATE
from .txt import _iter_export_messages

try:
    import orjson

    def _dumps(obj):
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2).decode()

    def _dumps_compact(obj):
        return orjson.dumps(obj).decode()
except ImportError:
    def _dumps(obj):
        return json.dumps(obj, ensure_ascii=False, indent=2)

    def _dumps_compact(obj):
        return json.dumps(obj, ensure_ascii=False)


def _message_to_dict(num, msg, opts) -> dict:
    d = {"index": num, "role": msg.role}
    if msg.text.strip():
        d["text"] = msg.text.strip()
    if msg.has_thoughts and opts.thoughts != THOUGHTS_EXCLUDE:
        d["thoughts"] = [t.strip() for t in msg.thoughts]
    if opts.attachments and msg.attachments:
        d["attachments"] = [
            {"kind": a.kind, "label": a.label_key, **({"id": a.drive_id} if a.drive_id else {}), **({"url": a.url} if a.url else {})}
            for a in msg.attachments
        ]
    if opts.timestamps and msg.create_time:
        d["time"] = msg.create_time
    if msg.token_count:
        d["tokens"] = msg.token_count
    if msg.finish_reason:
        d["finish_reason"] = msg.finish_reason
    return d


def _json_doc(chat, opts) -> dict:
    doc = {"title": chat.title}
    if opts.metadata:
        if chat.model:
            doc["model"] = chat.model
        if chat.path:
            doc["source_file"] = chat.path
        rs = chat.run_settings
        settings = {k: rs[k] for k in ("temperature", "topP", "topK", "maxOutputTokens") if k in rs}
        if settings:
            doc["settings"] = settings
        doc["stats"] = {
            "messages": len(chat.messages),
            "prompts": chat.user_count,
            "answers": chat.model_count,
            "thoughts": chat.thought_count,
        }
    if opts.system_instruction and chat.system_instruction and opts.content == "all":
        doc["system_instruction"] = chat.system_instruction

    msgs = []
    for num, msg in _iter_export_messages(chat, opts):
        if opts.content == CONTENT_THOUGHTS:
            msgs.append({"index": num, "role": msg.role, "thoughts": [t.strip() for t in msg.thoughts]})
        else:
            msgs.append(_message_to_dict(num, msg, opts))
    doc["messages"] = msgs
    return doc


class JsonExporter:
    def export(self, chat, opts):
        sep_doc = None
        if opts.content != CONTENT_THOUGHTS and opts.thoughts == THOUGHTS_SEPARATE:
            main_opts = type(opts)(**{**opts.__dict__, "thoughts": THOUGHTS_EXCLUDE})
            doc = _json_doc(chat, main_opts)
            th_msgs = [
                {"index": n, "role": m.role, "thoughts": [t.strip() for t in m.thoughts]}
                for n, m in _iter_export_messages(chat, opts)
                if m.has_thoughts
            ]
            if th_msgs:
                sep_doc = _dumps({"title": chat.title, "kind": "thoughts", "messages": th_msgs}) + "\n"
        else:
            doc = _json_doc(chat, opts)
        return _dumps(doc) + "\n", sep_doc


class JsonlExporter:
    def export(self, chat, opts):
        lines = []
        for num, msg in _iter_export_messages(chat, opts):
            if opts.content == CONTENT_THOUGHTS:
                d = {"index": num, "role": msg.role, "thoughts": [t.strip() for t in msg.thoughts]}
            else:
                d = _message_to_dict(num, msg, opts)
            if opts.metadata:
                d["chat"] = chat.title
                if chat.model:
                    d["model"] = chat.model
            lines.append(_dumps_compact(d))
        return "\n".join(lines) + "\n", None
