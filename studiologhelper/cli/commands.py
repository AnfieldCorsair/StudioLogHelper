# -*- coding: utf-8 -*-
import argparse
import sys
from pathlib import Path

from ..core.exporters.base import ExportOptions
from ..core.parsers.parser import parse_file
from ..core.scanner import scan_folder
from ..core.exceptions import ParseError
from ..i18n.translator import Translator, LANGS, DEFAULT_LANG
from ..indexer import SearchIndex


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="StudioLogHelper — parser for AI Studio logs")
    sub = p.add_subparsers(dest="cmd")

    pe = sub.add_parser("export", help="Parse/export")
    _add_export_args(pe)

    pi = sub.add_parser("index", help="Build/update search index")
    pi.add_argument("paths", nargs="+", help="Folders/files to index")
    pi.add_argument("--db", default=None)
    pi.add_argument("--no-recursive", action="store_true")
    pi.add_argument("--clear", action="store_true")
    pi.add_argument("--no-txt", action="store_true")
    pi.add_argument("--no-logs", action="store_true")
    pi.add_argument("--optimize", action="store_true")

    ps = sub.add_parser("search", help="Search index")
    ps.add_argument("query")
    ps.add_argument("--db", default=None)
    ps.add_argument("--in", dest="scope", default="all", choices=["all", "prompts", "answers", "thoughts", "txt"])
    ps.add_argument("--model", default=None)
    ps.add_argument("--path", default=None)
    ps.add_argument("--limit", type=int, default=30)

    pst = sub.add_parser("stats", help="Index stats")
    pst.add_argument("--db", default=None)
    return p


def _add_export_args(p):
    p.add_argument("input", nargs="+")
    p.add_argument("-o", "--out", default=None)
    p.add_argument("-f", "--format", choices=["txt", "html", "md", "json", "jsonl"], default="txt")
    p.add_argument("--content", choices=["all", "prompts", "answers", "thoughts"], default="all")
    p.add_argument("--thoughts", choices=["exclude", "include", "separate"], default="exclude")
    p.add_argument("--no-numbering", action="store_true")
    p.add_argument("--timestamps", action="store_true")
    p.add_argument("--no-metadata", action="store_true")
    p.add_argument("--no-attachments", action="store_true")
    p.add_argument("--no-markdown", action="store_true")
    p.add_argument("--no-recursive", action="store_true")
    p.add_argument("--user-label", default=None)
    p.add_argument("--model-label", default=None)
    p.add_argument("--lang", choices=sorted(LANGS), default=DEFAULT_LANG)


def collect_files(inputs, recursive: bool) -> list:
    files = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            found = scan_folder(p, recursive=recursive)
            if not found:
                print(f"[!] No logs in: {p}")
            files.extend(found)
        elif p.is_file():
            files.append(str(p))
        else:
            print(f"[!] Not found: {p}")
    seen, out = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def cmd_export(args) -> int:
    tr = Translator(lang=args.lang)
    files = collect_files(args.input, recursive=not args.no_recursive)
    if not files:
        print("No files.")
        return 1

    opts = ExportOptions(
        fmt=getattr(args, "format"),
        content=args.content,
        numbering=not args.no_numbering,
        thoughts=args.thoughts,
        timestamps=args.timestamps,
        metadata=not args.no_metadata,
        attachments=not args.no_attachments,
        render_markdown=not args.no_markdown,
        user_label=args.user_label or tr.tr("user"),
        model_label=args.model_label or tr.tr("model"),
        auto_model_label=args.model_label is None,
    )

    ok, fail = 0, 0
    for f in files:
        try:
            chat = parse_file(f)
        except (ParseError, OSError, ValueError) as ex:
            print(f"[err] {f}: {ex}")
            fail += 1
            continue
        print(f"[ok] {chat.title} — model {chat.model or '—'}, {len(chat.messages)} msgs (prompts {chat.user_count} / answers {chat.model_count}, thoughts {chat.thought_count})")
        for w in chat.warnings:
            print(f"     ⚠ {w}")
        if args.out:
            try:
                from ..core.exporters.manager import export_to_files
                created = export_to_files(chat, opts, args.out)
                for c in created:
                    print(f"     -> {c}")
            except OSError as ex:
                print(f"     [write err] {ex}")
                fail += 1
                continue
        ok += 1
    print(f"\nDone: {ok} ok, {fail} errors.")
    return 0 if fail == 0 else 2


def cmd_index(args) -> int:
    with SearchIndex(args.db) as idx:
        if args.clear:
            idx.clear()
            print("Index cleared.")

        def cb(done, total, path):
            if total and (done % 25 == 0 or done == total):
                print(f"  {done}/{total}…", end="\r")

        stats = idx.index_paths(args.paths, recursive=not args.no_recursive, include_logs=not args.no_logs, include_txt=not args.no_txt, progress=cb)
        print(f"\nIndexing: {stats.summary()}")
        for e in stats.errors[:10]:
            print(f"  ⚠ {e}")
        if args.optimize:
            idx.optimize()
            print("Index optimized.")
        st = idx.stats()
        print(f"Index: {st['files']} files (logs {st['logs']}, texts {st['texts']}), {st['messages']} records, DB {st['db_size']/1e6:.1f} MB ({st['db_path']})")
    return 0


def cmd_search(args) -> int:
    role, thoughts, kind = None, None, None
    if args.scope == "prompts":
        role, thoughts = "user", False
    elif args.scope == "answers":
        role, thoughts = "model", False
    elif args.scope == "thoughts":
        thoughts = True
    elif args.scope == "txt":
        kind = "txt"

    with SearchIndex(args.db) as idx:
        hits = idx.search(args.query, role=role, thoughts=thoughts, model=args.model, path_like=args.path, kind=kind, limit=args.limit)
        if not hits:
            print("Nothing found.")
            return 1
        for h in hits:
            if h.kind == "txt":
                icon = "📄"
                what = f"block #{h.msg_num}"
            else:
                icon = "💭" if h.is_thought else ("👤" if h.role == "user" else "🤖")
                what = f"msg #{h.msg_num}"
            print(f"{icon} {h.title} · {h.model or '—'} · {what}")
            print(f"   {h.snippet}")
            print(f"   {h.path}\n")
        print(f"Found: {len(hits)}")
    return 0


def cmd_stats(args) -> int:
    with SearchIndex(args.db) as idx:
        st = idx.stats()
        print(f"Files: {st['files']} (logs {st['logs']}, texts {st['texts']})\nRecords: {st['messages']}\nDB: {st['db_path']} ({st['db_size']/1e6:.1f} MB)")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("export", "index", "search", "stats", "-h", "--help"):
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
