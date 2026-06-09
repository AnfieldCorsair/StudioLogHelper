# -*- coding: utf-8 -*-
"""
cli.py — консольная версия парсера логов Google AI Studio.
Удобно для массовой обработки без GUI.

Примеры:
  python cli.py chat_log                         # инфо о файле
  python cli.py chat_log -f txt -o out/          # экспорт в TXT
  python cli.py logs_folder -f html --thoughts separate -o out/
  python cli.py chat_log -f md --no-numbering --timestamps -o out/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import core


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Парсер логов чатов Google AI Studio (JSON, в т.ч. без расширения).")
    p.add_argument("input", nargs="+",
                   help="Файл(ы) лога или папка(и) с логами")
    p.add_argument("-o", "--out", default=None,
                   help="Папка для экспорта (если не указана — только информация)")
    p.add_argument("-f", "--format", choices=["txt", "html", "md"],
                   default="txt", help="Формат экспорта (по умолчанию txt)")
    p.add_argument("--thoughts", choices=["exclude", "include", "separate"],
                   default="exclude", help="Размышления модели")
    p.add_argument("--no-numbering", action="store_true",
                   help="Отключить нумерацию сообщений")
    p.add_argument("--timestamps", action="store_true",
                   help="Добавить метки времени")
    p.add_argument("--no-metadata", action="store_true",
                   help="Без шапки (модель/параметры)")
    p.add_argument("--no-attachments", action="store_true",
                   help="Не выводить вложения")
    p.add_argument("--no-markdown", action="store_true",
                   help="HTML: не рендерить Markdown")
    p.add_argument("--no-recursive", action="store_true",
                   help="Не заходить в подпапки")
    return p


def collect_files(inputs, recursive: bool) -> list:
    files = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            found = core.scan_folder(p, recursive=recursive)
            if not found:
                print(f"[!] В папке нет файлов, похожих на логи: {p}")
            files.extend(found)
        elif p.is_file():
            files.append(str(p))
        else:
            print(f"[!] Не найдено: {p}")
    # без дублей, с сохранением порядка
    seen, out = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    files = collect_files(args.input, recursive=not args.no_recursive)
    if not files:
        print("Нет файлов для обработки.")
        return 1

    opts = core.ExportOptions(
        fmt=args.format,
        numbering=not args.no_numbering,
        thoughts=args.thoughts,
        timestamps=args.timestamps,
        metadata=not args.no_metadata,
        attachments=not args.no_attachments,
        render_markdown=not args.no_markdown,
    )

    ok, fail = 0, 0
    for f in files:
        try:
            chat = core.parse_file(f)
        except (core.ParseError, OSError, ValueError) as ex:
            print(f"[ошибка] {f}: {ex}")
            fail += 1
            continue

        print(f"[ok] {chat.title} — модель {chat.model or '—'}, "
              f"{len(chat.messages)} сообщ. "
              f"(промтов {chat.user_count} / ответов {chat.model_count}, "
              f"размышлений {chat.thought_count})")
        for w in chat.warnings:
            print(f"     ⚠ {w}")

        if args.out:
            try:
                created = core.export_to_files(chat, opts, args.out)
                for c in created:
                    print(f"     -> {c}")
            except OSError as ex:
                print(f"     [ошибка записи] {ex}")
                fail += 1
                continue
        ok += 1

    print(f"\nГотово: {ok} успешно, {fail} с ошибками.")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
