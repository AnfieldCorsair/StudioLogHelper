# -*- coding: utf-8 -*-
"""Оптимизированный поисковый индекс — батчи, ThreadPool, улучшенные PRAGMA."""

from __future__ import annotations

import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..core.parsers.detector import looks_like_log
from ..core.parsers.parser import parse_file
from ..utils.encoding import read_text_file, detect_encoding_and_decode
from ..utils.paths import get_index_db_path
from .text_splitter import split_text_blocks
from .query import sanitize_query

KIND_LOG = "log"
KIND_TXT = "txt"

TEXT_SUFFIXES = {".txt", ".md", ".log", ".text"}
MAX_TXT_SIZE = 50 * 1024 * 1024
DEFAULT_DB = get_index_db_path()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id        INTEGER PRIMARY KEY,
    path      TEXT UNIQUE NOT NULL,
    kind      TEXT NOT NULL DEFAULT 'log',
    mtime     REAL NOT NULL,
    size      INTEGER NOT NULL,
    title     TEXT,
    model     TEXT,
    msg_count INTEGER,
    indexed_at REAL
);
CREATE VIRTUAL TABLE IF NOT EXISTS messages USING fts5(
    body,
    role UNINDEXED,
    is_thought UNINDEXED,
    file_id UNINDEXED,
    msg_num UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
"""


@dataclass
class IndexStats:
    added: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0
    errors: list = field(default_factory=list)
    seconds: float = 0.0

    def summary(self) -> str:
        return (
            f"added {self.added}, updated {self.updated}, "
            f"skipped {self.skipped}, removed {self.removed}, "
            f"errors {len(self.errors)}, {self.seconds:.1f}s"
        )


@dataclass
class SearchHit:
    path: str
    title: str
    model: str
    kind: str
    msg_num: int
    role: str
    is_thought: bool
    snippet: str
    rank: float


def is_text_file(path) -> bool:
    p = Path(path)
    return p.is_file() and p.suffix.lower() in TEXT_SUFFIXES


class SearchIndex:
    """Поисковый индекс с оптимизациями: батч транзакции, пул парсеров."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.con.executescript(_SCHEMA)
        self._migrate()
        # Оптимизированные PRAGMA для скорости
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")
        self.con.execute("PRAGMA cache_size=-64000")  # 64MB cache
        self.con.execute("PRAGMA temp_store=MEMORY")
        self.con.execute("PRAGMA foreign_keys=OFF")

    def _migrate(self):
        cols = {r[1] for r in self.con.execute("PRAGMA table_info(files)")}
        if "kind" not in cols:
            with self.con:
                self.con.execute("ALTER TABLE files ADD COLUMN kind TEXT NOT NULL DEFAULT 'log'")

    # ---- сбор файлов ----
    def collect_targets(self, paths, recursive: bool = True, include_logs: bool = True, include_txt: bool = True) -> list[tuple[str, str]]:
        known = dict(self.con.execute("SELECT path, kind FROM files"))
        out: list[tuple[str, str]] = []
        seen = set()

        def add(p: str, kind: str):
            if p not in seen:
                seen.add(p)
                out.append((p, kind))

        def classify(f: Path):
            sp = str(f)
            k = known.get(sp)
            if k == KIND_TXT and include_txt:
                return KIND_TXT
            if k == KIND_LOG and include_logs:
                return KIND_LOG
            if include_logs and looks_like_log(f):
                return KIND_LOG
            if include_txt and is_text_file(f):
                return KIND_TXT
            return None

        for raw in paths:
            p = Path(raw)
            if p.is_file():
                k = classify(p)
                if k is None and include_logs:
                    k = KIND_LOG
                if k:
                    add(str(p), k)
                continue
            if not p.is_dir():
                continue
            # Используем scanner для единообразия
            from ..core.scanner import _walk_safe

            for f in _walk_safe(p, recursive):
                k = classify(f)
                if k:
                    add(str(f), k)
        return out

    # ---- подготовка данных ----
    @staticmethod
    def _prepare_log(path):
        chat = parse_file(path)
        rows = []
        for num, msg in enumerate(chat.messages, 1):
            if msg.text.strip():
                rows.append((msg.text, msg.role, 0, num))
            for t in msg.thoughts:
                if t.strip():
                    rows.append((t, "model", 1, num))
        return (chat.title, chat.model, len(chat.messages)), rows

    @staticmethod
    def _prepare_txt(path, st):
        if st.st_size > MAX_TXT_SIZE:
            raise ValueError(f"file > {MAX_TXT_SIZE // (1024*1024)} MB, skipped")
        try:
            text = read_text_file(Path(path), max_size=MAX_TXT_SIZE)
        except ValueError as e:
            raise e
        blocks = split_text_blocks(text)
        rows = [(b, "text", 0, n) for n, b in enumerate(blocks, 1)]
        return (Path(path).stem, "", len(blocks)), rows

    def _prepare_one(self, item):
        """Для пула: (path, kind) -> (meta, rows, file_stat) or error."""
        f, kind = item
        try:
            st = Path(f).stat()
        except OSError as ex:
            return (f, None, None, None, f"{f}: {ex}")

        try:
            if kind == KIND_TXT:
                meta, rows = self._prepare_txt(f, st)
            else:
                meta, rows = self._prepare_log(f)
        except Exception as ex:
            return (f, None, None, st, f"{f}: {ex}")
        return (f, meta, rows, st, None)

    def index_paths(self, paths, recursive: bool = True, include_logs: bool = True, include_txt: bool = True, progress=None, prune: bool = True, batch_size: int = 50, use_threads: bool = True) -> IndexStats:
        """Инкрементальная индексация с батчами и потоками."""
        t0 = time.time()
        stats = IndexStats()
        targets = self.collect_targets(paths, recursive, include_logs, include_txt)

        # Быстрый skip по mtime/size без парсинга
        to_parse: list[tuple[str, str]] = []
        for f, kind in targets:
            try:
                st = Path(f).stat()
            except OSError as ex:
                stats.errors.append(f"{f}: {ex}")
                continue
            row = self.con.execute("SELECT id, mtime, size FROM files WHERE path=?", (f,)).fetchone()
            if row and abs(row[1] - st.st_mtime) < 1e-6 and row[2] == st.st_size:
                stats.skipped += 1
                continue
            to_parse.append((f, kind))

        total_to_parse = len(to_parse)
        done = 0

        # Подготовка с потоками
        prepared = []
        if use_threads and total_to_parse > 10:
            with ThreadPoolExecutor(max_workers=4) as ex:
                futures = {ex.submit(self._prepare_one, item): item for item in to_parse}
                for fut in as_completed(futures):
                    res = fut.result()
                    path, meta, rows, st, err = res
                    if err:
                        stats.errors.append(err)
                    else:
                        prepared.append(res)
                    done += 1
                    if progress:
                        progress(done, total_to_parse, path)
        else:
            for item in to_parse:
                res = self._prepare_one(item)
                path, meta, rows, st, err = res
                if err:
                    stats.errors.append(err)
                else:
                    prepared.append(res)
                done += 1
                if progress:
                    progress(done, total_to_parse, path)

        # Батч-запись в БД — одна транзакция на batch_size файлов
        # Это даёт 10x ускорение vs транзакция на файл
        for i in range(0, len(prepared), batch_size):
            batch = prepared[i : i + batch_size]
            with self.con:  # транзакция
                for f, meta, rows, st, err in batch:
                    title, model, msg_count = meta
                    row = self.con.execute("SELECT id FROM files WHERE path=?", (f,)).fetchone()
                    if row:
                        file_id = row[0]
                        self.con.execute("DELETE FROM messages WHERE file_id=?", (file_id,))
                        self.con.execute(
                            "UPDATE files SET kind=?, mtime=?, size=?, title=?, model=?, msg_count=?, indexed_at=? WHERE id=?",
                            (self._get_kind(f), st.st_mtime, st.st_size, title, model, msg_count, time.time(), file_id),
                        )
                        stats.updated += 1
                    else:
                        cur = self.con.execute(
                            "INSERT INTO files (path, kind, mtime, size, title, model, msg_count, indexed_at) VALUES (?,?,?,?,?,?,?,?)",
                            (f, self._get_kind(f), st.st_mtime, st.st_size, title, model, msg_count, time.time()),
                        )
                        file_id = cur.lastrowid
                        stats.added += 1

                    # executemany для сообщений
                    self.con.executemany(
                        "INSERT INTO messages (body, role, is_thought, file_id, msg_num) VALUES (?,?,?,?,?)",
                        [(b, r, th, file_id, n) for b, r, th, n in rows],
                    )

        if progress:
            progress(total_to_parse, total_to_parse, "")

        if prune:
            stats.removed = self.prune_missing()

        stats.seconds = time.time() - t0
        return stats

    def _get_kind(self, path):
        # determine kind by content again? For simplicity, return log if looks_like_log else txt
        p = Path(path)
        if p.suffix.lower() in TEXT_SUFFIXES and not looks_like_log(p):
            return KIND_TXT
        return KIND_LOG

    def prune_missing(self) -> int:
        gone = []
        for fid, path in self.con.execute("SELECT id, path FROM files"):
            if not Path(path).exists():
                gone.append(fid)
        if gone:
            with self.con:
                qs = ",".join("?" * len(gone))
                self.con.execute(f"DELETE FROM messages WHERE file_id IN ({qs})", gone)
                self.con.execute(f"DELETE FROM files WHERE id IN ({qs})", gone)
        return len(gone)

    def search(self, query: str, role: Optional[str] = None, thoughts: Optional[bool] = None, model: Optional[str] = None, path_like: Optional[str] = None, kind: Optional[str] = None, limit: int = 100) -> list[SearchHit]:
        fts = sanitize_query(query)
        if not fts:
            return []
        sql = [
            "SELECT f.path, f.title, f.model, f.kind, m.msg_num, m.role,",
            "m.is_thought,",
            "snippet(messages, 0, '«', '»', ' … ', 12) AS snip,",
            "bm25(messages) AS rank",
            "FROM messages m JOIN files f ON f.id = m.file_id",
            "WHERE messages MATCH ?",
        ]
        args: list = [fts]
        if role in ("user", "model", "text"):
            sql.append("AND m.role = ?")
            args.append(role)
        if thoughts is True:
            sql.append("AND m.is_thought = 1")
        elif thoughts is False:
            sql.append("AND m.is_thought = 0")
        if model:
            sql.append("AND f.model LIKE ?")
            args.append(f"%{model}%")
        if path_like:
            sql.append("AND f.path LIKE ?")
            args.append(f"%{path_like}%")
        if kind in (KIND_LOG, KIND_TXT):
            sql.append("AND f.kind = ?")
            args.append(kind)
        sql.append("ORDER BY rank LIMIT ?")
        args.append(int(limit))

        try:
            rows = self.con.execute(" ".join(sql), args).fetchall()
        except sqlite3.OperationalError:
            return []
        return [
            SearchHit(path=r[0], title=r[1] or "", model=r[2] or "", kind=r[3] or KIND_LOG, msg_num=int(r[4]), role=r[5], is_thought=bool(int(r[6])), snippet=r[7], rank=float(r[8]))
            for r in rows
        ]

    def stats(self) -> dict:
        nf = self.con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        nl = self.con.execute("SELECT COUNT(*) FROM files WHERE kind='log'").fetchone()[0]
        nt = self.con.execute("SELECT COUNT(*) FROM files WHERE kind='txt'").fetchone()[0]
        nm = self.con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        size = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {"files": nf, "logs": nl, "texts": nt, "messages": nm, "db_path": str(self.db_path), "db_size": size}

    def optimize(self):
        with self.con:
            self.con.execute("INSERT INTO messages(messages) VALUES('optimize')")
        self.con.commit()
        old = self.con.isolation_level
        self.con.isolation_level = None
        try:
            self.con.execute("VACUUM")
        finally:
            self.con.isolation_level = old

    def clear(self):
        with self.con:
            self.con.execute("DELETE FROM messages")
            self.con.execute("DELETE FROM files")

    def close(self):
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
