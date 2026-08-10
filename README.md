# StudioLogHelper 2.0

Desktop (PyQt6) + CLI helper for AI chat logs: Google AI Studio JSON (including extensionless files from Google Drive), Claude, ChatGPT, Arena AI text exports, cleaned TXT/MD logs, Book Reading Mode, Highlighter quotes, Hybrid Search (FTS5 + Stemming + Local Embeddings), and Projects.

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

### CLI:

```bash
python cli.py export path/to/log -f txt -o out/
python cli.py index path/to/archive
python cli.py search "query"
```

## Key Features

1. **Modular 2.0 Architecture**: Decoupled Controllers (`FileListController`, `ProjectController`), Workers (`ParseWorker`, `ExportWorker`), Services (`CopyService`, `ExportService`), and Renderers.
2. **Book Reading Mode (Режим «Книга»)**: Clean book-like reader with Warm Paper (`#fdf6e3`), Sepia (`#f4ecd8`), and Soft OLED palettes, Serif typography, TOC, and fast anchor navigation.
3. **Interactive Quotes & Highlighter**: Highlight text fragments with colored markers (🟡 Yellow, 🟢 Green, 🌸 Pink, 🔵 Blue), attach notes, and export Markdown digests.
4. **Hybrid Search Engine**: Combines SQLite FTS5 (BM25) + Russian & English morphological stemming + subword dense n-gram embeddings for typo-tolerant and semantic search.
5. **Hierarchical Categories & Auto-save**: Nested folders (`Work/Research/Gemini`), subtree filtering, and automated non-blocking project saving.
6. **Hardware Virtualization**: Smooth 60 FPS scrolling for 10k+ message dialogs.
