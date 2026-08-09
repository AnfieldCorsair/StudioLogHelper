# -*- coding: utf-8 -*-
"""Text plugin"""

from pathlib import Path
from ..parsers.text_parser import parse_text_log
from ...utils.encoding import detect_encoding_and_decode
from ..parsers.detector import _looks_like_text_log_head


class TextPlugin:
    name = "builtin_text"
    description = "Arena AI / cleaned TXT/MD exports"
    extensions = [".txt", ".md", ".log", ".text"]

    def can_parse(self, path: Path, head: str) -> bool:
        return _looks_like_text_log_head(head)

    def parse(self, path: Path, text_options=None):
        data_bytes = Path(path).read_bytes()
        text = detect_encoding_and_decode(data_bytes)
        return parse_text_log(text, str(path), text_options)


def get_plugin():
    return TextPlugin()
