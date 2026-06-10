# -*- coding: utf-8 -*-
"""
indexer.py — инфраструктура «умного поиска» по большим массивам логов.

Архитектура (рассчитана на тысячи файлов с Google Drive):

  ┌────────────┐   scan    ┌─────────────┐   FTS5    ┌──────────────┐
  │ Папки/файлы├──────────►│ SearchIndex ├──────────►│ SQLite *.db  │
  └────────────┘ инкремент │  (этот файл)│  запросы  │ files + FTS  │
                           └─────────────┘           └──────────────┘

Ключевые решения:
  * SQLite + FTS5 (встроен в Python) — никаких внешних зависимостей,
    миллионы сообщений ищутся за миллисекунды.
  * Инкрементальность: файл переиндексируется только если изменились
    mtime/размер. Повторный прогон по гигантской папке почти мгновенный.
  * Токенизатор unicode61 + remove_diacritics — нормальный поиск по
    русскому/английскому, поддержка префиксов («сковород*»).
  * Фильтры: роль (user/model/thought), модель, конкретный файл.
  * БД лежит в ~/.aistudio_parser/index.db (можно указать свою).

Использование:
    from indexer import SearchIndex
    idx = SearchIndex()                     # или SearchIndex("my.db")
    stats = idx.index_paths(["D:/Drive"])   # инкрементально
    hits = idx.search("сковородка", role="model", limit=50)
    idx.close()

CLI:  python cli.py index <папки>   /   python cli.py search "<запрос>"
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import core

DEFAULT_DB = Path.home() / ".aistudio_parser" / "index.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id        INTEGER PRIMARY KEY,
    path      TEXT UNIQUE NOT NULL,
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
"""


@dataclass
class IndexStats:
    added: int = 0
    updated: int = 0
    skipped: int = 0       # не изменились
    removed: int = 0       # исчезли с диска
    errors: list = field(default_factory=list)
    seconds: float = 0.0

    def summary(self) -> str:
        return (f"добавлено {self.added}, обновлено {self.updated}, "
                f"без изменений {self.skipped}, удалено {self.removed}, "
                f"ошибок {len(self.errors)}, {self.seconds:.1f} c")


@dataclass
class SearchHit:
    path: str
    title: str
    model: str
    msg_num: int          # номер сообщения в чате (1-based)
    role: str             # user | model
    is_thought: bool
    snippet: str          # фрагмент с подсветкой
    rank: float


def _sanitize_query(q: str) -> str:
    """Превращает пользовательский ввод в безопасный FTS5-запрос.

    Слова соединяются через AND, к последнему добавляется * (префикс),
    фразы в кавычках сохраняются.
    """
    q = q.strip()
    if not q:
        return ""
    phrases = re.findall(r'"([^"]+)"', q)
    rest = re.sub(r'"[^"]*"', " ", q)
    words = re.findall(r"[\w\d_]+", rest, re.UNICODE)
    parts = [f'"{p}"' for p in phrases]
    for i, w in enumerate(words):
        if i == len(words) - 1 and not phrases:
            parts.append(f'"{w}"*')
        else:
            parts.append(f'"{w}"')
    return " AND ".join(parts)


