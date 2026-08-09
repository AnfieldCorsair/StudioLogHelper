# -*- coding: utf-8 -*-
"""Встроенный JSON плагин — обертка над существующим парсером."""

from pathlib import Path
from ..parsers.json_parser import parse_data, _json_loads
from ...utils.encoding import detect_encoding_and_decode


class JSONPlugin:
    name = "builtin_json"
    description = "Google AI Studio JSON logs"
    extensions = [".json", ""]  # без расширения тоже

    def can_parse(self, path: Path, head: str) -> bool:
        h = head.lstrip("\ufeff\x00\n\r\t ")
        if h.startswith("{") and ('"chunkedPrompt"' in h[:4096] or '"runSettings"' in h[:2048]):
            return True
        return False

    def parse(self, path: Path, text_options=None):
        data_bytes = Path(path).read_bytes()
        text = detect_encoding_and_decode(data_bytes)
        data = _json_loads(text)
        return parse_data(data, str(path))


def get_plugin():
    return JSONPlugin()
