# -*- coding: utf-8 -*-
"""Scanner с оптимизациями: генераторы, защита от симлинков, лимиты."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator, Iterable

from .parsers.detector import looks_like_log, BINARY_EXTS

# Не индексируем скрытые и системные папки
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", ".mypy_cache"}


def _walk_safe(root: Path, recursive: bool) -> Generator[Path, None, None]:
    """Безопасный обход с защитой от symlink loops."""
    if not recursive:
        try:
            for entry in root.iterdir():
                if entry.is_file():
                    yield entry
        except OSError:
            return
        return

    # Use os.walk с контролем
    seen_inodes = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # filter skip dirs in-place
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            # skip hidden
            if fname.startswith("."):
                # но allow .slh.json? No, those are project files, not logs
                if not fname.endswith(".slh.json"):
                    continue
            try:
                stat = fpath.stat()
                # защита от symlink loop через inode
                inode = (stat.st_dev, stat.st_ino)
                if inode in seen_inodes:
                    continue
                seen_inodes.add(inode)
                # быстрый фильтр по расширению до looks_like_log
                if fpath.suffix.lower() in BINARY_EXTS:
                    continue
                # слишком большие (>200MB) пропускаем как не лог? Но проверяем
                if stat.st_size > 200 * 1024 * 1024:
                    continue
            except OSError:
                continue
            yield fpath


def scan_folder(folder, recursive: bool = True) -> list[str]:
    p = Path(folder)
    if not p.is_dir():
        return []
    result = []
    for f in _walk_safe(p, recursive):
        if looks_like_log(f):
            result.append(str(f))
    result.sort()
    return result


def iter_log_files(folders: Iterable[Path | str], recursive: bool = True) -> Generator[str, None, None]:
    """Генератор для стриминга — не держит весь список в памяти."""
    seen = set()
    for folder in folders:
        p = Path(folder)
        if p.is_file():
            sp = str(p)
            if sp not in seen:
                seen.add(sp)
                yield sp
            continue
        if not p.is_dir():
            continue
        for f in _walk_safe(p, recursive):
            sf = str(f)
            if sf in seen:
                continue
            if looks_like_log(f):
                seen.add(sf)
                yield sf
