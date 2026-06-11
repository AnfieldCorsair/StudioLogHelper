# -*- coding: utf-8 -*-
"""
i18n.py — локализация интерфейса (RU / EN).

Использование:
    import i18n
    from i18n import tr

    i18n.set_lang("en")
    tr("open_files")                 # -> "📂 Open files…"
    tr("loaded_n", n=5)              # подстановка параметров через str.format
"""

from __future__ import annotations

# Доступные языки: код -> название в выпадающем списке
LANGS = {
    "ru": "Русский",
    "en": "English",
}

DEFAULT_LANG = "ru"

_lang = DEFAULT_LANG


def set_lang(code: str) -> None:
    """Устанавливает текущий язык интерфейса ('ru' | 'en')."""
    global _lang
    _lang = code if code in LANGS else DEFAULT_LANG


def get_lang() -> str:
    """Возвращает код текущего языка."""
    return _lang


def tr(key: str, **kwargs) -> str:
    """Перевод строки по ключу с подстановкой параметров.

    Порядок поиска: текущий язык -> русский -> сам ключ.
    При нехватке параметров формата строка возвращается как есть.
    """
    table = _STRINGS.get(_lang, _STRINGS[DEFAULT_LANG])
    s = table.get(key)
    if s is None:
        s = _STRINGS[DEFAULT_LANG].get(key, key)
    if kwargs:
        try:
            return s.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return s
    return s


# ----------------------------------------------------------------------------
# Строки
# ----------------------------------------------------------------------------

