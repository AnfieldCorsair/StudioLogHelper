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
    "export_all": "Экспорт всех файлов…",
    "view_markdown": "Markdown",
    "view_thoughts": "Размышления",
    "zoom_in_tip": "Крупнее (Ctrl+=)",
    "zoom_out_tip": "Мельче (Ctrl+-)",
    "lang_tip": "Язык интерфейса",
    "theme_tip": "Переключить тему",

    # --- список файлов ---
    "loaded_logs": "Загруженные логи",

    "show_extensions": "Расширения",
    "show_extensions_tip": "Показывать расширение и тип исходного файла в списке логов",
    "no_extension": "без расширения",
    "source_json": "Исходный JSON",
    "source_text": "Исходный текст",
    "copy_source_json": "📋 Копировать JSON",
    "copy_source_text": "📋 Копировать TXT",
    "organize_button": "🗃 Проект и категории ▾",
    "new_text_log": "Создать TXT-лог…",
    "new_category": "Создать категорию/группу…",
    "assign_category": "Назначить категорию текущему файлу…",
    "category_name": "Название категории:",
    "file_name": "Имя файла:",
    "category_created": "Категория создана: {name}",
    "category_assigned": "Категория назначена: {name}",
    "text_log_created": "TXT-лог создан: {path}",
    "all_categories": "Все категории",
    "uncategorized": "Без категории",
    "project_new": "Новый проект…",
    "project_open": "Открыть проект .slh.json…",
    "project_save": "Сохранить проект .slh.json…",
    "project_note_current": "Заметка к текущему файлу…",
    "organize_tip": "Проекты .slh.json сохраняют список файлов, категории и заметки. Используйте категории для наборов: ответы модели, запросы+ответы, произведения и т.п.",
    "project_name": "Название проекта:",
    "project_note": "Заметка:",
    "project_saved": "Проект сохранён: {path}",
    "project_loaded": "Проект загружен: {path}",
    "project_created": "Проект создан: {name}",
    "note_saved": "Заметка сохранена.",
    "category_label": "Категория",
    "note_label": "Заметка",
    "search_where": "Где искать:",
    "search_in_current": "В выбранном файле",
    "search_in_loaded": "Во всех открытых файлах",
    "search_in_index_all": "В проиндексированной папке: все файлы",
    "search_in_index_txt": "В проиндексированной папке: только TXT/MD",
    "search_in_index_json": "В проиндексированной папке: JSON/диалоги",
    "search_what": "Что искать:",
    "search_need_index": "Для поиска по папке сначала нажмите «Индексировать папку…».",

    "tags_label": "Теги",
    "set_tags_current": "Теги текущего файла…",
    "tags_prompt": "Теги через запятую:",
    "tags_saved": "Теги сохранены.",
    "filter_category": "Категория:",
    "filter_text": "Фильтр:",
    "filter_tag": "Тег:",
    "all_tags": "Все теги",
    "filter_placeholder": "часть названия/пути…",
    "show_diagnostics": "Диагностика",
    "show_diagnostics_tip": "Показывать формат, путь и служебные данные текущего файла",
    "diagnostics_label": "Диагностика",
    "batch_export_set": "Создать набор/экспорт в папку…",
    "batch_title": "Создание набора из файлов",
    "batch_source": "Какие файлы:",
    "batch_selected": "Выделенные в списке",
    "batch_all_loaded": "Все открытые файлы",
    "batch_result_category": "Категория результата:",
    "batch_note": "Заметка результата:",
    "batch_load_results": "Открыть созданные файлы в приложении",
    "batch_index_results": "Проиндексировать папку результата после экспорта",
    "batch_no_files": "Нет файлов для пакетной операции.",
    "batch_done": "Создан набор: файлов {n}, папка {dir}",
    "export_profiles": "Профиль экспорта:",
    "profile_none": "Без профиля / вручную",
    "profile_answers_txt": "TXT: только ответы модели",
    "profile_full_txt": "TXT: весь чат",
    "profile_full_md": "Markdown: весь чат",
    "profile_prompts_txt": "TXT: только промты",
    "profile_save": "Сохранить как профиль…",
    "profile_name": "Название профиля:",
    "profile_saved": "Профиль сохранён: {name}",
    "recent_projects": "Недавние проекты",
    "autosaved": "Проект автосохранён.",
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
    "source_copied": "Исходник скопирован.",
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


    # --- расширенные разделители текстовых логов ---
    "sep_button": "⚙️ Разделители…",
    "sep_title": "Расширенные разделители текстовых логов",
    "sep_hint": "Для Arena AI и очищенных TXT/MD можно добавить свои заголовки ролей. Пишите по одному варианту на строку: например, Right Gemini, Bot, Вопрос, Ответ.",
    "sep_user_headers": "Заголовки пользователя:",
    "sep_model_headers": "Заголовки модели:",
    "sep_numbered_mode": "Если блоки только #1:, #2:",
    "sep_num_alternating": "Считать чередованием пользователь → модель",
    "sep_num_model": "Считать все блоки ответами модели",
    "sep_num_user": "Считать все блоки запросами пользователя",
    "sep_save": "Сохранить",
    "sep_saved": "Настройки разделителей сохранены. Новые файлы будут распознаны с ними.",

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
    "core_warn_numbered_guess": "Нумерованные блоки #1/#2 распознаны как чередование пользователь/модель. Если это только ответы или только запросы — поменяйте режим в расширенных разделителях.",
    "core_err_text_no_messages": "Не удалось распознать текстовый лог: не найдены блоки User/Model/#N.",

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
    "export_all": "Export all files…",
    "view_markdown": "Markdown",
    "view_thoughts": "Thoughts",
    "zoom_in_tip": "Zoom in (Ctrl+=)",
    "zoom_out_tip": "Zoom out (Ctrl+-)",
    "lang_tip": "Interface language",
    "theme_tip": "Toggle theme",

    # --- file list ---
    "loaded_logs": "Loaded logs",

    "show_extensions": "Extensions",
    "show_extensions_tip": "Show source file extension and type in the log list",
    "no_extension": "no extension",
    "source_json": "Raw JSON",
    "source_text": "Raw text",
    "copy_source_json": "📋 Copy JSON",
    "copy_source_text": "📋 Copy TXT",
    "organize_button": "🗃 Project & categories ▾",
    "new_text_log": "Create TXT log…",
    "new_category": "Create category/group…",
    "assign_category": "Assign current file to category…",
    "category_name": "Category name:",
    "file_name": "File name:",
    "category_created": "Category created: {name}",
    "category_assigned": "Category assigned: {name}",
    "text_log_created": "TXT log created: {path}",
    "all_categories": "All categories",
    "uncategorized": "Uncategorized",
    "project_new": "New project…",
    "project_open": "Open project .slh.json…",
    "project_save": "Save project .slh.json…",
    "project_note_current": "Note for current file…",
    "organize_tip": "Projects .slh.json save file lists, categories and notes. Use categories for sets: model answers, prompts+answers, works, etc.",
    "project_name": "Project name:",
    "project_note": "Note:",
    "project_saved": "Project saved: {path}",
    "project_loaded": "Project loaded: {path}",
    "project_created": "Project created: {name}",
    "note_saved": "Note saved.",
    "category_label": "Category",
    "note_label": "Note",
    "search_where": "Search in:",
    "search_in_current": "Selected file",
    "search_in_loaded": "All opened files",
    "search_in_index_all": "Indexed folder: all files",
    "search_in_index_txt": "Indexed folder: TXT/MD only",
    "search_in_index_json": "Indexed folder: JSON/dialogs",
    "search_what": "Search what:",
    "search_need_index": "Index a folder first to search by folder.",

    "tags_label": "Tags",
    "set_tags_current": "Tags for current file…",
    "tags_prompt": "Comma-separated tags:",
    "tags_saved": "Tags saved.",
    "filter_category": "Category:",
    "filter_text": "Filter:",
    "filter_tag": "Tag:",
    "all_tags": "All tags",
    "filter_placeholder": "part of title/path…",
    "show_diagnostics": "Diagnostics",
    "show_diagnostics_tip": "Show format, path and technical details for the current file",
    "diagnostics_label": "Diagnostics",
    "batch_export_set": "Create set / export to folder…",
    "batch_title": "Create a file set",
    "batch_source": "Files:",
    "batch_selected": "Selected in the list",
    "batch_all_loaded": "All opened files",
    "batch_result_category": "Result category:",
    "batch_note": "Result note:",
    "batch_load_results": "Open created files in the app",
    "batch_index_results": "Index the output folder after export",
    "batch_no_files": "No files for batch operation.",
    "batch_done": "Set created: {n} files, folder {dir}",
    "export_profiles": "Export profile:",
    "profile_none": "No profile / manual",
    "profile_answers_txt": "TXT: model answers only",
    "profile_full_txt": "TXT: whole chat",
    "profile_full_md": "Markdown: whole chat",
    "profile_prompts_txt": "TXT: prompts only",
    "profile_save": "Save as profile…",
    "profile_name": "Profile name:",
    "profile_saved": "Profile saved: {name}",
    "recent_projects": "Recent projects",
    "autosaved": "Project auto-saved.",
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
    "source_copied": "Source copied.",
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


    # --- advanced text-log separators ---
    "sep_button": "⚙️ Separators…",
    "sep_title": "Advanced text-log separators",
    "sep_hint": "For Arena AI and cleaned TXT/MD files you can add custom role headers. Put one variant per line, e.g. Right Gemini, Bot, Question, Answer.",
    "sep_user_headers": "User headers:",
    "sep_model_headers": "Model headers:",
    "sep_numbered_mode": "For #1:, #2: blocks:",
    "sep_num_alternating": "Treat as user → model alternation",
    "sep_num_model": "Treat all blocks as model answers",
    "sep_num_user": "Treat all blocks as user prompts",
    "sep_save": "Save",
    "sep_saved": "Separator settings saved. Newly opened files will use them.",

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
    "core_warn_numbered_guess": "Numbered #1/#2 blocks were parsed as user/model alternation. If they are only answers or only prompts, change the mode in advanced separators.",
    "core_err_text_no_messages": "Could not parse the text log: no User/Model/#N blocks were found.",

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
