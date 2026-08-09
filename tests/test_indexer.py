import sys
from pathlib import Path
import tempfile
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studiologhelper.indexer import SearchIndex
from studiologhelper.core.models import ChatLog, Message


def test_indexer_basic(tmp_path):
    # Create 2 fake log files
    log1 = tmp_path / "log1.json"
    log1.write_text(json.dumps({
        "runSettings": {"model": "gemini"},
        "chunkedPrompt": {"chunks": [
            {"role": "user", "text": "hello world about сковородка"},
            {"role": "model", "text": "answer about frying pan"}
        ]}
    }), encoding="utf-8")

    log2 = tmp_path / "log2.txt"
    log2.write_text("User:\nsecond log\n\nModel:\ncontains сковородка again\n", encoding="utf-8")

    db_path = tmp_path / "index.db"
    with SearchIndex(db_path) as idx:
        stats = idx.index_paths([str(tmp_path)], recursive=True, use_threads=False)
        assert stats.added >= 2
        assert stats.skipped == 0

        hits = idx.search("сковородка", limit=10)
        assert len(hits) >= 1

        # second run should be skipped
        stats2 = idx.index_paths([str(tmp_path)], recursive=True, use_threads=False)
        assert stats2.skipped >= 2

        # search with filters
        hits_user = idx.search("world", role="user", limit=10)
        assert any(h.role == "user" for h in hits_user)

        st = idx.stats()
        assert st["files"] >= 2
        assert st["messages"] >= 3


def test_indexer_batch_optimization(tmp_path):
    # Create 60 files to test batch size 50
    files = []
    for i in range(60):
        p = tmp_path / f"log_{i}.json"
        p.write_text(json.dumps({
            "chunkedPrompt": {"chunks": [{"role": "user", "text": f"file {i} contains keyword batchtest"}]}
        }), encoding="utf-8")
        files.append(str(p))

    db_path = tmp_path / "batch.db"
    with SearchIndex(db_path) as idx:
        stats = idx.index_paths(files, recursive=False, use_threads=False, batch_size=50)
        assert stats.added == 60
        hits = idx.search("batchtest", limit=100)
        assert len(hits) == 60