_RU = {
    # --- общее ---
    "cancel": "Отмена",
    "user": "ПОЛЬЗОВАТЕЛЬ",
    "model": "МОДЕЛЬ",
    "status_hint": "Откройте файлы или папку с логами AI Studio — "
                   "или просто перетащите их в окно.",
    "loading": "Загрузка…",

    # --- верхняя панель ---
    "open_files": "📂 Открыть файлы…",
    "open_folder": "🗂 Открыть папку…",
    "copy_menu": "📋 Копировать ▾",
    "copy_all": "Весь чат",
    "copy_prompts": "Только промты",
    "copy_answers": "Только ответы",
    "copy_thoughts": "Только размышления",
    "export_current": "💾 Экспорт…",
    "export_all": "Экспорт всех…",
    "view_markdown": "Markdown",
    "view_thoughts": "Размышления",
    "zoom_in_tip": "Крупнее (Ctrl+=)",
    "zoom_out_tip": "Мельче (Ctrl+-)",
    "lang_tip": "Язык интерфейса",
    "theme_tip": "Переключить тему",

    # --- список файлов ---
    "loaded_logs": "Загруженные логи",
    "clear_list": "Очистить список",
    "messages_short": "сообщ.",

    # --- вкладки ---
    "tab_clean": "Чистый вид",
    "tab_raw": "Исходный JSON",
    "tab_search": "🔎 Поиск",
    "copy_json": "📋 Копировать JSON",

    # --- инфо о чате ---
    "info_model": "Модель",
    "info_msgs": "{n} сообщений (промтов: {u}, ответов: {m})",
    "info_thoughts": "размышлений: {n}",
    "system_instruction": "Системная инструкция",

    # --- карточка сообщения ---
    "copy": "Копировать",
    "copy_more": "▾",
    "copy_with_thoughts": "Копировать с размышлениями",
    "copy_only_thoughts": "Копировать только размышления",
    "thoughts_n": "💭 Размышления ({n})",
    "tokens_short": "ток.",
    "empty_message": "[пустое сообщение]",

    # --- статусы / сообщения ---
    "msg_copied": "Сообщение скопировано.",
    "thoughts_copied": "Размышления скопированы.",
    "json_copied": "JSON скопирован.",
    "copied_n": "Скопировано: {what} — {n} символов.",
    "loaded_n": "Загружено логов: {n}.",
    "errors_n": " Ошибок: {n}.",
    "not_all_loaded": "Загружены не все файлы",
    "not_logs": "Эти файлы не похожи на логи AI Studio "
                "или не читаются:",
    "no_logs_in_folder": "В выбранной папке не найдено файлов, "
                         "похожих на логи AI Studio.",
    "open_first": "Сначала откройте лог.",
    "list_empty": "Список пуст — нечего экспортировать.",

    # --- диалоги ---
    "dlg_open_files": "Выберите файлы логов AI Studio",
    "dlg_open_folder": "Выберите папку с логами",
    "dlg_all_files": "Все файлы (*);;JSON (*.json *.txt)",
    "dlg_save_dir": "Папка для сохранения",

    # --- экспорт ---
    "exp_title": "Настройки экспорта",
    "exp_format": "Формат",
    "exp_format_file": "Формат файла:",
    "exp_fmt_txt": "TXT — простой текст",
    "exp_fmt_html": "HTML — страница с оформлением",
    "exp_fmt_md": "Markdown (.md)",
    "exp_fmt_json": "JSON — чистая структура",
    "exp_fmt_jsonl": "JSONL — по сообщению на строку",
    "exp_content_what": "Что экспортировать:",
    "exp_content_all": "Весь чат",
    "exp_content_prompts": "Только промты",
    "exp_content_answers": "Только ответы",
    "exp_content_thoughts": "Только размышления",
    "exp_content": "Содержимое",
    "exp_numbering": "Нумерация сообщений",
    "exp_timestamps": "Метки времени",
    "exp_metadata": "Шапка (модель, параметры)",
    "exp_sysinstr": "Системная инструкция",
    "exp_attachments": "Вложения (плейсхолдеры + ссылки)",
    "exp_render_md": "HTML: рендерить Markdown",
    "exp_thoughts": "Размышления:",
    "exp_th_exclude": "Не включать",
    "exp_th_include": "Включить в сообщения",
    "exp_th_separate": "Отдельным файлом",
    "exp_labels": "Подписи ролей",
    "exp_auto_model": "Подпись модели = имя модели из лога",
    "exp_label_user": "Пользователь:",
    "exp_label_model": "Модель:",
    "exp_batch_note": "Будет экспортировано чатов: {n}.",
    "exp_ok": "Экспортировать",
    "export_done": "Экспорт завершён",
    "export_result": "Создано файлов: {n}\nПапка: {dir}",
    "export_errors": "Ошибки:",
    "exported_n": "Экспортировано файлов: {n}.",

    # --- поиск ---
    "search_placeholder": "Слова, \"точные фразы\"… (Enter — искать)",
    "search_btn": "Найти",
    "search_scope_all": "Везде",
    "search_scope_user": "Промты",
    "search_scope_model": "Ответы",
    "search_scope_thoughts": "Размышления",
    "search_scope_txt": "Текстовые файлы",
    "search_hint": "Слова соединяются как И; \"в кавычках\" — точная фраза; "
                   "последнее слово ищется как префикс. "
                   "Дабл-клик по результату открывает лог.",
    "search_no_results": "Ничего не найдено.",
    "search_results_n": "Найдено: {n}.",
    "index_folder_btn": "🗂 Индексировать папку…",
    "indexing": "Индексация…",
    "index_done": "Индексация завершена",
    "index_stats": "Индекс: {files} файлов, {msgs} записей, {mb:.1f} МБ",

    # --- core: вложения ---
    "att_image": "Изображение",
    "att_document": "Документ",
    "att_video": "Видео",
    "att_audio": "Аудио",
    "att_file": "Файл",
    "att_youtube": "YouTube-видео",
    "att_generic": "Вложение",
    "core_attachment": "Вложение",

    # --- core: парсер ---
    "core_untitled": "Без названия",
    "core_err_root": "Корень JSON — не объект; это не похоже на лог AI Studio.",
    "core_err_no_chunks": "Не найден список сообщений (chunkedPrompt.chunks). "
                          "Файл не похож на лог Google AI Studio.",
    "core_err_json": "Не удалось прочитать JSON: {err}",
    "core_err_unknown_fmt": "Неизвестный формат: {fmt}",
    "core_warn_chunk": "Чанк #{idx}: не объект, пропущен.",
    "core_warn_dangling": "В конце лога есть размышления без итогового "
                          "ответа модели.",
    "core_warn_empty": "Лог не содержит сообщений.",

    # --- core: экспорт ---
    "core_chat": "Чат",
    "core_model": "Модель",
    "core_params": "Параметры",
    "core_msgs_count": "Сообщений: {n} (промтов: {u}, ответов: {m})",
    "core_sysinstr_upper": "СИСТЕМНАЯ ИНСТРУКЦИЯ",
    "core_thoughts_tag": "Размышления",
    "core_model_thoughts": "Размышления модели",
    "core_thoughts_upper": "РАЗМЫШЛЕНИЯ МОДЕЛИ",
    "core_thoughts_sep_title": "Размышления — {title}",
    "empty_message_plain": "пустое сообщение",
}

