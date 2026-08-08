"""Тесты оптимизаций: scanner, encoding, indexer batch, translator"""

import sys
from pathlib import Path
import tempfile
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studiologhelper.core.parsers.detector import looks_like_log, BINARY_EXTS
from studiologhelper.core.scanner import scan_folder, _walk_safe
from studiologhelper.utils.encoding import detect_encoding_and_decode, read_text_file
from studiologhelper.i18n.translator import Translator
from studiologhelper.indexer.text_splitter import split_text_blocks
from studiologhelper.indexer.query import sanitize_query


def test_binary_ext_skipped():
    # Ensure BINARY_EXTS contains typical binaries
    assert ".png" in BINARY_EXTS
    assert ".exe" in BINARY_EXTS
    # create a fake binary file
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
        fname = f.name
    try:
        assert not looks_like_log(fname)
    finally:
        os.unlink(fname)


def test_encoding_detection_utf8():
    b = "привет мир".encode("utf-8")
    s = detect_encoding_and_decode(b)
    assert "привет" in s


def test_encoding_detection_bom():
    b = b"\xef\xbb\xbfhello world"
    s = detect_encoding_and_decode(b)
    assert "hello" in s


def test_scan_folder_skip_hidden_and_binary(tmp_path):
    # create structure
    (tmp_path / "valid.json").write_text('{"chunkedPrompt": {"chunks": [{"role":"user","text":"hi"}]}}', encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / ".hidden").write_text("secret", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git", encoding="utf-8")

    res = scan_folder(tmp_path, recursive=True)
    # only valid.json should be found
    assert any("valid.json" in r for r in res)
    assert not any("image.png" in r for r in res)
    assert not any(".hidden" in r for r in res)
    assert not any(".git" in r for r in res)


def test_split_blocks():
    text = "Para1\n\nPara2\n\nPara3"
    blocks = split_text_blocks(text, target=10)
    assert len(blocks) >= 2
    assert "Para1" in blocks[0]


def test_sanitize_query():
    q = 'hello world "exact phrase"'
    sanitized = sanitize_query(q)
    assert '"exact phrase"' in sanitized
    assert "AND" in sanitized


def test_translator_no_global():
    tr1 = Translator("ru")
    tr2 = Translator("en")
    assert tr1.get_lang() == "ru"
    assert tr2.get_lang() == "en"
    # same key different lang
    assert tr1.tr("cancel") != tr2.tr("cancel") or tr1.tr("cancel") == "Отмена"
    tr1.set_lang("en")
    assert tr1.get_lang() == "en"
    assert tr1.tr("cancel") == tr2.tr("cancel")


def test_translator_format():
    tr = Translator("en")
    s = tr.tr("loaded_n", n=5)
    assert "5" in s


def test_walk_safe_no_symlink_loop(tmp_path):
    # On Unix we can create symlink loop. Just ensure _walk_safe doesn't crash
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "a.txt").write_text('{"chunkedPrompt":{"chunks":[{"role":"user","text":"hi"}]}}', encoding="utf-8")
    # create symlink inside sub pointing to parent (if allowed)
    try:
        (sub / "link_to_parent").symlink_to(tmp_path)
    except (OSError, NotImplementedError):
        pass
    files = list(_walk_safe(tmp_path, recursive=True))
    # should at least find a.txt
    assert len(files) >= 1
