# -*- coding: utf-8 -*-
"""Claude / Anthropic export parser plugin example"""

from pathlib import Path
import json
from ..models import ChatLog, Message
from ...utils.encoding import detect_encoding_and_decode


class ClaudePlugin:
    name = "claude"
    description = "Claude Chat Export (JSON array of conversations)"
    extensions = [".json"]

    def can_parse(self, path: Path, head: str) -> bool:
        # Claude exports often have "chat_messages" or "conversations" with human/assistant
        h = head.lower()
        if '"human"' in h and '"assistant"' in h:
            return True
        if '"role": "human"' in h or '"role": "user"' in h and 'claude' in h:
            return True
        return False

    def parse(self, path: Path, text_options=None):
        text = detect_encoding_and_decode(Path(path).read_bytes())
        try:
            data = json.loads(text)
        except Exception:
            # maybe jsonl?
            raise

        chat = ChatLog(path=str(path), title=Path(path).stem, source_format="json", raw=data if isinstance(data, dict) else {})

        # Try multiple known Claude formats
        messages_data = None
        if isinstance(data, dict):
            # Format 1: {"chat_messages": [...]}
            if "chat_messages" in data and isinstance(data["chat_messages"], list):
                messages_data = data["chat_messages"]
                chat.title = data.get("name", chat.title)
            # Format 2: single conversation dict with "messages"
            elif "messages" in data and isinstance(data["messages"], list):
                messages_data = data["messages"]
            # Format 3: Anthropic API format {"content": [...]}
        elif isinstance(data, list):
            # list of messages directly
            messages_data = data

        if not messages_data:
            raise ValueError("Not a Claude format")

        for item in messages_data:
            if not isinstance(item, dict):
                continue
            role = item.get("role") or item.get("sender") or "unknown"
            # Normalize
            if role in ("human", "user", "User"):
                role = "user"
            elif role in ("assistant", "Assistant", "claude", "model"):
                role = "model"
            text_content = ""
            # content can be string or list of blocks
            c = item.get("text") or item.get("content") or item.get("message") or ""
            if isinstance(c, str):
                text_content = c
            elif isinstance(c, list):
                # Anthropic content blocks: [{"type": "text", "text": "..."}]
                parts = []
                for block in c:
                    if isinstance(block, dict) and "text" in block:
                        parts.append(block["text"])
                    elif isinstance(block, str):
                        parts.append(block)
                text_content = "\n".join(parts)
            elif isinstance(c, dict) and "text" in c:
                text_content = c["text"]

            if text_content:
                chat.messages.append(Message(role=role, text=text_content))

        if not chat.messages:
            raise ValueError("Claude parser: no messages found")
        return chat


def get_plugin():
    return ClaudePlugin()
