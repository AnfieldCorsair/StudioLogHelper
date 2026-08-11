# StudioLogHelper - Pre-Release 1.1

Desktop (PyQt6) + CLI helper for AI chat logs: **Google AI Studio JSON logs** (including files without extension downloaded from Google Drive), **Arena AI plain-text exports**, cleaned TXT/MD logs, Book Reading Mode, Highlighter quotes, Fuzzy Search (FTS5 + Stemming + Character N-grams), and Projects.

## Documentation

- [Русская версия](README.ru.md)
- [English version](README.en.md)
- [Project config `.slh.json` — RU](docs/CONFIG.ru.md)
- [Project config `.slh.json` — EN](docs/CONFIG.en.md)

## Quick Start

```bash
pip install -r requirements.txt
python app.py
# or
python -m studiologhelper.ui.app
```

### Installation as a package:

```bash
pip install .
studiologhelper
# or CLI
slh --help
```

### CLI Commands:

```bash
python cli.py export path/to/log -f txt -o out/
python cli.py index path/to/archive
python cli.py search "query"
```

## Key Features

1. **Modular Architecture**: Decoupled Controllers (`FileListController`, `ProjectController`), Background Workers (`ParseWorker`, `ExportWorker`, `SearchWorker`, `SaveProjectWorker`), Services (`CopyService`, `ExportService`), and Renderers.
2. **Book Reading Mode (Режим «Книга»)**: Accelerated book reader with Warm Paper (`#fdf6e3`), Sepia (`#f4ecd8`), and Soft OLED palettes, Serif typography, Table of Contents, and anchor navigation.
3. **Interactive Quotes & Highlighter**: Highlight text fragments with colored markers (🟡 Yellow, 🟢 Green, 🌸 Pink, 🔵 Blue), attach notes, and export Markdown digests.
4. **Fuzzy Search Engine**: Combines SQLite FTS5 (BM25) + Russian & English morphological stemming + character n-gram vectorizer for typo-tolerant search and live debounced queries.
5. **Hierarchical Categories & Auto-save**: Nested folders (`Work/Research/Gemini`), subtree filtering, and background non-blocking project auto-saving with `.bak` backups.
6. **Data Safety**: Atomic writing via temporary files + `fsync` + automatic `.bak` backups.
7. **Experimental Plugins**: Extensible plugin system with Safe Mode (`--safe-mode`).
