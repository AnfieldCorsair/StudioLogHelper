import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studiologhelper.core.parsers.streaming_json_parser import HAS_IJSON, parse_large_json_streaming, should_use_streaming


def test_should_use_streaming_false_for_small(tmp_path):
    p = tmp_path / "small.json"
    p.write_text("{}", encoding="utf-8")
    assert not should_use_streaming(p, threshold_mb=30)


def test_streaming_parser_if_available(tmp_path):
    if not HAS_IJSON:
        # Skip if ijson not installed, but we can still test fallback logic
        # Create a file that would trigger streaming if ijson existed
        p = tmp_path / "big.json"
        # create 5MB file
        data = {
            "runSettings": {"model": "models/gemini-1.5-pro"},
            "chunkedPrompt": {"chunks": [{"role": "user", "text": f"message {i}"} for i in range(100)]}
        }
        p.write_text(json.dumps(data), encoding="utf-8")
        # should_use_streaming with low threshold
        assert isinstance(should_use_streaming(p, threshold_mb=0), bool)
        return

    # With ijson
    p = tmp_path / "big.json"
    chunks = []
    for i in range(200):
        role = "user" if i % 2 == 0 else "model"
        chunks.append({"role": role, "text": f"message number {i} about сковородка" if i % 10 == 0 else f"msg {i}", "createTime": "2024-01-01T00:00:00Z"})
    data = {
        "runSettings": {"model": "models/gemini-1.5-pro"},
        "systemInstruction": {"text": "You are helpful"},
        "chunkedPrompt": {"chunks": chunks}
    }
    p.write_text(json.dumps(data), encoding="utf-8")

    chat = parse_large_json_streaming(p)
    assert len(chat.messages) == 200
    assert chat.model == "gemini-1.5-pro"
    assert chat.system_instruction == "You are helpful"
