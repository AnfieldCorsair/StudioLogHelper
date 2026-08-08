import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studiologhelper.core.models import ChatLog, Message, Attachment
from studiologhelper.core.exporters.base import ExportOptions, THOUGHTS_INCLUDE, THOUGHTS_EXCLUDE, CONTENT_ALL, CONTENT_ANSWERS
from studiologhelper.core.exporters.manager import export_chat


def make_sample_chat():
    chat = ChatLog(title="Test Chat", model="gemini-1.5-pro", source_format="json")
    chat.messages = [
        Message(role="user", text="Hello, model!", token_count=5, create_time="2024-01-01T00:00:00Z"),
        Message(role="model", text="Hi user! **Bold** and `code`", thoughts=["thinking..."], token_count=10),
    ]
    return chat


def test_txt_export():
    chat = make_sample_chat()
    opts = ExportOptions(fmt="txt", content=CONTENT_ALL, thoughts=THOUGHTS_EXCLUDE)
    main, sep = export_chat(chat, opts)
    assert "Test Chat" in main
    assert "Hello, model!" in main
    assert "Hi user!" in main


def test_txt_export_answers_only():
    chat = make_sample_chat()
    opts = ExportOptions(fmt="txt", content=CONTENT_ANSWERS)
    main, _ = export_chat(chat, opts)
    assert "Hello" not in main
    assert "Hi user" in main


def test_md_export_with_thoughts():
    chat = make_sample_chat()
    opts = ExportOptions(fmt="md", content=CONTENT_ALL, thoughts=THOUGHTS_INCLUDE)
    main, _ = export_chat(chat, opts)
    assert "thinking" in main.lower()


def test_html_export():
    chat = make_sample_chat()
    opts = ExportOptions(fmt="html", content=CONTENT_ALL, render_markdown=True)
    main, _ = export_chat(chat, opts)
    assert "<html" in main.lower()
    assert "Test Chat" in main


def test_json_export():
    chat = make_sample_chat()
    opts = ExportOptions(fmt="json")
    main, _ = export_chat(chat, opts)
    import json
    data = json.loads(main)
    assert data["title"] == "Test Chat"
    assert len(data["messages"]) == 2


def test_jsonl_export():
    chat = make_sample_chat()
    opts = ExportOptions(fmt="jsonl")
    main, _ = export_chat(chat, opts)
    lines = [l for l in main.splitlines() if l.strip()]
    assert len(lines) == 2
