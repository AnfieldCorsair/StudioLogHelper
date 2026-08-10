# -*- coding: utf-8 -*-
"""Tests for markdown safety (no network leaks) and virtual view model."""

from studiologhelper.core.markdown import markdown_to_html
from studiologhelper.core.models import ChatLog, Message


def test_markdown_no_network_images():
    # Verify that external image markdown is safely converted to badge, not <img>
    md_text = "Check this diagram: ![Architecture](https://malicious-or-slow-site.com/image.png) and link [Docs](https://docs.ai)"
    html = markdown_to_html(md_text)
    assert "<img" not in html.lower()
    assert "https://malicious-or-slow-site.com/image.png" in html
    assert "Architecture" in html


def test_virtual_model_basic():
    try:
        from studiologhelper.ui.widgets.virtual_view import MessageListModel
    except ImportError:
        return  # Headless test runner without PyQt6

    chat = ChatLog(
        title="Big Chat",
        model="gemini-1.5-pro",
        path="/tmp/big.json",
        messages=[
            Message(role="user", text="Prompt 1"),
            Message(role="model", text="Answer 1", thoughts=["Thinking step 1"]),
            Message(role="user", text="Prompt 2"),
        ],
    )
    model = MessageListModel()
    model.set_chat(chat, collapse_long=True, preview_chars=100)
    assert model.rowCount() == 3

    msg0 = model.data(model.index(0), MessageListModel.MessageRole)
    assert msg0.text == "Prompt 1"

    # Toggle expand
    assert not model.is_expanded(0)
    model.toggle_expanded(0)
    assert model.is_expanded(0)

    # Set all collapsed
    model.set_all_collapsed(False)
    assert model.is_expanded(1)
    model.set_all_collapsed(True)
    assert not model.is_expanded(1)
