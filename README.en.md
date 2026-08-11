# StudioLogHelper - Pre-Release 1.1 (PyQt6)

Desktop application and CLI utility for parsing, reading, searching, and exporting AI chat logs from **Google AI Studio** (including extensionless JSON files downloaded from Google Drive), **Arena AI plain-text exports**, and cleaned TXT/MD logs.

---

## Key Features

### 📖 Book Reading Mode & Typography
- **Comfortable Reading:** Formats conversations into a structured book with clean chapter headers and customizable column widths (`740px`, `920px`, `100%`).
- **Reading Palettes:**
  - 📜 **Warm Paper (Solarized Warm):** background `#fdf6e3`, soft text `#43525a`, accent `#b58900`.
  - 🕰 **Vintage Sepia:** background `#f4ecd8`, warm text `#3c2f1f`.
  - 🌙 **Night Reading (Soft OLED):** gentle dark `#191a21`, text `#d0d3dc`.
  - ☀️ **Light** & 🌑 **Dark** modes.
- **Typography Controls:** Serif (`Georgia`, `Noto Serif`, `Merriweather`), Sans-serif, Monospace fonts; line height presets (`1.4x`, `1.7x`, `2.0x`); instant zoom `A−` / `A+`.
- **Navigation:** Block jumping with `Ctrl+Up` / `Ctrl+Down`, Table of Contents (TOC) with role badges and snippet previews.

### 🖍 Interactive Quotes & Highlighter
- Select text with the cursor and highlight with colored markers: 🟡 **Yellow**, 🟢 **Green**, 🌸 **Pink**, 🔵 **Blue**.
- Accurate `(start, end)` boundary preservation and source text hash validation.
- Attach custom user notes to quotes and bookmarks (`Ctrl+B`).
- Saved in `.slh.json` project metadata with one-click Markdown summary export.

### 🔎 Fuzzy & Hybrid Search Engine (FTS5 + Stemming + Character N-grams)
- **Lexical Index:** Fast SQLite FTS5 (BM25) over indexed folders.
- **Morphological Stemmer (RU/EN):** Porter stemmer matches inflected word forms (searching for `cooking` finds `cook`, `cooked`, `cooks`; Russian `сковородка` finds `сковорода`, `сковороду`, `сковороде`).
- **Local N-gram Vectorizer:** LRU-cached cosine similarity provides typo-tolerant ranking without heavy external AI dependencies.
- **Asynchronous Non-blocking Worker:** Background query execution with real-time cancellation of obsolete searches and input debouncing.

### 🗃 Hierarchical Categories & Non-blocking Auto-save
- **Nested Categories:** Support for subcategories such as `Work/Research/Gemini`, `Work/Code`, `Personal/Notes` with subtree filtering.
- **Atomic Background Auto-save (`SaveProjectWorker`):** Truly non-blocking debounced saving in a separate thread via temporary files and `fsync` with automatic `.bak` backups.
- **Project Portability:** Relative path resolution (`rel_path`) allows copying project directories across computers without losing linked files.
- **Undo / Redo:** Multi-level command stack (`Ctrl+Z` / `Ctrl+Y`).

### 🛡 Security & Plugins
- **HTML Sanitization:** Built-in XSS protection, entity decoding, and stripping of dangerous tags and `javascript:` protocols.
- **Safe External Links:** Automatic injection of `rel="noopener noreferrer"`.
- **Plugin Safe Mode:** Safe mode flag `--safe-mode` / `--disable-plugins` in GUI and CLI to prevent loading arbitrary third-party code.

---

## Installation & Running

```bash
pip install -r requirements.txt
python app.py
# or
python -m studiologhelper.ui.app
```

Install as a package:

```bash
pip install .
studiologhelper
# or CLI
slh --help
```

### CLI Usage:

```bash
python cli.py export path/to/log -f txt -o out/
python cli.py index path/to/folder
python cli.py search "query"
```

## Hotkeys

- `Ctrl+O` — Open files
- `Ctrl+Shift+O` — Open folder
- `Ctrl+E` — Export current chat
- `Ctrl+Shift+E` — Export all chats
- `Ctrl+B` — Toggle bookmark / Highlight quote
- `Ctrl+F` — Find in text
- `Ctrl+K` — Quick search across open chats
- `Ctrl+1..5` — Switch tabs (Cards, Virtual, Reader, Source, Search)
- `Ctrl+Up` / `Ctrl+Down` — Jump to previous / next block
- `Ctrl+=` / `Ctrl+-` / `Ctrl+0` — Zoom
- `Ctrl+Z` / `Ctrl+Y` — Undo / Redo
