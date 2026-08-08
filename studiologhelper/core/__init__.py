# -*- coding: utf-8 -*-
"""Core package — facades for backward compatibility"""

from .models import Attachment, ChatLog, Message
from .exceptions import ParseError
from .parsers import (
    TextParseOptions,
    parse_file,
    parse_data,
    parse_text_log,
    looks_like_log,
)
from .scanner import scan_folder
from .exporters import ExportOptions, export_to_files, export_chat
from .exporters.base import (
    THOUGHTS_EXCLUDE,
    THOUGHTS_INCLUDE,
    THOUGHTS_SEPARATE,
    CONTENT_ALL,
    CONTENT_PROMPTS,
    CONTENT_ANSWERS,
    CONTENT_THOUGHTS,
    CONTENT_SUFFIX,
    EXT,
)
from .markdown import markdown_to_html
from .models import (
    COPY_ALL,
    COPY_PROMPTS,
    COPY_ANSWERS,
    COPY_THOUGHTS,
    chat_to_clipboard_text,
    message_copy_text,
)

__all__ = [
    "Attachment",
    "Message",
    "ChatLog",
    "ParseError",
    "TextParseOptions",
    "parse_file",
    "parse_data",
    "parse_text_log",
    "looks_like_log",
    "scan_folder",
    "ExportOptions",
    "export_to_files",
    "export_chat",
    "THOUGHTS_EXCLUDE",
    "THOUGHTS_INCLUDE",
    "THOUGHTS_SEPARATE",
    "CONTENT_ALL",
    "CONTENT_PROMPTS",
    "CONTENT_ANSWERS",
    "CONTENT_THOUGHTS",
    "COPY_ALL",
    "COPY_PROMPTS",
    "COPY_ANSWERS",
    "COPY_THOUGHTS",
    "markdown_to_html",
    "chat_to_clipboard_text",
    "message_copy_text",
]
