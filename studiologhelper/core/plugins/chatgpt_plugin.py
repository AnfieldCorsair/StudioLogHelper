# -*- coding: utf-8 -*-
"""ChatGPT export parser"""

from pathlib import Path
import json
from ..models import ChatLog, Message
from ...utils.encoding import detect_encoding_and_decode


class ChatGPTPlugin:
    name = "chatgpt"
    description = "ChatGPT conversations.json export"
    extensions = [".json"]

    def can_parse(self, path: Path, head: str) -> bool:
        h = head.lower()
        # ChatGPT export contains "mapping" and "conversation"
        if '"mapping"' in h and '"message"' in h and '"author"' in h:
            return True
        if '"conversations"' in h and '"title"' in h and '"create_time"' in h:
            return True
        return False

    def parse(self, path: Path, text_options=None):
        text = detect_encoding_and_decode(Path(path).read_bytes())
        data = json.loads(text)

        # ChatGPT export: list of conversations
        conversations = data if isinstance(data, list) else data.get("conversations", [data])

        # We parse first conversation as one ChatLog, or if many, concat?
        # For simplicity: if file contains list, parse first, but title indicates count
        # User should split file per conversation externally, but we support single

        # If data is a single conversation with mapping
        chat = ChatLog(path=str(path), title=Path(path).stem, source_format="json", raw={})

        conv = conversations[0] if conversations else {}
        if not isinstance(conv, dict):
            raise ValueError("Not ChatGPT format")

        chat.title = conv.get("title", chat.title) or chat.title

        mapping = conv.get("mapping", {})
        if not mapping:
            # maybe already list of messages
            msgs = conv.get("messages", [])
            for m in msgs:
                role = m.get("role", "unknown")
                if role == "user":
                    role = "user"
                elif role in ("assistant", "model", "system"):
                    # system as special? keep as model but store as sys instr?
                    if role == "system" and not chat.system_instruction:
                        chat.system_instruction = m.get("content", {}).get("parts", [""])[0] if isinstance(m.get("content"), dict) else m.get("content", "")
                        continue
                    role = "model"
                txt = ""
                content = m.get("content", {})
                if isinstance(content, dict):
                    parts = content.get("parts", [])
                    txt = "\n".join(str(p) for p in parts if p)
                elif isinstance(content, str):
                    txt = content
                if txt:
                    chat.messages.append(Message(role=role, text=txt))
            return chat

        # Walk mapping tree to reconstruct linear history: find current_node and traverse parent
        # ChatGPT mapping: id -> {message, parent, children}
        # Linearize via current_node
        current_node = conv.get("current_node")
        nodes = []
        if current_node:
            cur = current_node
            while cur and cur in mapping:
                node = mapping[cur]
                nodes.append(node)
                cur = node.get("parent")
            nodes = list(reversed(nodes))
        else:
            # fallback: sorted by create_time
            nodes = sorted([v for v in mapping.values() if v.get("message")], key=lambda x: x.get("message", {}).get("create_time", 0) or 0)

        for node in nodes:
            msg = node.get("message")
            if not msg:
                continue
            author = msg.get("author", {})
            role = author.get("role", "unknown")
            if role == "user":
                role = "user"
            elif role == "assistant":
                role = "model"
            elif role == "system":
                if not chat.system_instruction:
                    content = msg.get("content", {})
                    if isinstance(content, dict):
                        parts = content.get("parts", [])
                        chat.system_instruction = "\n".join(str(p) for p in parts)
                continue
            else:
                continue

            content = msg.get("content", {})
            txt = ""
            if isinstance(content, dict):
                # content_type text
                parts = content.get("parts", [])
                txt = "\n".join(str(p) for p in parts if p)
            if txt.strip():
                chat.messages.append(Message(role=role, text=txt.strip()))

        if not chat.messages:
            raise ValueError("ChatGPT parser: no messages")
        return chat


def get_plugin():
    return ChatGPTPlugin()
