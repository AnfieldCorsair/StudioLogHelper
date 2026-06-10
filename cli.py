# -*- coding: utf-8 -*-
"""
cli.py — консольная версия парсера логов Google AI Studio.
Удобно для массовой обработки и поиска без GUI.

Примеры:
  python cli.py chat_log                              # инфо о файле
  python cli.py chat_log -f txt -o out/               # экспорт в TXT
  python cli.py logs/ -f html --thoughts separate -o out/
  python cli.py chat_log -f md --content answers -o out/   # только ответы

  python cli.py index D:/GoogleDrive                  # построить/обновить индекс
  python cli.py search "сковородка" --in thoughts     # поиск по индексу
  python cli.py search "frying pan" --model gemini-2.5 --limit 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import core


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Парсер логов чатов Google AI Studio "
                    "(JSON, в т.ч. без расширения).")
    sub = p.add_subparsers(dest="cmd")

    # --- export (по умолчанию) ---
    pe = sub.add_parser("export", help="Парсинг/экспорт (команда по умолчанию)")
    _add_export_args(pe)

    # --- index ---
    pi = sub.add_parser("index", help="Построить/обновить поисковый индекс")
    pi.add_argument("paths", nargs="+", help="Папки/файлы для индексации")
    pi.add_argument("--db", default=None, help="Путь к файлу индекса (.db)")
    pi.add_argument("--no-recursive", action="store_true")
    pi.add_argument("--clear", action="store_true",
                    help="Очистить индекс перед индексацией")

    # --- search ---
    ps = sub.add_parser("search", help="Поиск по индексу")
    ps.add_argument("query", help="Поисковый запрос")
    ps.add_argument("--db", default=None, help="Путь к файлу индекса (.db)")
    ps.add_argument("--in", dest="scope", default="all",
                    choices=["all", "prompts", "answers", "thoughts"],
                    help="Где искать")
    ps.add_argument("--model", default=None, help="Фильтр по имени модели")
    ps.add_argument("--path", default=None, help="Фильтр по подстроке пути")
    ps.add_argument("--limit", type=int, default=30)

    # --- stats ---
    pst = sub.add_parser("stats", help="Статистика индекса")
    pst.add_argument("--db", default=None)
    return p


def _add_export_args(p):
    p.add_argument("input", nargs="+",
                   help="Файл(ы) лога или папка(и) с логами")
    p.add_argument("-o", "--out", default=None,
                   help="Папка для экспорта (если не указана — только инфо)")
    p.add_argument("-f", "--format", choices=["txt", "html", "md"],
                   default="txt", help="Формат экспорта (по умолчанию txt)")
    p.add_argument("--content", choices=["all", "prompts", "answers", "thoughts"],
                   default="all", help="Что экспортировать (по умолчанию всё)")
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
    p.add_argument("--user-label", default=core.USER_LABEL,
                   help="Подпись пользователя")
    p.add_argument("--model-label", default=None,
                   help="Подпись модели (по умолчанию — имя модели из лога)")


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
    seen, out = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def cmd_export(args) -> int:
    files = collect_files(args.input, recursive=not args.no_recursive)
    if not files:
        print("Нет файлов для обработки.")
        return 1

    opts = core.ExportOptions(
        fmt=args.format,
        content=args.content,
        numbering=not args.no_numbering,
        thoughts=args.thoughts,
        timestamps=args.timestamps,
        metadata=not args.no_metadata,
        attachments=not args.no_attachments,
        render_markdown=not args.no_markdown,
        user_label=args.user_label,
        model_label=args.model_label or core.MODEL_LABEL,
        auto_model_label=args.model_label is None,
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


def cmd_index(args) -> int:
    from indexer import SearchIndex
    with SearchIndex(args.db) as idx:
        if args.clear:
            idx.clear()
            print("Индекс очищен.")

        def cb(done, total, path):
            if total and (done % 25 == 0 or done == total):
                print(f"  {done}/{total}…", end="\r")

        stats = idx.index_paths(args.paths,
                                recursive=not args.no_recursive,
                                progress=cb)
        print(f"\nИндексация: {stats.summary()}")
        for e in stats.errors[:10]:
            print(f"  ⚠ {e}")
        st = idx.stats()
        print(f"Итого в индексе: {st['files']} файлов, "
              f"{st['messages']} сообщений, БД {st['db_size']/1e6:.1f} МБ "
              f"({st['db_path']})")
    return 0


def cmd_search(args) -> int:
    from indexer import SearchIndex
    role, thoughts = None, None
    if args.scope == "prompts":
        role, thoughts = "user", False
    elif args.scope == "answers":
        role, thoughts = "model", False
    elif args.scope == "thoughts":
        thoughts = True

    with SearchIndex(args.db) as idx:
        hits = idx.search(args.query, role=role, thoughts=thoughts,
                          model=args.model, path_like=args.path,
                          limit=args.limit)
        if not hits:
            print("Ничего не найдено.")
            return 1
        for h in hits:
            kind = "💭" if h.is_thought else ("👤" if h.role == "user" else "🤖")
            print(f"{kind} {h.title} · {h.model or '—'} · сообщение #{h.msg_num}")
            print(f"   {h.snippet}")
            print(f"   {h.path}\n")
        print(f"Найдено: {len(hits)}")
    return 0


def cmd_stats(args) -> int:
    from indexer import SearchIndex
    with SearchIndex(args.db) as idx:
        st = idx.stats()
        print(f"Файлов: {st['files']}\nСообщений: {st['messages']}\n"
              f"БД: {st['db_path']} ({st['db_size']/1e6:.1f} МБ)")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # обратная совместимость: `python cli.py файл …` == `export файл …`
    if argv and argv[0] not in ("export", "index", "search", "stats",
                                "-h", "--help"):
        argv.insert(0, "export")
    args = build_parser().parse_args(argv)
    if args.cmd == "export":
        return cmd_export(args)
    if args.cmd == "index":
        return cmd_index(args)
    if args.cmd == "search":
        return cmd_search(args)
    if args.cmd == "stats":
        return cmd_stats(args)
    build_parser().print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
