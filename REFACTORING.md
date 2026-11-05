# StudioLogHelper 2.0 — Refactored PyQt6

Полный рефактор проекта

## Что изменено

- **PySide6 → PyQt6**: лучшая совместимость с тестами, кроссплатформа Windows/Linux, коммерческая дружелюбность с GPL, pytest-qt.
- **Монолит 2400 строк app.py → модули**: `ui/main_window.py`, `ui/widgets/`, `ui/dialogs/`, `ui/themes.py`
- **Монолит core.py → `core/parsers/`, `core/exporters/`, `core/markdown.py`, `core/scanner.py`, `core/models.py`**
- **i18n глобальный → класс Translator** без глобального состояния, можно мокать.
- **Кроссплатформенные пути** через `QStandardPaths` + fallback XDG/AppData
- **Оптимизации**:
  - `orjson` опционально — 3-5x быстрее JSON
  - Regex precompile кэш
  - Single-pass encoding detection вместо 4 декодирований
  - Scanner с защитой от symlink loop, skip binary по расширению + magic bytes
  - Indexer: batch transactions (50 файлов в одной транзакции = 10x быстрее), ThreadPool для CPU-bound парсинга
  - UI: воркер QThread для загрузки, чтобы GUI не фризил; cached QSS; lazy batch rendering kept + улучшен
  - `reveal_in_file_manager()` — единая функция для Win/Linux/mac

## Запуск

```bash
pip install -r requirements.txt
python app.py
# или
python -m studiologhelper.ui.app

# CLI
python cli.py export path/to/log -f txt -o out/
python cli.py index folder/
python cli.py search "query"
```

## Структура

```
studiologhelper/
  core/
    models.py — Attachment, Message, ChatLog
    parsers/
      base.py — TextParseOptions
      detector.py — looks_like_log (оптимизир)
      json_parser.py — orjson fallback
      text_parser.py — compiled regex
      parser.py — top-level parse_file
    exporters/ — txt, md, html, json, jsonl, manager
    scanner.py — _walk_safe + scan_folder
    markdown.py — оптимиз. с кэшем + markdown lib fallback
    project.py — Project .slh.json v2
  indexer/
    index.py — SearchIndex с батчами + threads
    text_splitter.py
    query.py
  i18n/
    translator.py — без глобалей
  ui/
    themes.py — cached QSS
    widgets/message_card.py
    dialogs/
    main_window.py — MainWindow с ParseWorker QThread
    app.py
  cli/commands.py
  utils/paths.py, encoding.py
```

## Тесты

```bash
pytest tests/ -v
pytest --cov=studiologhelper
```

## Кроссплатформа checklist

- [x] Paths via QStandardPaths / XDG / AppData
- [x] reveal_in_file_manager: explorer /select, xdg-open, open -R
- [x] QFileDialog native
- [x] QSettings IniFormat on Linux
- [x] No hardcoded \ or /
- [x] All via pathlib



## Раунд оптимизации 2026-11 (рефакторинг горячих путей)

Кратко:

- **stemmer**: `@lru_cache` на `stem_word`, предкомпилированные regex, однопроходная
  токенизация — поиск `fast_search_chats` ~7x, `hybrid_search` ~4x.
- **text_parser**: наборы заголовков собираются один раз на файл, быстрые guard'ы —
  парсинг 1.6MB лога ~6x. Исправлен баг bare-заголовков (`answer`/`response`
  в теле сообщения срезали текст) + регрессионный тест.
- **SearchIndex**: один `_load_known()` вместо SELECT на файл; `kind` не перечитывается.
- **memory_search/hybrid_search**: один `lower`/`search` на кандидата, кэш dict-векторов.
- **reader_view**: кэш body-HTML блоков (не зависит от темы/шрифта), debounce 120ms,
  O(n+m) карты закладок/цитат; **virtual_view**: кэш `time_str()`.
- Бенчмарк: `bench/bench.py`; новые тесты: `tests/test_refactor_regressions.py` (65 passed).

## Раунд 2026-11 (ч.2): CI, виртуализация «Книги», режимы UI

- **GitHub Actions CI** (`.github/workflows/ci.yml`): pytest-матрица Linux
  (Python 3.10–3.13) + Windows + macOS, headless Qt (`QT_QPA_PLATFORM=offscreen`,
  `tests/conftest.py` с session QApplication), lint ruff.
- **Бенчмарк-гейты**: `bench/bench.py`, `bench/check_gates.py`, `bench/golden.json` —
  сборка падает при регрессии производительности; результаты — артефактом.
- **Виртуализация «Книги»**: оконный рендер блоков вокруг позиции чтения
  (`_window_bounds`), догрузка по скроллу и ссылкам «↑/↓ показать ещё»,
  переходы `jump_to_block` переносят окно; настройки `reader/window_init` (40),
  `reader/window_grow` (30). 1000+ сообщений — без фризов.
- **Режимы интерфейса**: «Простой» (по умолчанию — только Книга + Поиск) и
  «Расширенный» (все инструменты). Переключатель «Режим:» в правом верхнем углу,
  состояние в `ui/mode`. В простом режиме Reader также скрывает типографику.
- **Тесты**: 77 passed (добавлены `test_reader_virtualization.py`,
  `test_ui_modes.py`); ruff нашёл и мы починили реальный баг: `_html`
  не импортирован в `main_window._show_plugins` (краш при открытии Plugins).
- **pyproject**: `requires-python = ">=3.10"` (код использует `dataclass(slots=True)`).
