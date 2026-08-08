# -*- coding: utf-8 -*-
"""JSON парсер для логов AI Studio — оптимизированный."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..exceptions import ParseError
from ..models import Attachment, ATTACHMENT_KINDS, ChatLog, Message

# Попытка использовать orjson для 3-5x ускорения
try:
    import orjson

    def _json_loads(s: str | bytes):
        if isinstance(s, str):
            s = s.encode()
        return orjson.loads(s)

    HAS_ORJSON = True
except ImportError:
    import json

    def _json_loads(s: str | bytes):
        if isinstance(s, bytes):
            s = s.decode("utf-8", errors="replace")
        return json.loads(s)

    HAS_ORJSON = False


def _chunk_text(chunk: dict) -> str:
    text = chunk.get("text")
    if isinstance(text, str) and text:
        return text
    parts = chunk.get("parts")
    if isinstance(parts, list):
        out = []
        for p in parts:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                out.append(p["text"])
        return "".join(out)
    return ""


def _chunk_attachments(chunk: dict) -> list[Attachment]:
    found = []
    for key, val in chunk.items():
        if not isinstance(val, dict):
            continue
        if key in ATTACHMENT_KINDS or key.startswith("drive"):
            drive_id = str(val.get("id", "") or "")
            found.append(Attachment(kind=key, drive_id=drive_id))
    return found


def parse_data(data: dict, path: str = "") -> ChatLog:
    if not isinstance(data, dict):
        raise ParseError("JSON root is not an object; not an AI Studio log.")

    chat = ChatLog(path=path, raw=data, source_format="json")
    chat.title = Path(path).stem if path else "Untitled"

    rs = data.get("runSettings")
    if isinstance(rs, dict):
        chat.run_settings = rs
        model = rs.get("model", "")
        if isinstance(model, str):
            chat.model = model.split("/")[-1] if model else ""

    si = data.get("systemInstruction")
    if isinstance(si, dict):
        sys_text = si.get("text")
        if not sys_text and isinstance(si.get("parts"), list):
            sys_text = "".join(p.get("text", "") for p in si["parts"] if isinstance(p, dict))
        if isinstance(sys_text, str):
            chat.system_instruction = sys_text.strip()
    elif isinstance(si, str):
        chat.system_instruction = si.strip()

    cp = data.get("chunkedPrompt")
    chunks = None
    if isinstance(cp, dict):
        chunks = cp.get("chunks")
    if chunks is None:
        for alt in ("chunks", "history", "messages"):
            if isinstance(data.get(alt), list):
                chunks = data[alt]
                break
    if not isinstance(chunks, list):
        raise ParseError("Message list not found (chunkedPrompt.chunks). Not an AI Studio log.")

    pending_thoughts: list[str] = []
    pending_meta: dict = {}

    messages = chat.messages  # local ref for speed
    warnings = chat.warnings

    for idx, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            warnings.append(f"Chunk #{idx}: not an object, skipped.")
            continue

        role = chunk.get("role") or "unknown"
        text = _chunk_text(chunk)
        atts = _chunk_attachments(chunk)
        tok = chunk.get("tokenCount") or 0
        ctime = chunk.get("createTime") or ""
        finish = chunk.get("finishReason") or ""

        if role == "model" and chunk.get("isThought"):
            if text.strip():
                pending_thoughts.append(text)
            pending_meta.setdefault("create_time", ctime)
            continue

        if role == "model":
            msg = Message(
                role="model",
                text=text,
                thoughts=pending_thoughts,
                attachments=atts,
                token_count=tok if isinstance(tok, int) else 0,
                create_time=ctime or pending_meta.get("create_time", ""),
                finish_reason=str(finish),
            )
            messages.append(msg)
            pending_thoughts, pending_meta = [], {}
            continue

        # user coalescing
        last = messages[-1] if messages else None
        if last is not None and last.role == role and role == "user":
            if text:
                last.text = (last.text + "\n" + text).strip("\n") if last.text else text
            last.attachments.extend(atts)
            if isinstance(tok, int):
                last.token_count += tok
            if not last.create_time:
                last.create_time = ctime
        else:
            messages.append(
                Message(
                    role=role,
                    text=text,
                    attachments=atts,
                    token_count=tok if isinstance(tok, int) else 0,
                    create_time=ctime,
                )
            )

    if pending_thoughts:
        messages.append(
            Message(
                role="model",
                text="",
                thoughts=pending_thoughts,
                create_time=pending_meta.get("create_time", ""),
            )
        )
        warnings.append("Log ends with thoughts without final model answer.")

    if not messages:
        warnings.append("Log contains no messages.")
    return chat
