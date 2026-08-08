# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from .base import EXT, CONTENT_SUFFIX, ExportOptions
from .txt import TxtExporter
from .md import MdExporter
from .html import HtmlExporter
from .json_exporter import JsonExporter, JsonlExporter

EXPORTERS = {
    "txt": TxtExporter,
    "md": MdExporter,
    "html": HtmlExporter,
    "json": JsonExporter,
    "jsonl": JsonlExporter,
}


def export_chat(chat, opts: ExportOptions):
    exporter_cls = EXPORTERS.get(opts.fmt)
    if exporter_cls is None:
        raise ValueError(f"Unknown format: {opts.fmt}")
    exporter = exporter_cls()
    return exporter.export(chat, opts)


def export_to_files(chat, opts: ExportOptions, out_dir, base_name=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_name or (Path(chat.path).stem if chat.path else chat.title) or "chat"
    base += CONTENT_SUFFIX.get(opts.content, "")
    main, sep = export_chat(chat, opts)
    ext = EXT[opts.fmt]
    created = []
    main_path = out_dir / f"{base}{ext}"
    main_path.write_text(main, encoding="utf-8")
    created.append(str(main_path))
    if sep:
        sep_path = out_dir / f"{base}_thoughts{ext}"
        sep_path.write_text(sep, encoding="utf-8")
        created.append(str(sep_path))
    return created