_EN = {
    # --- common ---
    "cancel": "Cancel",
    "user": "USER",
    "model": "MODEL",
    "status_hint": "Open AI Studio log files or a folder — "
                   "or just drag & drop them here.",
    "loading": "Loading…",

    # --- top bar ---
    "open_files": "📂 Open files…",
    "open_folder": "🗂 Open folder…",
    "copy_menu": "📋 Copy ▾",
    "copy_all": "Whole chat",
    "copy_prompts": "Prompts only",
    "copy_answers": "Answers only",
    "copy_thoughts": "Thoughts only",
    "export_current": "💾 Export…",
    "export_all": "Export all…",
    "view_markdown": "Markdown",
    "view_thoughts": "Thoughts",
    "zoom_in_tip": "Zoom in (Ctrl+=)",
    "zoom_out_tip": "Zoom out (Ctrl+-)",
    "lang_tip": "Interface language",
    "theme_tip": "Toggle theme",

    # --- file list ---
    "loaded_logs": "Loaded logs",
    "clear_list": "Clear list",
    "messages_short": "msgs",

    # --- tabs ---
    "tab_clean": "Clean view",
    "tab_raw": "Raw JSON",
    "tab_search": "🔎 Search",
    "copy_json": "📋 Copy JSON",

    # --- chat info ---
    "info_model": "Model",
    "info_msgs": "{n} messages (prompts: {u}, answers: {m})",
    "info_thoughts": "thoughts: {n}",
    "system_instruction": "System instruction",

    # --- message card ---
    "copy": "Copy",
    "copy_more": "▾",
    "copy_with_thoughts": "Copy with thoughts",
    "copy_only_thoughts": "Copy thoughts only",
    "thoughts_n": "💭 Thoughts ({n})",
    "tokens_short": "tok.",
    "empty_message": "[empty message]",

    # --- statuses / messages ---
    "msg_copied": "Message copied.",
    "thoughts_copied": "Thoughts copied.",
    "json_copied": "JSON copied.",
    "copied_n": "Copied: {what} — {n} characters.",
    "loaded_n": "Logs loaded: {n}.",
    "errors_n": " Errors: {n}.",
    "not_all_loaded": "Some files were not loaded",
    "not_logs": "These files don't look like AI Studio logs "
                "or could not be read:",
    "no_logs_in_folder": "No files that look like AI Studio logs "
                         "were found in the selected folder.",
    "open_first": "Open a log first.",
    "list_empty": "The list is empty — nothing to export.",

    # --- dialogs ---
    "dlg_open_files": "Select AI Studio log files",
    "dlg_open_folder": "Select a folder with logs",
    "dlg_all_files": "All files (*);;JSON (*.json *.txt)",
    "dlg_save_dir": "Output folder",

    # --- export ---
    "exp_title": "Export settings",
    "exp_format": "Format",
    "exp_format_file": "File format:",
    "exp_fmt_txt": "TXT — plain text",
    "exp_fmt_html": "HTML — styled page",
    "exp_fmt_md": "Markdown (.md)",
    "exp_fmt_json": "JSON — clean structure",
    "exp_fmt_jsonl": "JSONL — one message per line",
    "exp_content_what": "What to export:",
    "exp_content_all": "Whole chat",
    "exp_content_prompts": "Prompts only",
    "exp_content_answers": "Answers only",
    "exp_content_thoughts": "Thoughts only",
    "exp_content": "Content",
    "exp_numbering": "Message numbering",
    "exp_timestamps": "Timestamps",
    "exp_metadata": "Header (model, settings)",
    "exp_sysinstr": "System instruction",
    "exp_attachments": "Attachments (placeholders + links)",
    "exp_render_md": "HTML: render Markdown",
    "exp_thoughts": "Thoughts:",
    "exp_th_exclude": "Exclude",
    "exp_th_include": "Include in messages",
    "exp_th_separate": "Separate file",
    "exp_labels": "Role labels",
    "exp_auto_model": "Model label = model name from the log",
    "exp_label_user": "User:",
    "exp_label_model": "Model:",
    "exp_batch_note": "Chats to be exported: {n}.",
    "exp_ok": "Export",
    "export_done": "Export finished",
    "export_result": "Files created: {n}\nFolder: {dir}",
    "export_errors": "Errors:",
    "exported_n": "Files exported: {n}.",

    # --- search ---
    "search_placeholder": "Words, \"exact phrases\"… (Enter — search)",
    "search_btn": "Search",
    "search_scope_all": "Everywhere",
    "search_scope_user": "Prompts",
    "search_scope_model": "Answers",
    "search_scope_thoughts": "Thoughts",
    "search_scope_txt": "Text files",
    "search_hint": "Words are ANDed; \"quoted\" — exact phrase; "
                   "the last word is matched as a prefix. "
                   "Double-click a result to open the log.",
    "search_no_results": "Nothing found.",
    "search_results_n": "Found: {n}.",
    "index_folder_btn": "🗂 Index a folder…",
    "indexing": "Indexing…",
    "index_done": "Indexing finished",
    "index_stats": "Index: {files} files, {msgs} records, {mb:.1f} MB",

    # --- core: attachments ---
    "att_image": "Image",
    "att_document": "Document",
    "att_video": "Video",
    "att_audio": "Audio",
    "att_file": "File",
    "att_youtube": "YouTube video",
    "att_generic": "Attachment",
    "core_attachment": "Attachment",

    # --- core: parser ---
    "core_untitled": "Untitled",
    "core_err_root": "JSON root is not an object; this doesn't look like "
                     "an AI Studio log.",
    "core_err_no_chunks": "Message list not found (chunkedPrompt.chunks). "
                          "The file doesn't look like a Google AI Studio log.",
    "core_err_json": "Failed to read JSON: {err}",
    "core_err_unknown_fmt": "Unknown format: {fmt}",
    "core_warn_chunk": "Chunk #{idx}: not an object, skipped.",
    "core_warn_dangling": "The log ends with thoughts that have no final "
                          "model answer.",
    "core_warn_empty": "The log contains no messages.",

    # --- core: export ---
    "core_chat": "Chat",
    "core_model": "Model",
    "core_params": "Settings",
    "core_msgs_count": "Messages: {n} (prompts: {u}, answers: {m})",
    "core_sysinstr_upper": "SYSTEM INSTRUCTION",
    "core_thoughts_tag": "Thoughts",
    "core_model_thoughts": "Model thoughts",
    "core_thoughts_upper": "MODEL THOUGHTS",
    "core_thoughts_sep_title": "Thoughts — {title}",
    "empty_message_plain": "empty message",
}

_STRINGS = {"ru": _RU, "en": _EN}
