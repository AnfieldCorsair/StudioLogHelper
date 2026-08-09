import sys
from pathlib import Path
import json
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studiologhelper.core.plugins import PluginRegistry
from studiologhelper.core.plugins.builtin_json import JSONPlugin
from studiologhelper.core.plugins.builtin_text import TextPlugin
from studiologhelper.core.plugins.claude_plugin import ClaudePlugin
from studiologhelper.core.plugins.chatgpt_plugin import ChatGPTPlugin


def test_builtin_json_plugin(tmp_path):
    p = tmp_path / "log.json"
    p.write_text(json.dumps({
        "runSettings": {"model": "gemini"},
        "chunkedPrompt": {"chunks": [{"role": "user", "text": "hi"}]}
    }), encoding="utf-8")
    head = p.read_text(encoding="utf-8")[:2000]
    plugin = JSONPlugin()
    assert plugin.can_parse(p, head)
    chat = plugin.parse(p)
    assert len(chat.messages) == 1


def test_builtin_text_plugin(tmp_path):
    p = tmp_path / "log.txt"
    p.write_text("User:\nhello\n\nModel:\nworld\n", encoding="utf-8")
    head = p.read_text(encoding="utf-8")[:2000]
    plugin = TextPlugin()
    assert plugin.can_parse(p, head)
    chat = plugin.parse(p)
    assert len(chat.messages) == 2


def test_claude_plugin(tmp_path):
    # Claude format with chat_messages
    data = {
        "name": "Claude chat",
        "chat_messages": [
            {"sender": "human", "text": "hello"},
            {"sender": "assistant", "text": "hi there"}
        ]
    }
    p = tmp_path / "claude.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    head = p.read_text(encoding="utf-8")[:2000]
    plugin = ClaudePlugin()
    assert plugin.can_parse(p, head)
    chat = plugin.parse(p)
    assert len(chat.messages) == 2
    assert chat.messages[0].role == "user"
    assert chat.messages[1].role == "model"


def test_chatgpt_plugin(tmp_path):
    # ChatGPT mapping format
    data = {
        "title": "Test ChatGPT",
        "mapping": {
            "node1": {
                "parent": None,
                "message": {
                    "author": {"role": "user"},
                    "content": {"parts": ["hello"]},
                    "create_time": 1
                }
            },
            "node2": {
                "parent": "node1",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"parts": ["hi"]},
                    "create_time": 2
                }
            }
        },
        "current_node": "node2"
    }
    p = tmp_path / "chatgpt.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    head = p.read_text(encoding="utf-8")[:2000]
    plugin = ChatGPTPlugin()
    assert plugin.can_parse(p, head)
    chat = plugin.parse(p)
    assert len(chat.messages) == 2


def test_registry_load():
    reg = PluginRegistry()
    reg.load_builtin()
    assert len(reg.plugins) >= 4
    names = [p.name for p in reg.plugins]
    assert "builtin_json" in names
    assert "claude" in names
    assert "chatgpt" in names
