# -*- coding: utf-8 -*-
"""Unit tests for HTML sanitization, URL safety, plugin safe mode, and search worker."""

from pathlib import Path
from studiologhelper.core.models import ChatLog, Message
from studiologhelper.core.plugins import PluginRegistry, is_safe_mode, set_safe_mode
from studiologhelper.core.security import is_safe_url, sanitize_html, sanitize_url
from studiologhelper.ui.workers.search_worker import SearchWorker


def test_html_and_xss_sanitization():
    # 1. Strip script tags
    dirty_html = '<p>Hello <script>alert("xss")</script>World</p>'
    clean = sanitize_html(dirty_html)
    assert "<script>" not in clean
    assert "alert" not in clean
    assert "Hello" in clean and "World" in clean

    # 2. Strip dangerous iframes and objects
    dirty_iframe = '<iframe src="https://evil.com"></iframe><object data="test"></object>'
    clean_iframe = sanitize_html(dirty_iframe)
    assert "<iframe" not in clean_iframe
    assert "<object" not in clean_iframe

    # 3. Strip event handlers (onload, onerror, onclick)
    dirty_attr = '<div onclick="stealCookies()" onmouseover="evil()">Content</div>'
    clean_attr = sanitize_html(dirty_attr)
    assert "onclick" not in clean_attr
    assert "onmouseover" not in clean_attr
    assert "Content" in clean_attr

    # 4. Strip javascript: URLs
    dirty_js_link = '<a href="javascript:alert(1)">Click me</a>'
    clean_js_link = sanitize_html(dirty_js_link)
    assert "javascript:" not in clean_js_link

    # 5. Add rel="noopener noreferrer" to external links
    ext_link = '<a href="https://example.com">Example</a>'
    clean_ext = sanitize_html(ext_link)
    assert 'rel="noopener noreferrer"' in clean_ext


def test_url_safety_check():
    assert is_safe_url("https://example.com/log") is True
    assert is_safe_url("http://localhost:8080") is True
    assert is_safe_url("mailto:user@example.com") is True
    assert is_safe_url("#block_1") is True

    # Dangerous URLs
    assert is_safe_url("javascript:alert(1)") is False
    assert is_safe_url("vbscript:msgbox(1)") is False
    assert is_safe_url("data:text/html,<script>alert(1)</script>") is False
    assert is_safe_url("file:///etc/passwd") is False

    assert sanitize_url("javascript:alert(1)") == "#"
    assert sanitize_url("https://google.com") == "https://google.com"


def test_plugin_safe_mode(tmp_path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "user_plugin.py"
    plugin_file.write_text("PLUGIN = None\n", encoding="utf-8")

    registry = PluginRegistry()

    # 1. When safe mode is enabled, directory loading is skipped
    set_safe_mode(True)
    assert is_safe_mode() is True
    registry.load_from_directory(plugin_dir)
    assert len(registry.loaded_plugin_files) == 0

    # 2. Reset safe mode
    set_safe_mode(False)
    assert is_safe_mode() is False


def test_search_worker_execution_and_abort():
    chat = ChatLog(
        title="Testing Chat",
        path="/tmp/test.json",
        messages=[
            Message(role="user", text="Первый вопрос о сковородках"),
            Message(role="model", text="Ответ про сковороду и приготовление"),
        ],
    )
    worker = SearchWorker(
        mode="hybrid_chats",
        query="сковорода",
        chats=[chat],
    )

    results = []
    worker.resultsReady.connect(lambda hits: results.extend(hits))
    worker.run()

    assert len(results) >= 1
    assert results[0].msg_num in (1, 2)

    # Test abort cancellation
    worker_abort = SearchWorker(mode="hybrid_chats", query="test", chats=[chat])
    worker_abort.abort()
    assert worker_abort._abort is True
