# -*- coding: utf-8 -*-
"""
indexer.py — инфраструктура «умного поиска» по большим массивам данных.

Индексируются два типа источников:
  1. Логи Google AI Studio (JSON, в т.ч. без расширения) — по сообщениям,
     с ролями user/model и флагом «размышление».
  2. Обычные текстовые файлы (.txt, .md, .log) — например, уже очищенные
     экспорты этой же программы. Текст бьётся на блоки по абзацам,
     чтобы сниппеты в результатах были осмысленными.

Архитектура (рассчитана на тысячи файлов с Google Drive):

  ┌────────────┐   scan    ┌─────────────┐   FTS5    ┌──────────────┐
  │ Папки/файлы├──────────►│ SearchIndex ├──────────►│ SQLite *.db  │
  └────────────┘ инкремент │  (этот файл)│  запросы  │ files + FTS  │
                           └─────────────┘           └──────────────┘

Ключевые решения:
  * SQLite + FTS5 (встроен в Python) — без внешних зависимостей,
    миллионы записей ищутся за миллисекунды (bm25 + сниппеты).
  * Инкрементальность: файл переиндексируется только если изменились
    mtime/размер. Повторный прогон по гигантской папке почти мгновенный.
  * Запись каждого файла — одна транзакция; вставка блоков — executemany.
  * Токенизатор unicode61 + remove_diacritics — нормальный поиск по
    русскому/английскому, поддержка префиксов («сковород*») и "фраз".
  * Фильтры: роль (user/model/text), размышления, модель, путь, тип файла.
  * БД лежит в ~/.aistudio_parser/index.db (можно указать свою).

Использование:
    from indexer import SearchIndex
    idx = SearchIndex()                       # или SearchIndex("my.db")
    stats = idx.index_paths(["D:/Drive"])     # инкрементально, логи + txt
    hits = idx.search("сковородка", role="model", limit=50)
    hits = idx.search("отчёт", kind="txt")    # только по текстовым файлам
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

KIND_LOG = "log"   # лог AI Studio
KIND_TXT = "txt"   # обычный текстовый файл

TEXT_SUFFIXES = {".txt", ".md", ".log", ".text"}
MAX_TXT_SIZE = 50 * 1024 * 1024     # 50 МБ — защита от случайного гиганта
BLOCK_TARGET = 1500                  # целевой размер блока текста, символов

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
    kind: str             # log | txt
    msg_num: int          # номер сообщения/блока (1-based)
    role: str             # user | model | text
    is_thought: bool
    snippet: str          # фрагмент с подсветкой
    rank: float


def split_text_blocks(text: str, target: int = BLOCK_TARGET) -> list:
    """Бьёт произвольный текст на блоки ~target символов по абзацам.

    Зачем: один FTS-документ на весь файл дал бы бесполезные сниппеты и
    грубый bm25; по абзацам — точные попадания и нумерация блоков.
    """
    paragraphs = re.split(r"\n\s*\n", text)
    blocks: list = []
    buf: list = []
    size = 0
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        # сверхдлинный абзац режем жёстко
        while len(p) > target * 2:
            blocks.append(p[:target * 2])
            p = p[target * 2:]
        if size + len(p) > target and buf:
            blocks.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(p)
        size += len(p)
    if buf:
        blocks.append("\n\n".join(buf))
    return blocks


def is_text_file(path) -> bool:
    p = Path(path)
    return p.is_file() and p.suffix.lower() in TEXT_SUFFIXES


def _read_text(path) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8", "utf-8-sig", "utf-16", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


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
    """Поисковый индекс логов AI Studio и текстовых файлов (SQLite FTS5)."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.db_path))
        self.con.executescript(_SCHEMA)
        self._migrate()
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")

    def _migrate(self):
        """Миграция старых БД (без колонки kind)."""
        cols = {r[1] for r in self.con.execute("PRAGMA table_info(files)")}
        if "kind" not in cols:
            with self.con:
                self.con.execute(
                    "ALTER TABLE files ADD COLUMN kind TEXT NOT NULL "
                    "DEFAULT 'log'")

    # ---------------- сбор файлов ----------------

    def collect_targets(self, paths, recursive: bool = True,
                        include_logs: bool = True,
                        include_txt: bool = True) -> list:
        """Возвращает [(path, kind), ...] без дублей.

        Оптимизация: для файлов, уже известных индексу, тип берётся из БД
        без чтения содержимого (экономит I/O при повторных прогонах).
        """
        known = dict(self.con.execute("SELECT path, kind FROM files"))
        out: list = []
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
            if include_txt and is_text_file(f):
                return KIND_TXT
            if include_logs and core.looks_like_log(f):
                return KIND_LOG
            return None

        for raw in paths:
            p = Path(raw)
            if p.is_file():
                k = classify(p)
                if k is None and include_logs:
                    k = KIND_LOG  # явно указанный файл — пробуем как лог
                if k:
                    add(str(p), k)
                continue
            if not p.is_dir():
                continue
            it = p.rglob("*") if recursive else p.glob("*")
            for f in sorted(it):
                if not f.is_file():
                    continue
                k = classify(f)
                if k:
                    add(str(f), k)
        return out

    # ---------------- индексация ----------------

    def index_paths(self, paths, recursive: bool = True,
                    include_logs: bool = True, include_txt: bool = True,
                    progress=None, prune: bool = True) -> IndexStats:
        """Инкрементально индексирует файлы/папки (логи + txt).

        progress: optional callable(done:int, total:int, path:str)
        """
        t0 = time.time()
        stats = IndexStats()
        targets = self.collect_targets(paths, recursive,
                                       include_logs, include_txt)

        for i, (f, kind) in enumerate(targets):
            if progress:
                progress(i, len(targets), f)
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
                if kind == KIND_TXT:
                    meta, rows = self._prepare_txt(f, st)
                else:
                    meta, rows = self._prepare_log(f)
            except (core.ParseError, OSError, ValueError) as ex:
                stats.errors.append(f"{f}: {ex}")
                continue

            title, model, msg_count = meta
            with self.con:
                if row:
                    file_id = row[0]
                    self.con.execute(
                        "DELETE FROM messages WHERE file_id=?", (file_id,))
                    self.con.execute(
                        "UPDATE files SET kind=?, mtime=?, size=?, title=?, "
                        "model=?, msg_count=?, indexed_at=? WHERE id=?",
                        (kind, st.st_mtime, st.st_size, title, model,
                         msg_count, time.time(), file_id))
                    stats.updated += 1
                else:
                    cur = self.con.execute(
                        "INSERT INTO files (path, kind, mtime, size, title, "
                        "model, msg_count, indexed_at) VALUES (?,?,?,?,?,?,?,?)",
                        (f, kind, st.st_mtime, st.st_size, title, model,
                         msg_count, time.time()))
                    file_id = cur.lastrowid
                    stats.added += 1

                self.con.executemany(
                    "INSERT INTO messages (body, role, is_thought, file_id, "
                    "msg_num) VALUES (?,?,?,?,?)",
                    [(b, r, th, file_id, n) for b, r, th, n in rows])

        if progress:
            progress(len(targets), len(targets), "")
        if prune:
            stats.removed = self.prune_missing()
        stats.seconds = time.time() - t0
        return stats

    @staticmethod
    def _prepare_log(path):
        chat = core.parse_file(path)
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
            raise ValueError(
                f"файл больше {MAX_TXT_SIZE // (1024*1024)} МБ, пропущен")
        text = _read_text(path)
        blocks = split_text_blocks(text)
        rows = [(b, "text", 0, n) for n, b in enumerate(blocks, 1)]
        return (Path(path).stem, "", len(blocks)), rows

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
               path_like: Optional[str] = None, kind: Optional[str] = None,
               limit: int = 100) -> list:
        """Полнотекстовый поиск. Возвращает список SearchHit.

        role:     "user" | "model" | "text" | None (все)
        thoughts: True — только размышления, False — без них, None — все
        model:    подстрока имени модели
        path_like: подстрока пути файла
        kind:     "log" | "txt" | None (все)
        """
        fts = _sanitize_query(query)
        if not fts:
            return []
        sql = ["SELECT f.path, f.title, f.model, f.kind, m.msg_num, m.role,",
               "m.is_thought,",
               "snippet(messages, 0, '«', '»', ' … ', 12) AS snip,",
               "bm25(messages) AS rank",
               "FROM messages m JOIN files f ON f.id = m.file_id",
               "WHERE messages MATCH ?"]
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
        return [SearchHit(path=r[0], title=r[1] or "", model=r[2] or "",
                          kind=r[3] or KIND_LOG, msg_num=int(r[4]),
                          role=r[5], is_thought=bool(int(r[6])),
                          snippet=r[7], rank=float(r[8]))
                for r in rows]

    # ---------------- сервис ----------------

    def stats(self) -> dict:
        nf = self.con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        nl = self.con.execute(
            "SELECT COUNT(*) FROM files WHERE kind='log'").fetchone()[0]
        nt = self.con.execute(
            "SELECT COUNT(*) FROM files WHERE kind='txt'").fetchone()[0]
        nm = self.con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        size = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {"files": nf, "logs": nl, "texts": nt, "messages": nm,
                "db_path": str(self.db_path), "db_size": size}

    def optimize(self):
        """Сжатие FTS-индекса и БД (после массовых обновлений)."""
        with self.con:
            self.con.execute(
                "INSERT INTO messages(messages) VALUES('optimize')")
        self.con.commit()
        # VACUUM требует автокоммита (вне транзакции)
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
