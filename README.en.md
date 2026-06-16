# StudioLogHelper

StudioLogHelper is a desktop app and CLI utility for parsing, viewing, organizing, searching and exporting AI chat logs.

Supported sources:

- Google AI Studio JSON logs, including files downloaded from Google Drive without an extension;
- Arena AI plain-text exports (`User:`, `Right AI:`, `Right model`, `ModelName`, `#1:` blocks);
- cleaned TXT/MD exports created by this app;
- regular TXT/MD files for indexing/search.

## Features

### Viewing

- Open files, multiple files, folders recursively, drag & drop.
- Clean card view, raw JSON/text view, search tab.
- Dark/light theme, Russian/English UI.
- UI zoom with `A− / A+`, `Ctrl+=`, `Ctrl+-`, `Ctrl+0`.
- Lazy message rendering for long logs.

### Copying

- Copy whole chat, prompts only, answers only, thoughts only.
- Copy individual messages.
- Copy raw JSON or source text.
- Copy settings: include/exclude service headers, blank lines, long line or custom separator between messages.

### Export

Formats:

- TXT;
- HTML;
- Markdown;
- JSON;
- JSONL.

Export options:

- whole chat / prompts only / answers only / thoughts only;
- numbering;
- timestamps;
- metadata;
- system instruction;
- attachments;
- thoughts excluded / inline / separate file;
- optional export profiles;
- batch export: selected/all opened files to a folder, assign category/tags/note to generated files and index the output folder.

### Projects, categories and tags

The app can save a working set as `.slh.json`:

- opened file list;
- categories/groups;
- custom tags;
- notes;
- custom tags;
- derived/exported file links;
- parser settings.

This is useful for workflows like:

1. Open several raw Google Drive files without extension.
2. Mark them as `Raw Google Drive JSON`.
3. Export model answers to TXT into a separate folder.
4. Open generated TXT files.
5. Mark them as `Model answers for work X`.
6. Save the whole workspace as a project.

### Search

Search modes:

- selected file;
- all opened files;
- indexed folder: all files;
- indexed folder: TXT/MD only;
- indexed folder: JSON/dialog logs.

The global index uses SQLite FTS5.

## Installation

```bash
pip install -r requirements.txt
python app.py
```

## CLI examples

```bash
python cli.py path/to/log
python cli.py export path/to/log -f txt -o out/
python cli.py export logs/ -f md --content answers -o out/
python cli.py index D:/GoogleDrive
python cli.py search "exact phrase"
python cli.py search "cow aerodynamics" --in answers
```

## Project structure

| File | Purpose |
|---|---|
| `core.py` | Parser and exporters, no GUI dependency |
| `app.py` | PySide6 desktop GUI |
| `cli.py` | Command line interface |
| `indexer.py` | SQLite FTS5 search index |
| `i18n.py` | RU/EN localization |
| `assets/icons/` | Custom UI icons with safe fallback |
| `docs/` | Config, release audit and license notes |
| `tests/` | Core/parser regression tests |
| `docs/CONFIG.md` | Project config documentation in Russian |
| `docs/CONFIG.en.md` | Project config documentation in English |

## Tests

```bash
python -m pytest -q tests
python -m py_compile app.py core.py cli.py i18n.py indexer.py
```
