import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import core


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
    chat = core.parse_text_log(text, "arena.txt")
    assert len(chat.messages) == 4
    assert [m.role for m in chat.messages] == ["user", "model", "user", "model"]
    assert chat.model == "Arena AI"


def test_numbered_default_is_model_answers():
    text = "#1: answer one\n\n#2: answer two\n"
    chat = core.parse_text_log(text, "numbered.txt")
    assert [m.role for m in chat.messages] == ["model", "model"]


def test_numbered_can_alternate():
    text = "#1: hello\n\n#2: answer\n"
    opts = core.TextParseOptions(numbered_mode="alternating")
    chat = core.parse_text_log(text, "numbered.txt", opts)
    assert [m.role for m in chat.messages] == ["user", "model"]


def test_clean_txt_export_roundtrip(tmp_path):
    text = "User:\nhello\n\nModel:\nanswer\n"
    src = tmp_path / "src.txt"
    src.write_text(text, encoding="utf-8")
    chat = core.parse_file(src)
    exported, _ = core.export_txt(chat, core.ExportOptions(metadata=True))
    out = tmp_path / "exported.txt"
    out.write_text(exported, encoding="utf-8")
    parsed = core.parse_file(out)
    assert len(parsed.messages) == 2
    assert parsed.user_count == 1
    assert parsed.model_count == 1
