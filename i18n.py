# -*- coding: utf-8 -*-
"""
i18n.py — локализация интерфейса (RU / EN).

Использование:
    import i18n
    i18n.set_lang("en")
    i18n.tr("open_files")  -> "Open file(s)"
"""

LANGS = {"ru": "Русский", "en": "English"}

_STRINGS = {
    "ru": {
        # верхняя панель
        "open_files": "📄 Открыть файл(ы)",
        "open_folder": "📁 Открыть папку",
        "copy_menu": "📋 Копировать ▾",
        "copy_all": "Весь чат",
        "copy_prompts": "Только промты",
        "copy_answers": "Только ответы",
        "copy_thoughts": "Только размышления",
        "export_current": "💾 Экспорт текущего…",
        "export_all": "💾 Экспорт всех…",
        "view_markdown": "Markdown",
        "view_thoughts": "Размышления",
        "theme_tip": "Переключить тему",
        "zoom_in_tip": "Крупнее (Ctrl+=)",
        "zoom_out_tip": "Мельче (Ctrl+-)",
        "lang_tip": "Язык интерфейса",
        # список
        "loaded_logs": "Загруженные логи",
        "clear_list": "Очистить список",
        "messages_short": "сообщ.",
        # вкладки
        "tab_clean": "Чистый вид",
        "tab_raw": "Исходный JSON",
        "copy_json": "Копировать JSON",
        # карточка
        "user": "ПОЛЬЗОВАТЕЛЬ",
        "model": "МОДЕЛЬ",
        "copy": "Копировать",
        "copy_more": "▾",
        "copy_with_thoughts": "Копировать с размышлениями",
        "copy_only_thoughts": "Копировать только размышления",
        "thoughts_n": "💭 Размышления ({n})",
        "tokens_short": "ток.",
        "attachment": "Вложение",
        "empty_message": "[пустое сообщение]",
        "system_instruction": "СИСТЕМНАЯ ИНСТРУКЦИЯ",
        # статусы и сообщения
        "status_hint": "Откройте файл лога или перетащите файлы/папку в окно",
        "msg_copied": "Сообщение скопировано в буфер обмена",
        "thoughts_copied": "Размышления скопированы",
        "json_copied": "Исходный JSON скопирован",
        "copied_n": "{what}: скопировано {n} символов",
        "loaded_n": "Загружено: {n}",
        "errors_n": ", ошибок: {n}",
        "open_first": "Сначала откройте лог.",
        "list_empty": "Список логов пуст.",
        "no_logs_in_folder": ("В папке (и подпапках) не найдено файлов, похожих "
                              "на логи AI Studio.\nИскал JSON с ключами "
                              "chunkedPrompt / runSettings."),
        "not_all_loaded": "Не все файлы загружены",
        "not_logs": "Эти файлы не распознаны как логи AI Studio:",
        "loading": "Загрузка логов…",
        "cancel": "Отмена",
        # информация о чате
        "info_model": "модель",
        "info_msgs": "сообщений: {n} (промтов {u} / ответов {m})",
        "info_thoughts": "размышлений: {n}",
        # диалоги
        "dlg_open_files": "Выберите файлы логов AI Studio",
        "dlg_open_folder": "Выберите папку с логами",
        "dlg_save_dir": "Папка для сохранения",
        "dlg_all_files": "Все файлы (*);;JSON (*.json)",
        "export_done": "Экспорт завершён",
        "export_result": "Создано файлов: {n}\nПапка: {dir}",
        "export_errors": "Ошибки:",
        "exported_n": "Экспортировано файлов: {n}",
        # диалог экспорта
        "exp_title": "Настройки экспорта",
        "exp_format": "Формат",
        "exp_format_file": "Формат файла:",
        "exp_fmt_txt": "TXT — чистый текст",
        "exp_fmt_html": "HTML — красивый просмотр в браузере",
        "exp_fmt_md": "Markdown (.md)",
        "exp_content": "Содержимое",
        "exp_content_what": "Что экспортировать:",
        "exp_content_all": "Весь чат",
        "exp_content_prompts": "Только промты",
        "exp_content_answers": "Только ответы",
        "exp_content_thoughts": "Только размышления",
        "exp_numbering": "Нумерация сообщений (#1, #2, …)",
        "exp_timestamps": "Метки времени сообщений",
        "exp_metadata": "Шапка: модель, параметры, статистика",
        "exp_sysinstr": "Системная инструкция (если есть)",
        "exp_attachments": "Вложения: плейсхолдер + ссылка на Google Drive",
        "exp_render_md": "HTML: рендерить Markdown (код, жирный, списки)",
        "exp_thoughts": "Размышления модели:",
        "exp_th_exclude": "Не включать",
        "exp_th_include": "Включать в сообщения",
        "exp_th_separate": "Отдельным файлом (*_thoughts)",
        "exp_labels": "Подписи ролей",
        "exp_auto_model": "Подпись модели = имя модели из лога",
        "exp_label_user": "Пользователь:",
        "exp_label_model": "Модель:",
        "exp_batch_note": "Будет экспортировано файлов: {n}",
        "exp_ok": "Экспортировать",
        # поиск
        "tab_search": "🔎 Поиск",
        "search_placeholder": "Поиск по всем проиндексированным логам… "
                              "(слова, \"точные фразы\", префикс*)",
        "search_scope_all": "Везде",
        "search_scope_user": "В промтах",
        "search_scope_model": "В ответах",
        "search_scope_thoughts": "В размышлениях",
        "search_btn": "Найти",
        "index_folder_btn": "📂 Индексировать папку…",
        "index_stats": "В индексе: файлов {files}, сообщений {msgs}, "
                       "БД {mb:.1f} МБ",
        "indexing": "Индексация…",
        "index_done": "Индексация завершена",
        "search_no_results": "Ничего не найдено. Проверьте, что нужная папка "
                             "проиндексирована.",
        "search_results_n": "Найдено: {n}",
        "search_hint": "Дабл-клик по результату открывает лог. Индекс "
                       "инкрементальный: повторная индексация той же папки "
                       "обрабатывает только изменённые файлы.",
    },
    "en": {
        "open_files": "📄 Open file(s)",
        "open_folder": "📁 Open folder",
        "copy_menu": "📋 Copy ▾",
        "copy_all": "Entire chat",
        "copy_prompts": "Prompts only",
        "copy_answers": "Answers only",
        "copy_thoughts": "Thoughts only",
        "export_current": "💾 Export current…",
        "export_all": "💾 Export all…",
        "view_markdown": "Markdown",
        "view_thoughts": "Thoughts",
        "theme_tip": "Toggle theme",
        "zoom_in_tip": "Zoom in (Ctrl+=)",
        "zoom_out_tip": "Zoom out (Ctrl+-)",
        "lang_tip": "Interface language",
        "loaded_logs": "Loaded logs",
        "clear_list": "Clear list",
        "messages_short": "msgs",
        "tab_clean": "Clean view",
        "tab_raw": "Raw JSON",
        "copy_json": "Copy JSON",
        "user": "USER",
        "model": "MODEL",
        "copy": "Copy",
        "copy_more": "▾",
        "copy_with_thoughts": "Copy with thoughts",
        "copy_only_thoughts": "Copy thoughts only",
        "thoughts_n": "💭 Thoughts ({n})",
        "tokens_short": "tok.",
        "attachment": "Attachment",
        "empty_message": "[empty message]",
        "system_instruction": "SYSTEM INSTRUCTION",
        "status_hint": "Open a log file or drag & drop files/folder into the window",
        "msg_copied": "Message copied to clipboard",
        "thoughts_copied": "Thoughts copied",
        "json_copied": "Raw JSON copied",
        "copied_n": "{what}: copied {n} characters",
        "loaded_n": "Loaded: {n}",
        "errors_n": ", errors: {n}",
        "open_first": "Open a log first.",
        "list_empty": "The log list is empty.",
        "no_logs_in_folder": ("No files that look like AI Studio logs were found "
                              "in the folder (and subfolders).\nLooked for JSON "
                              "with chunkedPrompt / runSettings keys."),
        "not_all_loaded": "Some files were not loaded",
        "not_logs": "These files were not recognized as AI Studio logs:",
        "loading": "Loading logs…",
        "cancel": "Cancel",
        "info_model": "model",
        "info_msgs": "messages: {n} (prompts {u} / answers {m})",
        "info_thoughts": "thoughts: {n}",
        "dlg_open_files": "Select AI Studio log files",
        "dlg_open_folder": "Select folder with logs",
        "dlg_save_dir": "Output folder",
        "dlg_all_files": "All files (*);;JSON (*.json)",
        "export_done": "Export finished",
        "export_result": "Files created: {n}\nFolder: {dir}",
        "export_errors": "Errors:",
        "exported_n": "Files exported: {n}",
        "exp_title": "Export settings",
        "exp_format": "Format",
        "exp_format_file": "File format:",
        "exp_fmt_txt": "TXT — plain text",
        "exp_fmt_html": "HTML — pretty view in browser",
        "exp_fmt_md": "Markdown (.md)",
        "exp_content": "Content",
        "exp_content_what": "What to export:",
        "exp_content_all": "Entire chat",
        "exp_content_prompts": "Prompts only",
        "exp_content_answers": "Answers only",
        "exp_content_thoughts": "Thoughts only",
        "exp_numbering": "Message numbering (#1, #2, …)",
        "exp_timestamps": "Message timestamps",
        "exp_metadata": "Header: model, settings, stats",
        "exp_sysinstr": "System instruction (if present)",
        "exp_attachments": "Attachments: placeholder + Google Drive link",
        "exp_render_md": "HTML: render Markdown (code, bold, lists)",
        "exp_thoughts": "Model thoughts:",
        "exp_th_exclude": "Exclude",
        "exp_th_include": "Include in messages",
        "exp_th_separate": "Separate file (*_thoughts)",
        "exp_labels": "Role labels",
        "exp_auto_model": "Model label = model name from the log",
        "exp_label_user": "User:",
        "exp_label_model": "Model:",
        "exp_batch_note": "Files to be exported: {n}",
        "exp_ok": "Export",
        # search
        "tab_search": "🔎 Search",
        "search_placeholder": "Search across all indexed logs… "
                              "(words, \"exact phrases\", prefix*)",
        "search_scope_all": "Everywhere",
        "search_scope_user": "In prompts",
        "search_scope_model": "In answers",
        "search_scope_thoughts": "In thoughts",
        "search_btn": "Search",
        "index_folder_btn": "📂 Index folder…",
        "index_stats": "Index: {files} files, {msgs} messages, "
                       "DB {mb:.1f} MB",
        "indexing": "Indexing…",
        "index_done": "Indexing finished",
        "search_no_results": "Nothing found. Make sure the folder is indexed.",
        "search_results_n": "Found: {n}",
        "search_hint": "Double-click a result to open the log. The index is "
                       "incremental: re-indexing the same folder only "
                       "processes changed files.",
    },
}

_current = "ru"


def set_lang(lang: str):
    global _current
    if lang in _STRINGS:
        _current = lang


def get_lang() -> str:
    return _current


def tr(key: str, **fmt) -> str:
    s = _STRINGS.get(_current, {}).get(key)
    if s is None:
        s = _STRINGS["ru"].get(key, key)
    if fmt:
        try:
            return s.format(**fmt)
        except (KeyError, IndexError):
            return s
    return s
