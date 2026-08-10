# StudioLogHelper 2.0 (PyQt6)

Desktop app and CLI utility for parsing, viewing, deep reading, searching, and exporting AI chat logs from **Google AI Studio** (including extensionless JSON files from Google Drive), **Arena AI**, and cleaned TXT/MD logs.

---

## What's New in Version 2.0

### 📖 Book Reading Mode & Typography
- **Distraction-Free Reading:** Formats conversations into a structured book with clean chapter headers and customizable column widths (`740px`, `920px`, `100%`).
- **Reading Palettes:**
  - 📜 **Warm Paper (Solarized Warm):** background `#fdf6e3`, soft text `#43525a`, accent `#b58900`.
  - 🕰 **Vintage Sepia:** background `#f4ecd8`, warm text `#3c2f1f`.
  - 🌙 **Night Reading (Soft OLED):** gentle night dark `#191a21`, text `#d0d3dc`.
  - ☀️ **Light** & 🌑 **Dark** modes.
- **Typography Controls:** Serif (`Georgia`, `Noto Serif`, `Merriweather`), Sans-serif, Monospace fonts; line height presets (`1.4x`, `1.7x`, `2.0x`); instant zoom `A−` / `A+`.
- **Navigation:** Block jumping with `Ctrl+Up` / `Ctrl+Down`, Table of Contents (TOC) with role badges and snippet previews.

### 🖍 Interactive Quotes & Highlighter
- Select any text with your mouse and highlight with colored markers: 🟡 **Yellow**, 🟢 **Green**, 🌸 **Pink**, 🔵 **Blue**.
- Attach custom user notes to quotes and bookmarks (`Ctrl+B`).
- Saved in `.slh.json` project metadata with one-click Markdown summary export.

### 🔎 Hybrid Search Engine (FTS5 + Stemming + Local Embeddings)
- **Lexical Index:** Fast SQLite FTS5 (BM25) over indexed folders.
- **Morphological Stemmer (RU/EN):** Porter stemmer matches inflected word forms (searching for `cooking` finds `cook`, `cooked`, `cooks`; Russian `сковородка` finds `сковорода`, `сковороду`, `сковороде`).
- **Subword Dense Embeddings:** Local n-gram cosine similarity provides semantic and fuzzy ranking without large AI dependencies.
- Exact phrase search in quotes (`"exact phrase"`) and wildcard prefix queries (`term*`).

### 🗃 Hierarchical Categories & Auto-save
- **Nested Categories:** Support for subcategories such as `Work/Research/Gemini`, `Work/Code`, `Personal/Notes` with subtree filtering.
- **Project Auto-save:** Real-time, non-blocking auto-save for tags, notes, categories, and highlights into `.slh.json`.
- **Undo / Redo:** Multi-level command stack (`Ctrl+Z` / `Ctrl+Y`).

### ⚡ Performance & Hardware Virtualization
- **0% Idle CPU & 60 FPS Scrolling:** Unified C++ accelerated canvas and `QListView` virtualization for 10,000+ message logs.
- **Lazy Tab Rendering:** Zero lag when toggling filters or checkboxes; only the visible tab is rendered.
- **Network Leak Protection:** Markdown images are sanitized to safe badges, preventing synchronous network stalls.

---

## Installation & Running

```bash
pip install -r requirements.txt
python app.py
# or
python -m studiologhelper.ui.app
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