class SearchIndex:
    """Поисковый индекс логов AI Studio на SQLite FTS5."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.db_path))
        self.con.executescript(_SCHEMA)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")

    # ---------------- индексация ----------------

    def index_paths(self, paths, recursive: bool = True,
                    progress=None) -> IndexStats:
        """Инкрементально индексирует файлы/папки.

        progress: optional callable(done:int, total:int, path:str)
        """
        t0 = time.time()
        stats = IndexStats()

        files: list = []
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                files.extend(core.scan_folder(p, recursive=recursive))
            elif p.is_file():
                files.append(str(p))

        # убрать дубли, сохранить порядок
        seen = set()
        files = [f for f in files if not (f in seen or seen.add(f))]

        for i, f in enumerate(files):
            if progress:
                progress(i, len(files), f)
            try:
                st = Path(f).stat()
            except OSError as ex:
                stats.errors.append(f"{f}: {ex}")
                continue

            row = self.con.execute(
                "SELECT id, mtime, size FROM files WHERE path=?", (f,)
            ).fetchone()
            if row and abs(row[1] - st.st_mtime) < 1e-6 and row[2] == st.st_size:
                stats.skipped += 1
                continue

            try:
                chat = core.parse_file(f)
            except (core.ParseError, OSError, ValueError) as ex:
                stats.errors.append(f"{f}: {ex}")
                continue

            with self.con:
                if row:
                    file_id = row[0]
                    self.con.execute(
                        "DELETE FROM messages WHERE file_id=?", (file_id,))
                    self.con.execute(
                        "UPDATE files SET mtime=?, size=?, title=?, model=?, "
                        "msg_count=?, indexed_at=? WHERE id=?",
                        (st.st_mtime, st.st_size, chat.title, chat.model,
                         len(chat.messages), time.time(), file_id))
                    stats.updated += 1
                else:
                    cur = self.con.execute(
                        "INSERT INTO files (path, mtime, size, title, model, "
                        "msg_count, indexed_at) VALUES (?,?,?,?,?,?,?)",
                        (f, st.st_mtime, st.st_size, chat.title, chat.model,
                         len(chat.messages), time.time()))
                    file_id = cur.lastrowid
                    stats.added += 1

                rows = []
                for num, msg in enumerate(chat.messages, 1):
                    if msg.text.strip():
                        rows.append((msg.text, msg.role, 0, file_id, num))
                    for t in msg.thoughts:
                        if t.strip():
                            rows.append((t, "model", 1, file_id, num))
                self.con.executemany(
                    "INSERT INTO messages (body, role, is_thought, file_id, "
                    "msg_num) VALUES (?,?,?,?,?)", rows)

        if progress:
            progress(len(files), len(files), "")
        stats.removed = self.prune_missing()
        stats.seconds = time.time() - t0
        return stats

    def prune_missing(self) -> int:
        """Удаляет из индекса файлы, которых больше нет на диске."""
        gone = []
        for fid, path in self.con.execute("SELECT id, path FROM files"):
            if not Path(path).exists():
                gone.append(fid)
        if gone:
            with self.con:
                qs = ",".join("?" * len(gone))
                self.con.execute(
                    f"DELETE FROM messages WHERE file_id IN ({qs})", gone)
                self.con.execute(
                    f"DELETE FROM files WHERE id IN ({qs})", gone)
        return len(gone)

    # ---------------- поиск ----------------

    def search(self, query: str, role: Optional[str] = None,
               thoughts: Optional[bool] = None, model: Optional[str] = None,
               path_like: Optional[str] = None, limit: int = 100) -> list:
        """Полнотекстовый поиск. Возвращает список SearchHit.

        role:     "user" | "model" | None (все)
        thoughts: True — только размышления, False — без них, None — все
        model:    подстрока имени модели
        path_like: подстрока пути файла
        """
        fts = _sanitize_query(query)
        if not fts:
            return []
        sql = ["SELECT f.path, f.title, f.model, m.msg_num, m.role,",
               "m.is_thought,",
               "snippet(messages, 0, '«', '»', ' … ', 12) AS snip,",
               "bm25(messages) AS rank",
               "FROM messages m JOIN files f ON f.id = m.file_id",
               "WHERE messages MATCH ?"]
        args: list = [fts]
        if role in ("user", "model"):
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
        sql.append("ORDER BY rank LIMIT ?")
        args.append(int(limit))

        try:
            rows = self.con.execute(" ".join(sql), args).fetchall()
        except sqlite3.OperationalError:
            return []
        return [SearchHit(path=r[0], title=r[1] or "", model=r[2] or "",
                          msg_num=int(r[3]), role=r[4],
                          is_thought=bool(int(r[5])), snippet=r[6],
                          rank=float(r[7]))
                for r in rows]

    # ---------------- сервис ----------------

    def stats(self) -> dict:
        nf = self.con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        nm = self.con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        size = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {"files": nf, "messages": nm, "db_path": str(self.db_path),
                "db_size": size}

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
