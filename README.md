# StudioLogHelper

Desktop + CLI helper for AI chat logs: Google AI Studio JSON, files without extension from Google Drive, Arena AI text exports, cleaned TXT/MD logs, batch export, search, projects, categories and tags.

## Documentation

- [Русская версия](README.ru.md)
- [English version](README.en.md)
- [Project config `.slh.json` — RU](docs/CONFIG.ru.md)
- [Project config `.slh.json` — EN](docs/CONFIG.en.md)

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

CLI:

```bash
python cli.py export path/to/log -f txt -o out/
python cli.py index path/to/archive
python cli.py search "query"
```
