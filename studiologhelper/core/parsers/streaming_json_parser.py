# -*- coding: utf-8 -*-
"""Streaming JSON parser для очень больших логов — ijson fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generator

from ..exceptions import ParseError
from ..models import Attachment, ChatLog, Message
from ...utils.encoding import detect_encoding_and_decode

try:
    import ijson  # type: ignore
    HAS_IJSON = True
except ImportError:
    HAS_IJSON = False

try:
    import orjson

    def _loads(b):
        return orjson.loads(b)

    HAS_ORJSON = True
except ImportError:
    def _loads(b):
        return json.loads(b)

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


def _chunk_attachments(chunk: dict):
    from ..models import ATTACHMENT_KINDS
    found = []
    for key, val in chunk.items():
        if not isinstance(val, dict):
            continue
        if key in ATTACHMENT_KINDS or key.startswith("drive"):
            drive_id = str(val.get("id", "") or "")
            found.append(Attachment(kind=key, drive_id=drive_id))
    return found


def parse_large_json_streaming(path: Path) -> ChatLog:
    """Парсит большой JSON лога стримингом через ijson, не грузя всё в RAM.

    Ожидает структуру:
    {
      "runSettings": {...},
      "systemInstruction": {...},
      "chunkedPrompt": {"chunks": [ {...}, ... ]}
    }

    Читает runSettings / systemInstruction отдельно (первые 64KB),
    затем стримит chunks.
    """
    p = Path(path)
    if not HAS_IJSON:
        raise RuntimeError("ijson not installed")

    chat = ChatLog(path=str(p), title=p.stem, source_format="json")

    # First, try to get runSettings and systemInstruction via small read
    try:
        # Read first 128KB to extract header
        with p.open("rb") as f:
            head_bytes = f.read(128 * 1024)
            # Try to decode head as partial JSON? We'll use regex fallback for model
            # Simpler: use ijson for runSettings
        # Use ijson to get runSettings
        with p.open("rb") as f:
            # ijson can parse runSettings.model
            try:
                # This iterates over runSettings
                for prefix, event, value in ijson.parse(f):
                    if prefix == "runSettings.model" and event == "string":
                        chat.model = value.split("/")[-1]
                    if prefix == "systemInstruction.text" and event == "string":
                        chat.system_instruction = value.strip()
                    if prefix == "chunkedPrompt.chunks.item":
                        # We've reached chunks, break to streaming loop below
                        break
            except Exception:
                pass
    except Exception:
        pass

    # Now stream chunks
    messages: list[Message] = []
    warnings: list[str] = []
    pending_thoughts: list[str] = []
    pending_meta: dict = {}

    try:
        with p.open("rb") as f:
            # ijson.items for chunks
            chunks_iter = ijson.items(f, "chunkedPrompt.chunks.item")
            for idx, chunk in enumerate(chunks_iter):
                if not isinstance(chunk, dict):
                    warnings.append(f"Chunk #{idx}: not object, skipped")
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

            # Also try alternative paths if chunkedPrompt not found
            if not messages:
                # Try top-level chunks, history, messages
                for alt_path in ("chunks.item", "history.item", "messages.item"):
                    try:
                        with p.open("rb") as f2:
                            for idx, chunk in enumerate(ijson.items(f2, alt_path)):
                                if not isinstance(chunk, dict):
                                    continue
                                role = chunk.get("role") or "unknown"
                                text = _chunk_text(chunk)
                                if text:
                                    messages.append(Message(role=role, text=text))
                        if messages:
                            break
                    except Exception:
                        continue

    except Exception as e:
        raise ParseError(f"Streaming parse failed: {e}") from e

    if pending_thoughts:
        messages.append(Message(role="model", text="", thoughts=pending_thoughts, create_time=pending_meta.get("create_time", "")))
        warnings.append("Log ends with thoughts without final answer")

    if not messages:
        warnings.append("Log contains no messages")

    chat.messages = messages
    chat.warnings = warnings
    # Try to get runSettings from file if not yet
    if not chat.model:
        try:
            with p.open("rb") as f:
                for prefix, event, value in ijson.parse(f):
                    if prefix == "runSettings.model" and event == "string":
                        chat.model = value.split("/")[-1]
                        break
        except Exception:
            pass

    return chat


def should_use_streaming(path: Path, threshold_mb: int = 30) -> bool:
    """Решает, использовать ли стриминг для файла."""
    try:
        size_mb = path.stat().st_size / (1024 * 1024)
        return size_mb >= threshold_mb and HAS_IJSON
    except OSError:
        return False
