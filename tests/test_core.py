import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studiologhelper.core.parsers.text_parser import parse_text_log
from studiologhelper.core.parsers.base import TextParseOptions
from studiologhelper.core.models import ChatLog


def test_arena_text_log_roles():
    text = """Arena Side-by-Side Chat

User:
hello

Right AI:
answer

User:
again

Right model:
ok
"""
    chat = parse_text_log(text, "arena.txt")
    assert len(chat.messages) == 4
    assert [m.role for m in chat.messages] == ["user", "model", "user", "model"]
    assert chat.model == "Arena AI"


def test_numbered_default_is_model_answers():
    text = "#1: answer one\n\n#2: answer two\n"
    chat = parse_text_log(text, "numbered.txt")
    assert [m.role for m in chat.messages] == ["model", "model"]


def test_numbered_can_alternate():
    text = "#1: hello\n\n#2: answer\n"
    opts = TextParseOptions(numbered_mode="alternating")
    chat = parse_text_log(text, "numbered.txt", opts)
    assert [m.role for m in chat.messages] == ["user", "model"]


def test_clean_txt_export_roundtrip(tmp_path):
    from studiologhelper.core.parsers.parser import parse_file
    from studiologhelper.core.exporters.manager import export_to_files
    from studiologhelper.core.exporters.base import ExportOptions

    text = "User:\nhello\n\nModel:\nanswer\n"
    src = tmp_path / "src.txt"
    src.write_text(text, encoding="utf-8")
    chat = parse_file(src)
    opts = ExportOptions(metadata=True)
    # Use manager export_chat for logic
    from studiologhelper.core.exporters.txt import TxtExporter
    exporter = TxtExporter()
    exported, _ = exporter.export(chat, opts)
    out = tmp_path / "exported.txt"
    out.write_text(exported, encoding="utf-8")
    parsed = parse_file(out)
    assert len(parsed.messages) == 2
    assert parsed.user_count == 1
    assert parsed.model_count == 1
