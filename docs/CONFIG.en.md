# StudioLogHelper project config (`.slh.json`)

A project file stores not only opened logs, but also the meaning of your workflow: categories, tags, notes and links between source files and exported files.

Default extension: `.slh.json`.

## Example

```jsonc
{
  "app": "AI Studio Log Parser",
  "schema": "studiologhelper.project.v1",
  "created_or_saved_at": "2026-06-16T12:00:00",
  "project": {
    "name": "Novel X — log processing",
    "path": "D:/work/novel-x/project.slh.json"
  },
  "categories": [
    "Raw Google Drive JSON",
    "Model answers for Novel X",
    "Clean TXT with prompts and answers"
  ],
  "files": [
    {
      "path": "D:/logs/raw/01",
      "title": "01",
      "source_format": "json",
      "model": "gemini-2.5-pro",
      "messages": 42,
      "prompts": 21,
      "answers": 21,
      "category": "Raw Google Drive JSON",
      "tags": ["novel-x", "raw", "google-drive"],
      "note": "File without extension, downloaded directly from Google Drive"
    },
    {
      "path": "D:/logs/answers/01_answers.txt",
      "source_format": "text",
      "category": "Model answers for Novel X",
      "tags": ["novel-x", "answers"],
      "derived_from": "D:/logs/raw/01",
      "note": "Model answers only"
    }
  ],
  "parser": {
    "numbered_mode": "model",
    "user_headers": [],
    "model_headers": ["Right Gemini", "Bot"]
  },
  "ui": {
    "show_extensions": true,
    "theme": "dark"
  }
}
```

## Typical workflow

1. Create a project: **Project & categories → New project**.
2. Open raw Google Drive files without extension.
3. Create category: `Raw Google Drive JSON`.
4. Assign the category and notes to these files.
5. Batch-export model answers to a separate folder.
6. Open generated TXT files.
7. Create category: `Model answers for Novel X`.
8. Assign tags and notes to the generated TXT files.
9. Save the workspace as `.slh.json`.

## Planned fields

Future versions may expand the config with:

- `export_profile` — which profile created a derived file;
- `batch_id` — batch operation identifier;
- richer `derived_from` chains;
- per-file diagnostics and encoding metadata.
