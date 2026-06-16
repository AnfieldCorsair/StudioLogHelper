# -*- coding: utf-8 -*-
"""
core.py — ядро парсера логов Google AI Studio.

Лог AI Studio (скачанный с Google Drive, обычно без расширения) — это JSON вида:
{
  "runSettings": { "model": "...", "temperature": ..., ... },
  "systemInstruction": { "text": "..." }  (может быть пустым),
  "chunkedPrompt": {
     "chunks": [ {"role": "user"|"model", "text": "...", "isThought": true?,
                  "driveImage": {"id": "..."}?, "tokenCount": ..., "createTime": "..."} , ...],
     "pendingInputs": [...]
  }
}

Модуль не зависит от GUI и может использоваться из CLI.
"""

from __future__ import annotations

import json
import html as _html
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote as _urlquote

from i18n import tr

# ----------------------------------------------------------------------------
# Модель данных
# ----------------------------------------------------------------------------

# ключ из JSON -> ключ локализации подписи
ATTACHMENT_KINDS = {
    "driveImage": "att_image",
    "driveDocument": "att_document",
    "driveVideo": "att_video",
    "driveAudio": "att_audio",
    "driveFile": "att_file",
    "youtubeVideo": "att_youtube",
}


@dataclass
class Attachment:
    kind: str                 # ключ из JSON (driveImage и т.п.)
    drive_id: str = ""

    @property
    def label(self) -> str:
        return tr(ATTACHMENT_KINDS.get(self.kind, "att_generic"))

    @property
    def url(self) -> str:
        if not self.drive_id:
            return ""
        # id берётся из внешнего JSON — экранируем на случай «злого» лога
        safe_id = _urlquote(self.drive_id, safe="")
        if self.kind == "youtubeVideo":
            return f"https://www.youtube.com/watch?v={safe_id}"
        return f"https://drive.google.com/file/d/{safe_id}/view"


@dataclass
class Message:
    role: str                                  # "user" | "model" | другое
    text: str = ""
    thoughts: list = field(default_factory=list)       # список текстов размышлений
    attachments: list = field(default_factory=list)    # список Attachment
    token_count: int = 0
    create_time: str = ""                      # ISO-строка из лога
    finish_reason: str = ""

    @property
    def is_user(self) -> bool:
        return self.role == "user"

    @property
    def has_thoughts(self) -> bool:
        return bool(self.thoughts)

    def time_str(self) -> str:
        """Человекочитаемое время (локальное представление ISO-метки)."""
        if not self.create_time:
            return ""
        try:
            dt = datetime.fromisoformat(self.create_time.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%d.%m.%Y %H:%M:%S")
        except (ValueError, OSError):
            return self.create_time


@dataclass
class ChatLog:
    path: str = ""
    title: str = ""
    model: str = ""
    source_format: str = ""                           # json | text
    raw_text: str = ""                                # исходник для text-логов
    run_settings: dict = field(default_factory=dict)
    system_instruction: str = ""
    messages: list = field(default_factory=list)       # список Message
    warnings: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def user_count(self) -> int:
        return sum(1 for m in self.messages if m.is_user)

    @property
    def model_count(self) -> int:
        # именно роль "model": неизвестные роли не считаем «ответами»
        return sum(1 for m in self.messages if m.role == "model")

    @property
    def thought_count(self) -> int:
        return sum(len(m.thoughts) for m in self.messages)


class ParseError(Exception):
    pass


# ----------------------------------------------------------------------------
# Парсинг
# ----------------------------------------------------------------------------

def _chunk_text(chunk: dict) -> str:
    """Достаём текст чанка: основное поле text, иначе склейка parts."""
    text = chunk.get("text")
    if isinstance(text, str) and text:
        return text
    parts = chunk.get("parts")
    if isinstance(parts, list):
        out = []
        for p in parts:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                out.append(p["text"])
        return "".join(out)
    return ""


def _chunk_attachments(chunk: dict) -> list:
    """Ищем вложения: ключи drive*/youtube* со словарём, содержащим id."""
    found = []
    for key, val in chunk.items():
        if not isinstance(val, dict):
            continue
        if key in ATTACHMENT_KINDS or key.startswith("drive"):
            drive_id = str(val.get("id", "") or "")
            found.append(Attachment(kind=key, drive_id=drive_id))
    return found


def parse_data(data: dict, path: str = "") -> ChatLog:
    """Разбирает уже загруженный JSON-объект лога AI Studio."""
    if not isinstance(data, dict):
        raise ParseError(tr("core_err_root"))

    chat = ChatLog(path=path, raw=data, source_format="json")
    chat.title = Path(path).stem if path else tr("core_untitled")

    rs = data.get("runSettings")
    if isinstance(rs, dict):
        chat.run_settings = rs
        model = rs.get("model", "")
        if isinstance(model, str):
            chat.model = model.split("/")[-1] if model else ""

    si = data.get("systemInstruction")
    if isinstance(si, dict):
        sys_text = si.get("text")
        if not sys_text and isinstance(si.get("parts"), list):
            sys_text = "".join(
                p.get("text", "") for p in si["parts"] if isinstance(p, dict)
            )
        if isinstance(sys_text, str):
            chat.system_instruction = sys_text.strip()
    elif isinstance(si, str):
        chat.system_instruction = si.strip()

    cp = data.get("chunkedPrompt")
    chunks = None
    if isinstance(cp, dict):
        chunks = cp.get("chunks")
    if chunks is None:
        # запасные варианты структуры
        for alt in ("chunks", "history", "messages"):
            if isinstance(data.get(alt), list):
                chunks = data[alt]
                break
    if not isinstance(chunks, list):
        raise ParseError(tr("core_err_no_chunks"))

    pending_thoughts: list = []
    pending_meta: dict = {}

    for idx, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            chat.warnings.append(tr("core_warn_chunk", idx=idx))
            continue

        role = chunk.get("role") or "unknown"
        text = _chunk_text(chunk)
        atts = _chunk_attachments(chunk)
        tok = chunk.get("tokenCount") or 0
        ctime = chunk.get("createTime") or ""
        finish = chunk.get("finishReason") or ""

        if role == "model" and chunk.get("isThought"):
            # размышление — копим до ближайшего "обычного" ответа модели
            if text.strip():
                pending_thoughts.append(text)
            pending_meta.setdefault("create_time", ctime)
            continue

        if role == "model":
            msg = Message(
                role="model",
                text=text,
                thoughts=pending_thoughts,
                attachments=atts,
                token_count=tok if isinstance(tok, int) else 0,
                create_time=ctime or pending_meta.get("create_time", ""),
                finish_reason=str(finish),
            )
            chat.messages.append(msg)
            pending_thoughts, pending_meta = [], {}
            continue

        # user (или неизвестная роль): сливаем подряд идущие чанки одной роли
        # (например, отдельный чанк-вложение + следом текстовый чанк)
        last = chat.messages[-1] if chat.messages else None
        if last is not None and last.role == role and role == "user":
            if text:
                last.text = (last.text + "\n" + text).strip("\n") if last.text else text
            last.attachments.extend(atts)
            if isinstance(tok, int):
                last.token_count += tok
            if not last.create_time:
                last.create_time = ctime
        else:
            chat.messages.append(
                Message(
                    role=role,
                    text=text,
                    attachments=atts,
                    token_count=tok if isinstance(tok, int) else 0,
                    create_time=ctime,
                )
            )

    # размышления без финального ответа (генерация оборвана)
    if pending_thoughts:
        chat.messages.append(
            Message(
                role="model",
                text="",
                thoughts=pending_thoughts,
                create_time=pending_meta.get("create_time", ""),
            )
        )
        chat.warnings.append(tr("core_warn_dangling"))

    if not chat.messages:
        chat.warnings.append(tr("core_warn_empty"))
    return chat


# ----------------------------------------------------------------------------
# Парсинг текстовых логов (Arena AI / очищенные экспорты / простые диалоги)
# ----------------------------------------------------------------------------

DEFAULT_USER_HEADERS = (
    "user", "пользователь", "human", "prompt", "request", "запрос",
)
DEFAULT_MODEL_HEADERS = (
    "right ai", "right model", "model", "modelname", "assistant", "ai",
    "answer", "response", "модель", "ассистент", "ответ",
)


@dataclass
class TextParseOptions:
    """Настройки разбора простых текстовых логов.

    numbered_mode:
      * alternating — строки вида #1:, #2: считаются чередованием user/model;
      * model       — все #N: считаются ответами модели;
      * user        — все #N: считаются запросами пользователя.
    """
    user_headers: list = field(default_factory=list)
    model_headers: list = field(default_factory=list)
    numbered_mode: str = "model"


def _norm_header(s: str) -> str:
    s = s.strip().strip(":").strip()
    s = re.sub(r"\s+", " ", s).lower()
    return s


def _merged_headers(extra: list, defaults: tuple) -> set:
    vals = set(defaults)
    for x in extra or []:
        nx = _norm_header(str(x))
        if nx:
            vals.add(nx)
    return vals


def looks_like_text_log_text(text: str) -> bool:
    """Быстрая эвристика для Arena AI / очищенных текстовых экспортов."""
    head = text[:20000]
    if re.search(r"(?im)^\s*(Arena\s+Side-by-Side\s+Chat|User\s*:|Right\s+(AI|model)\s*:|Model(Name)?\s*:)", head):
        return True
    if len(re.findall(r"(?im)^\s*(User|Right\s+(AI|model)|Model(Name)?|Assistant)\s*$", head)) >= 2:
        return True
    if re.search(r"(?im)^\s*---\s*#?\d+\s+(.{0,40}?)(USER|ПОЛЬЗОВАТЕЛЬ|MODEL|МОДЕЛЬ|Assistant|AI|Ответ)", head):
        return True
    # Нумерованные блоки #1:, #2: — минимум два блока, иначе слишком рискованно.
    return len(re.findall(r"(?m)^\s*#\d+\s*:", head)) >= 2


def _role_from_header(header: str, opts: TextParseOptions) -> Optional[str]:
    h = _norm_header(header)
    uh = _merged_headers(opts.user_headers, DEFAULT_USER_HEADERS)
    mh = _merged_headers(opts.model_headers, DEFAULT_MODEL_HEADERS)
    if h in uh:
        return "user"
    if h in mh:
        return "model"
    # Частые варианты с названием модели: "Right Gemini", "Model GPT-4".
    if h.startswith("right ") or h.startswith("model "):
        return "model"
    return None


def _role_for_number(num: int, opts: TextParseOptions) -> str:
    mode = (opts.numbered_mode or "model").lower()
    if mode == "model":
        return "model"
    if mode == "user":
        return "user"
    return "user" if num % 2 == 1 else "model"


def _flush_text_msg(chat: ChatLog, role: Optional[str], buf: list):
    text = "\n".join(buf).strip("\n")
    if role and text.strip():
        chat.messages.append(Message(role=role, text=text))


def _parse_export_header(line: str) -> Optional[tuple[int, str]]:
    """Распознаёт только реальные заголовки экспортированных сообщений.

    Важно: Markdown-заголовки внутри ответа (`#### 1. Python`) и горизонтальные
    линии (`---`) не должны дробить сообщение. Поэтому принимаем только формы:
      --- #4 МОДЕЛЬ -----
      #4: text              (обрабатывается отдельно numbered_re)
      ## #4 МОДЕЛЬ
    """
    stripped = line.strip()
    if not stripped:
        return None

    # TXT export: --- #4 МОДЕЛЬ --------------------------------------
    m = re.match(r"^-{3,}\s*#(?P<num>\d+)\s+(?P<label>.*?)\s*-{3,}\s*$", stripped)
    if m:
        return int(m.group("num")), m.group("label").strip()

    # Markdown export: ## #4 МОДЕЛЬ  (именно #4 после markdown-решёток)
    m = re.match(r"^#{1,6}\s+#(?P<num>\d+)\s+(?P<label>.+?)\s*$", stripped)
    if m:
        return int(m.group("num")), m.group("label").strip()

    return None


def parse_text_log(text: str, path: str = "", options: Optional[TextParseOptions] = None) -> ChatLog:
    """Разбор plain-text логов: Arena AI, экспортов этой программы и простых диалогов.

    Поддерживаемые блоки:
      User: / Right AI: / Right model: / Model: / ModelName:
      --- #1 USER ---- / ## #2 MODEL
      #1: ... #2: ... (роль берётся из numbered_mode; по умолчанию чередование)
    """
    opts = options or TextParseOptions()
    chat = ChatLog(path=path, title=Path(path).stem if path else tr("core_untitled"),
                   source_format="text", raw_text=text)
    if re.search(r"(?im)^\s*Arena\s+Side-by-Side\s+Chat\s*$", text):
        chat.model = "Arena AI"

    role: Optional[str] = None
    buf: list = []
    saw_numbered = False

    numbered_re = re.compile(r"^\s*#(?P<num>\d+)\s*:\s*(?P<rest>.*)$")
    plain_header_re = re.compile(r"^\s*(?P<header>[\wА-Яа-яЁё][\wА-Яа-яЁё ._-]{0,60})\s*:\s*(?P<rest>.*)$")

    for line in text.splitlines():
        # Игнорируем общий заголовок Arena.
        if re.match(r"(?i)^\s*Arena\s+Side-by-Side\s+Chat\s*$", line):
            continue

        # В некоторых выгрузках роль стоит отдельной строкой без двоеточия:
        # User / Right model / ModelName.
        bare_norm = _norm_header(line)
        bare_role = _role_from_header(line, opts)
        safe_bare = {
            "user", "пользователь", "human",
            "right ai", "right model", "model", "modelname",
            "assistant", "ai", "модель", "ассистент",
        } | _merged_headers(opts.user_headers, ()) | _merged_headers(opts.model_headers, ())
        if bare_role and bare_norm in safe_bare:
            _flush_text_msg(chat, role, buf)
            buf = []
            role = bare_role
            continue

        m = numbered_re.match(line)
        if m:
            _flush_text_msg(chat, role, buf)
            buf = []
            n = int(m.group("num"))
            saw_numbered = True
            role = _role_for_number(n, opts)
            rest = m.group("rest")
            if rest:
                buf.append(rest)
            continue

        exported = _parse_export_header(line)
        if exported:
            n, label = exported
            # Убираем служебные скобки времени и хвостовые разделители.
            label = re.sub(r"\[[^\]]+\]", "", label).strip(" -—	")
            detected = _role_from_header(label, opts) or _role_for_number(n, opts)
            _flush_text_msg(chat, role, buf)
            buf = []
            saw_numbered = True
            role = detected
            continue

        m = plain_header_re.match(line)
        if m:
            # В шапках экспортов есть строки "  Модель: ..." — не считаем
            # их началом сообщения, пока не встретили первый настоящий блок.
            if role is None and line[:1].isspace():
                continue
            detected = _role_from_header(m.group("header"), opts)
            if detected:
                _flush_text_msg(chat, role, buf)
                buf = []
                role = detected
                rest = m.group("rest")
                if rest:
                    buf.append(rest)
                continue

        # До первого распознанного блока пропускаем служебные строки.
        if role is not None:
            buf.append(line)

    _flush_text_msg(chat, role, buf)

    if saw_numbered and (opts.numbered_mode or "model") == "alternating":
        chat.warnings.append(tr("core_warn_numbered_guess"))
    if not chat.messages:
        raise ParseError(tr("core_err_text_no_messages"))
    return chat


def parse_file(path, text_options: Optional[TextParseOptions] = None) -> ChatLog:
    """Читает и парсит файл.

    Оптимизация: для явных текстовых файлов и файлов, которые не начинаются с
    JSON-объекта/массива, сначала пробуем дешёвую эвристику текстового лога.
    Это сильно ускоряет открытие папок с большими TXT-экспортами.
    """
    p = Path(path)
    raw_bytes = p.read_bytes()
    data = None
    last_err = None
    text_candidates = []

    # Сначала декодируем. JSON будем парсить только если файл реально похож на JSON.
    for enc in ("utf-8", "utf-8-sig", "utf-16", "cp1251"):
        try:
            decoded = raw_bytes.decode(enc)
            text_candidates.append(decoded)
        except UnicodeDecodeError as e:
            last_err = e

    # TXT/MD/LOG и любой не-JSON-подобный текст: быстрый путь без json.loads
    # на многомегабайтном тексте.
    suffix = p.suffix.lower()
    for decoded_text in text_candidates:
        stripped = decoded_text.lstrip("\ufeff\x00\n\r\t ")
        looks_jsonish = stripped.startswith("{") or stripped.startswith("[")
        if (suffix in {".txt", ".md", ".log", ".text"} or not looks_jsonish):
            if looks_like_text_log_text(decoded_text):
                return parse_text_log(decoded_text, str(p), text_options)
            if not looks_jsonish:
                # Это обычный текст, но не диалоговый лог.
                break

    # JSON-путь: нужен для AI Studio и файлов без расширения с Google Drive.
    for decoded in text_candidates:
        stripped = decoded.lstrip("\ufeff\x00\n\r\t ")
        if not (stripped.startswith("{") or stripped.startswith("[")):
            continue
        try:
            data = json.loads(decoded)
            break
        except json.JSONDecodeError as e:
            last_err = e
    if data is not None:
        return parse_data(data, str(p))

    # Запасной текстовый путь для UTF-16/сложных случаев.
    for decoded_text in text_candidates:
        if looks_like_text_log_text(decoded_text):
            return parse_text_log(decoded_text, str(p), text_options)
    raise ParseError(tr("core_err_json", err=last_err))

def looks_like_log(path) -> bool:
    """Быстрая эвристика: стоит ли пытаться парсить файл из папки."""
    p = Path(path)
    if not p.is_file():
        return False
    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".zip", ".exe",
                            ".pdf", ".mp4", ".mp3", ".docx", ".xlsx"}:
        return False
    try:
        with p.open("rb") as fh:
            head = fh.read(4096).decode("utf-8", errors="ignore").lstrip()
    except OSError:
        return False
    if head.startswith("{") and (
        '"chunkedPrompt"' in head or '"runSettings"' in head or '"chunks"' in head
    ):
        return True
    return looks_like_text_log_text(head)


def scan_folder(folder, recursive: bool = True) -> list:
    """Возвращает список путей-кандидатов в папке."""
    p = Path(folder)
    it = p.rglob("*") if recursive else p.glob("*")
    return [str(f) for f in sorted(it) if looks_like_log(f)]


# ----------------------------------------------------------------------------
# Настройки экспорта
# ----------------------------------------------------------------------------

THOUGHTS_EXCLUDE = "exclude"     # без размышлений
THOUGHTS_INCLUDE = "include"     # размышления внутри сообщений
THOUGHTS_SEPARATE = "separate"   # размышления отдельным файлом

# фильтр содержимого экспорта
CONTENT_ALL = "all"              # весь чат
CONTENT_PROMPTS = "prompts"      # только промты пользователя
CONTENT_ANSWERS = "answers"      # только ответы модели
CONTENT_THOUGHTS = "thoughts"    # только размышления модели

# Статические значения по умолчанию (для обратной совместимости).
# Актуальные локализованные подписи дают tr("user") / tr("model").
USER_LABEL = "ПОЛЬЗОВАТЕЛЬ"
MODEL_LABEL = "МОДЕЛЬ"


@dataclass
class ExportOptions:
    fmt: str = "txt"                      # "txt" | "html" | "md"
    numbering: bool = True                # нумерация сообщений
    thoughts: str = THOUGHTS_EXCLUDE      # exclude | include | separate
    content: str = CONTENT_ALL            # all | prompts | answers | thoughts
    timestamps: bool = False              # выводить время сообщений
    metadata: bool = True                 # шапка с моделью/настройками
    attachments: bool = True              # плейсхолдеры вложений + ссылки
    system_instruction: bool = True       # выводить системную инструкцию
    render_markdown: bool = True          # html: рендерить markdown
    user_label: str = USER_LABEL
    model_label: str = MODEL_LABEL
    auto_model_label: bool = True         # подпись модели = имя модели из лога


def effective_labels(chat: "ChatLog", opts: "ExportOptions"):
    """Подписи ролей с учётом auto_model_label (имя модели из лога)."""
    user = opts.user_label or USER_LABEL
    model = opts.model_label or MODEL_LABEL
    if opts.auto_model_label and chat.model:
        model = chat.model
    return user, model


def iter_export_messages(chat: "ChatLog", opts: "ExportOptions"):
    """Итератор (номер, сообщение) с учётом фильтра содержимого.

    Нумерация всегда глобальная по чату, чтобы «#4 МОДЕЛЬ» совпадало
    с положением сообщения в полном диалоге.
    """
    for num, msg in enumerate(chat.messages, 1):
        if opts.content == CONTENT_PROMPTS and not msg.is_user:
            continue
        if opts.content == CONTENT_ANSWERS and msg.is_user:
            continue
        if opts.content == CONTENT_THOUGHTS and not msg.has_thoughts:
            continue
        yield num, msg


# ----------------------------------------------------------------------------
# Мини-рендер Markdown -> HTML (без внешних зависимостей)
# ----------------------------------------------------------------------------

_re_bold = re.compile(r"\*\*(.+?)\*\*")
_re_italic = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_re_code = re.compile(r"`([^`]+)`")
_re_link = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_re_strike = re.compile(r"~~(.+?)~~")


def _inline_md(escaped: str) -> str:
    """Инлайн-разметка поверх уже экранированного HTML."""
    escaped = _re_code.sub(r"<code>\1</code>", escaped)
    escaped = _re_bold.sub(r"<b>\1</b>", escaped)
    escaped = _re_italic.sub(r"<i>\1</i>", escaped)
    escaped = _re_strike.sub(r"<s>\1</s>", escaped)
    escaped = _re_link.sub(r'<a href="\2">\1</a>', escaped)
    return escaped


def markdown_to_html(text: str) -> str:
    """Простой и устойчивый конвертер Markdown -> HTML."""
    lines = text.split("\n")
    out: list = []
    i = 0
    in_code = False
    code_buf: list = []
    code_lang = ""
    list_stack: list = []  # "ul" | "ol"

    def close_lists():
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    while i < len(lines):
        line = lines[i]

        if in_code:
            if line.strip().startswith("```"):
                cls = f' class="lang-{_html.escape(code_lang)}"' if code_lang else ""
                out.append(
                    f"<pre{cls}><code>{_html.escape(chr(10).join(code_buf))}</code></pre>"
                )
                in_code, code_buf, code_lang = False, [], ""
            else:
                code_buf.append(line)
            i += 1
            continue

        stripped = line.strip()

        if stripped.startswith("```"):
            close_lists()
            in_code = True
            code_lang = stripped[3:].strip()
            i += 1
            continue

        if not stripped:
            close_lists()
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            close_lists()
            lvl = min(len(m.group(1)) + 2, 6)  # h1->h3 чтобы не кричало
            out.append(f"<h{lvl}>{_inline_md(_html.escape(m.group(2)))}</h{lvl}>")
            i += 1
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        if stripped.startswith(">"):
            close_lists()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(
                "<blockquote>"
                + "<br>".join(_inline_md(_html.escape(q)) for q in quote)
                + "</blockquote>"
            )
            continue

        m = re.match(r"^[-*+]\s+(.*)$", stripped)
        if m:
            if not list_stack or list_stack[-1] != "ul":
                close_lists()
                out.append("<ul>")
                list_stack.append("ul")
            out.append(f"<li>{_inline_md(_html.escape(m.group(1)))}</li>")
            i += 1
            continue

        m = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if m:
            if not list_stack or list_stack[-1] != "ol":
                close_lists()
                out.append("<ol>")
                list_stack.append("ol")
            out.append(f"<li>{_inline_md(_html.escape(m.group(1)))}</li>")
            i += 1
            continue

        # обычный абзац — собираем подряд идущие строки
        para = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith(("```", "#", ">", "- ", "* ", "+ "))
                    or re.match(r"^\d+[.)]\s", nxt)
                    or re.match(r"^(-{3,}|\*{3,}|_{3,})$", nxt)):
                break
            para.append(nxt)
            i += 1
        close_lists()
        out.append("<p>" + "<br>".join(_inline_md(_html.escape(s)) for s in para) + "</p>")

    if in_code and code_buf:  # незакрытый код-блок
        out.append(f"<pre><code>{_html.escape(chr(10).join(code_buf))}</code></pre>")
    close_lists()
    return "\n".join(out)


# ----------------------------------------------------------------------------
# Экспорт: TXT
# ----------------------------------------------------------------------------

def _txt_header(chat: ChatLog, opts: ExportOptions) -> str:
    lines = []
    bar = "=" * 70
    lines.append(bar)
    lines.append(f"  {tr('core_chat')}: {chat.title}")
    if chat.model:
        lines.append(f"  {tr('core_model')}: {chat.model}")
    rs = chat.run_settings
    extra = []
    if "temperature" in rs:
        extra.append(f"temperature={rs['temperature']}")
    if "topP" in rs:
        extra.append(f"topP={rs['topP']}")
    if "topK" in rs:
        extra.append(f"topK={rs['topK']}")
    if "maxOutputTokens" in rs:
        extra.append(f"maxOutputTokens={rs['maxOutputTokens']}")
    if extra:
        lines.append(f"  {tr('core_params')}: {', '.join(extra)}")
    lines.append("  " + tr("core_msgs_count", n=len(chat.messages),
                            u=chat.user_count, m=chat.model_count))
    lines.append(bar)
    return "\n".join(lines)


def _msg_label(msg: Message, num: Optional[int], opts: ExportOptions,
               labels=None) -> str:
    user_l, model_l = labels if labels else (opts.user_label, opts.model_label)
    base = user_l if msg.is_user else model_l
    if msg.role not in ("user", "model"):
        base = msg.role.upper()
    parts = []
    if num is not None:
        parts.append(f"#{num}")
    parts.append(base)
    if opts.timestamps and msg.time_str():
        parts.append(f"[{msg.time_str()}]")
    return " ".join(parts)


def _attachment_lines(msg: Message) -> list:
    out = []
    for a in msg.attachments:
        if a.url:
            out.append(f"[{tr('core_attachment')}: {a.label}] {a.url}")
        else:
            out.append(f"[{tr('core_attachment')}: {a.label}]")
    return out


def export_txt(chat: ChatLog, opts: ExportOptions):
    """Возвращает (основной_текст, текст_размышлений_или_None)."""
    out: list = []
    thoughts_out: list = []
    labels = effective_labels(chat, opts)
    only_thoughts = opts.content == CONTENT_THOUGHTS

    if opts.metadata:
        out.append(_txt_header(chat, opts))
        out.append("")

    if (opts.system_instruction and chat.system_instruction
            and opts.content == CONTENT_ALL):
        out.append(f"--- {tr('core_sysinstr_upper')} " + "-" * 44)
        out.append(chat.system_instruction)
        out.append("")

    for num, msg in iter_export_messages(chat, opts):
        label = _msg_label(msg, num if opts.numbering else None, opts, labels)
        out.append(f"--- {label} " + "-" * max(3, 66 - len(label)))

        if only_thoughts:
            for t in msg.thoughts:
                out.append(t.strip())
            out.append("")
            continue

        if msg.has_thoughts and opts.thoughts == THOUGHTS_INCLUDE:
            out.append(f"[{tr('core_thoughts_tag')}]")
            for t in msg.thoughts:
                out.append(t.strip())
            out.append(f"[/{tr('core_thoughts_tag')}]")
            out.append("")
        if msg.has_thoughts and opts.thoughts == THOUGHTS_SEPARATE:
            head = f"=== {label} ==="
            thoughts_out.append(head)
            for t in msg.thoughts:
                thoughts_out.append(t.strip())
            thoughts_out.append("")

        if opts.attachments and msg.attachments:
            out.extend(_attachment_lines(msg))

        text = msg.text.strip()
        if text:
            out.append(text)
        elif not msg.attachments and not msg.has_thoughts:
            out.append(f"[{tr('empty_message_plain')}]")
        out.append("")

    main = "\n".join(out).rstrip() + "\n"
    sep = None
    if (not only_thoughts and opts.thoughts == THOUGHTS_SEPARATE
            and thoughts_out):
        head = f"{tr('core_thoughts_upper')} — {chat.title}\n" + "=" * 70 + "\n"
        sep = head + "\n".join(thoughts_out).rstrip() + "\n"
    return main, sep


# ----------------------------------------------------------------------------
# Экспорт: Markdown
# ----------------------------------------------------------------------------

def export_md(chat: ChatLog, opts: ExportOptions):
    out: list = []
    thoughts_out: list = []
    labels = effective_labels(chat, opts)
    only_thoughts = opts.content == CONTENT_THOUGHTS

    if opts.metadata:
        out.append(f"# {chat.title}")
        meta = []
        if chat.model:
            meta.append(f"**{tr('core_model')}:** `{chat.model}`")
        meta.append("**" + tr("core_msgs_count", n=len(chat.messages),
                           u=chat.user_count, m=chat.model_count) + "**")
        out.append("  \n".join(meta))
        out.append("")

    if (opts.system_instruction and chat.system_instruction
            and opts.content == CONTENT_ALL):
        out.append(f"## {tr('system_instruction')}")
        out.append(chat.system_instruction)
        out.append("")

    for num, msg in iter_export_messages(chat, opts):
        label = _msg_label(msg, num if opts.numbering else None, opts, labels)
        out.append(f"## {label}")

        if only_thoughts:
            for t in msg.thoughts:
                out.append(t.strip())
            out.append("")
            continue

        if msg.has_thoughts and opts.thoughts == THOUGHTS_INCLUDE:
            for t in msg.thoughts:
                out.append(f"> **{tr('core_thoughts_tag')}:**")
                for ln in t.strip().split("\n"):
                    out.append(f"> {ln}")
                out.append("")
        if msg.has_thoughts and opts.thoughts == THOUGHTS_SEPARATE:
            thoughts_out.append(f"## {label}")
            for t in msg.thoughts:
                thoughts_out.append(t.strip())
            thoughts_out.append("")

        if opts.attachments and msg.attachments:
            for a in msg.attachments:
                if a.url:
                    out.append(f"*[{tr('core_attachment')}: {a.label}]({a.url})*")
                else:
                    out.append(f"*[{tr('core_attachment')}: {a.label}]*")
            out.append("")

        if msg.text.strip():
            out.append(msg.text.strip())
        out.append("")

    main = "\n".join(out).rstrip() + "\n"
    sep = None
    if (not only_thoughts and opts.thoughts == THOUGHTS_SEPARATE
            and thoughts_out):
        sep = (f"# {tr('core_model_thoughts')} — {chat.title}\n\n"
               + "\n".join(thoughts_out).rstrip() + "\n")
    return main, sep


# ----------------------------------------------------------------------------
# Экспорт: HTML
# ----------------------------------------------------------------------------

_HTML_CSS = """
:root {
  --bg: #f4f5f7; --card: #ffffff; --text: #1c1e21; --muted: #65676b;
  --user: #1a73e8; --model: #188038; --thought: #b06000;
  --user-bg: #e8f0fe; --model-bg: #ffffff; --thought-bg: #fef7e0;
  --code-bg: #f0f2f5; --border: #d8dadf;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #18191a; --card: #242526; --text: #e4e6eb; --muted: #b0b3b8;
    --user: #8ab4f8; --model: #81c995; --thought: #fdd663;
    --user-bg: #1f2b3e; --model-bg: #242526; --thought-bg: #332b14;
    --code-bg: #1b1c1d; --border: #3e4042;
  }
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--text); margin: 0;
  font: 15px/1.55 "Segoe UI", Roboto, Arial, sans-serif; }
.wrap { max-width: 880px; margin: 0 auto; padding: 24px 16px 64px; }
h1.title { font-size: 22px; margin: 0 0 4px; }
.meta { color: var(--muted); font-size: 13px; margin-bottom: 20px; }
.sysinstr { background: var(--card); border: 1px dashed var(--border);
  border-radius: 10px; padding: 12px 16px; margin-bottom: 20px; }
.sysinstr .hdr { font-weight: 600; color: var(--muted); font-size: 12px;
  text-transform: uppercase; letter-spacing: .5px; margin-bottom: 6px; }
.msg { background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 14px 18px; margin-bottom: 14px; }
.msg.user { background: var(--user-bg); }
.msg .hdr { display: flex; gap: 10px; align-items: baseline;
  font-size: 12.5px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .5px; margin-bottom: 8px; }
.msg.user .hdr .who { color: var(--user); }
.msg.model .hdr .who { color: var(--model); }
.msg .hdr .time { color: var(--muted); font-weight: 400; text-transform: none; }
.body { overflow-wrap: anywhere; white-space: pre-wrap; }
.body.md { white-space: normal; }
.body.md p { margin: 0 0 10px; }
.body.md pre { background: var(--code-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px; overflow-x: auto; white-space: pre; }
.body.md code { background: var(--code-bg); border-radius: 4px;
  padding: 1px 5px; font-family: Consolas, "Courier New", monospace; font-size: 13.5px; }
.body.md pre code { background: none; padding: 0; }
.body.md blockquote { border-left: 3px solid var(--border); margin: 8px 0;
  padding: 4px 12px; color: var(--muted); }
.body.md h3, .body.md h4, .body.md h5, .body.md h6 { margin: 14px 0 8px; }
.body.md hr { border: none; border-top: 1px solid var(--border); margin: 14px 0; }
details.thought { background: var(--thought-bg); border: 1px solid var(--border);
  border-radius: 8px; margin: 0 0 10px; padding: 8px 12px; }
details.thought summary { cursor: pointer; color: var(--thought);
  font-weight: 600; font-size: 13px; }
details.thought .body { margin-top: 8px; font-size: 14px; }
.att { display: inline-block; background: var(--code-bg);
  border: 1px solid var(--border); border-radius: 16px; padding: 3px 12px;
  font-size: 13px; margin: 0 6px 8px 0; }
.att a { color: var(--user); text-decoration: none; }
.empty { color: var(--muted); font-style: italic; }
"""


def _body_html(text: str, opts: ExportOptions) -> str:
    if opts.render_markdown:
        return f'<div class="body md">{markdown_to_html(text)}</div>'
    return f'<div class="body">{_html.escape(text)}</div>'


def export_html(chat: ChatLog, opts: ExportOptions):
    out: list = []
    thoughts_out: list = []
    labels = effective_labels(chat, opts)
    only_thoughts = opts.content == CONTENT_THOUGHTS

    out.append("<!DOCTYPE html>")
    out.append('<html lang="ru"><head><meta charset="utf-8">')
    out.append(f"<title>{_html.escape(chat.title)}</title>")
    out.append(f"<style>{_HTML_CSS}</style></head><body><div class='wrap'>")

    if opts.metadata:
        out.append(f"<h1 class='title'>{_html.escape(chat.title)}</h1>")
        meta = []
        if chat.model:
            meta.append(f"{tr('core_model')}: <b>{_html.escape(chat.model)}</b>")
        rs = chat.run_settings
        if "temperature" in rs:
            meta.append(f"temperature={rs['temperature']}")
        meta.append(_html.escape(tr("core_msgs_count", n=len(chat.messages),
                                 u=chat.user_count, m=chat.model_count)))
        out.append(f"<div class='meta'>{' &middot; '.join(meta)}</div>")

    if (opts.system_instruction and chat.system_instruction
            and opts.content == CONTENT_ALL):
        out.append(f"<div class='sysinstr'><div class='hdr'>"
                   f"{_html.escape(tr('system_instruction'))}</div>")
        out.append(_body_html(chat.system_instruction, opts))
        out.append("</div>")

    user_l, model_l = labels
    for num, msg in iter_export_messages(chat, opts):
        cls = "user" if msg.is_user else "model"
        who = user_l if msg.is_user else model_l
        if msg.role not in ("user", "model"):
            who = msg.role
        hdr = []
        if opts.numbering:
            hdr.append(f"<span class='who'>#{num} {_html.escape(who)}</span>")
        else:
            hdr.append(f"<span class='who'>{_html.escape(who)}</span>")
        if opts.timestamps and msg.time_str():
            hdr.append(f"<span class='time'>{_html.escape(msg.time_str())}</span>")

        out.append(f"<div class='msg {cls}'><div class='hdr'>{''.join(hdr)}</div>")

        if only_thoughts:
            for t in msg.thoughts:
                out.append(_body_html(t.strip(), opts))
            out.append("</div>")
            continue

        if msg.has_thoughts and opts.thoughts == THOUGHTS_INCLUDE:
            out.append(f"<details class='thought'><summary>"
                       f"{_html.escape(tr('core_model_thoughts'))}</summary>")
            for t in msg.thoughts:
                out.append(_body_html(t.strip(), opts))
            out.append("</details>")
        if msg.has_thoughts and opts.thoughts == THOUGHTS_SEPARATE:
            label = _msg_label(msg, num if opts.numbering else None, opts, labels)
            thoughts_out.append(f"<div class='msg model'><div class='hdr'>"
                                f"<span class='who'>{_html.escape(label)}</span></div>")
            for t in msg.thoughts:
                thoughts_out.append(_body_html(t.strip(), opts))
            thoughts_out.append("</div>")

        if opts.attachments and msg.attachments:
            for a in msg.attachments:
                if a.url:
                    out.append(
                        f"<span class='att'>📎 "
                        f"<a href='{_html.escape(a.url, quote=True)}' "
                        f"target='_blank'>{_html.escape(a.label)}</a></span>")
                else:
                    out.append(f"<span class='att'>📎 "
                               f"{_html.escape(a.label)}</span>")

        if msg.text.strip():
            out.append(_body_html(msg.text.strip(), opts))
        elif not msg.attachments and not msg.has_thoughts:
            out.append(f"<div class='empty'>[{_html.escape(tr('empty_message_plain'))}]</div>")

        out.append("</div>")

    out.append("</div></body></html>")
    main = "\n".join(out)

    sep = None
    if (not only_thoughts and opts.thoughts == THOUGHTS_SEPARATE
            and thoughts_out):
        sep = ("<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>"
               f"<title>{_html.escape(tr('core_thoughts_sep_title', title=chat.title))}</title>"
               f"<style>{_HTML_CSS}</style></head><body><div class='wrap'>"
               f"<h1 class='title'>{_html.escape(tr('core_model_thoughts'))} — {_html.escape(chat.title)}</h1>"
               + "\n".join(thoughts_out) + "</div></body></html>")
    return main, sep


# ----------------------------------------------------------------------------
# Экспорт: JSON / JSONL (чистая структура без служебного мусора)
# ----------------------------------------------------------------------------

def _message_to_dict(num: int, msg: Message, opts: ExportOptions) -> dict:
    d: dict = {"index": num, "role": msg.role}
    if msg.text.strip():
        d["text"] = msg.text.strip()
    if msg.has_thoughts and opts.thoughts != THOUGHTS_EXCLUDE:
        d["thoughts"] = [t.strip() for t in msg.thoughts]
    if opts.attachments and msg.attachments:
        d["attachments"] = [
            {"kind": a.kind, "label": a.label,
             **({"id": a.drive_id} if a.drive_id else {}),
             **({"url": a.url} if a.url else {})}
            for a in msg.attachments
        ]
    if opts.timestamps and msg.create_time:
        d["time"] = msg.create_time
    if msg.token_count:
        d["tokens"] = msg.token_count
    if msg.finish_reason:
        d["finish_reason"] = msg.finish_reason
    return d


def _json_doc(chat: ChatLog, opts: ExportOptions) -> dict:
    doc: dict = {"title": chat.title}
    if opts.metadata:
        if chat.model:
            doc["model"] = chat.model
        if chat.path:
            doc["source_file"] = chat.path
        rs = chat.run_settings
        settings = {k: rs[k] for k in
                    ("temperature", "topP", "topK", "maxOutputTokens")
                    if k in rs}
        if settings:
            doc["settings"] = settings
        doc["stats"] = {
            "messages": len(chat.messages),
            "prompts": chat.user_count,
            "answers": chat.model_count,
            "thoughts": chat.thought_count,
        }
    if (opts.system_instruction and chat.system_instruction
            and opts.content == CONTENT_ALL):
        doc["system_instruction"] = chat.system_instruction

    msgs = []
    for num, msg in iter_export_messages(chat, opts):
        if opts.content == CONTENT_THOUGHTS:
            msgs.append({"index": num, "role": msg.role,
                         "thoughts": [t.strip() for t in msg.thoughts]})
        else:
            msgs.append(_message_to_dict(num, msg, opts))
    doc["messages"] = msgs
    return doc


def export_json(chat: ChatLog, opts: ExportOptions):
    """Чистый JSON: метаданные + messages[]. Размышления — по настройке.

    При thoughts=separate основной файл идёт без размышлений, а вторым
    документом возвращается JSON только с размышлениями.
    """
    sep_doc = None
    if opts.content != CONTENT_THOUGHTS and opts.thoughts == THOUGHTS_SEPARATE:
        main_opts = ExportOptions(**{**opts.__dict__,
                                     "thoughts": THOUGHTS_EXCLUDE})
        doc = _json_doc(chat, main_opts)
        th_msgs = [{"index": n, "role": m.role,
                    "thoughts": [t.strip() for t in m.thoughts]}
                   for n, m in iter_export_messages(chat, opts)
                   if m.has_thoughts]
        if th_msgs:
            sep_doc = json.dumps({"title": chat.title,
                                  "kind": "thoughts",
                                  "messages": th_msgs},
                                 ensure_ascii=False, indent=2) + "\n"
    else:
        doc = _json_doc(chat, opts)
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n", sep_doc


def export_jsonl(chat: ChatLog, opts: ExportOptions):
    """JSONL: одна строка — одно сообщение. Удобно для скриптов/пайплайнов."""
    lines = []
    for num, msg in iter_export_messages(chat, opts):
        if opts.content == CONTENT_THOUGHTS:
            d = {"index": num, "role": msg.role,
                 "thoughts": [t.strip() for t in msg.thoughts]}
        else:
            d = _message_to_dict(num, msg, opts)
        if opts.metadata:
            d["chat"] = chat.title
            if chat.model:
                d["model"] = chat.model
        lines.append(json.dumps(d, ensure_ascii=False))
    return "\n".join(lines) + "\n", None


# ----------------------------------------------------------------------------
# Универсальный экспорт и копирование
# ----------------------------------------------------------------------------

_EXPORTERS = {"txt": export_txt, "html": export_html, "md": export_md,
              "json": export_json, "jsonl": export_jsonl}
EXT = {"txt": ".txt", "html": ".html", "md": ".md",
       "json": ".json", "jsonl": ".jsonl"}


def export_chat(chat: ChatLog, opts: ExportOptions):
    """Возвращает (основной_документ, документ_размышлений_или_None)."""
    fn = _EXPORTERS.get(opts.fmt)
    if fn is None:
        raise ValueError(tr("core_err_unknown_fmt", fmt=opts.fmt))
    return fn(chat, opts)


_CONTENT_SUFFIX = {
    CONTENT_PROMPTS: "_prompts",
    CONTENT_ANSWERS: "_answers",
    CONTENT_THOUGHTS: "_thoughts_only",
}


def export_to_files(chat: ChatLog, opts: ExportOptions, out_dir, base_name=None):
    """Пишет файлы на диск, возвращает список созданных путей."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_name or (Path(chat.path).stem if chat.path else chat.title) or "chat"
    base += _CONTENT_SUFFIX.get(opts.content, "")
    main, sep = export_chat(chat, opts)
    ext = EXT[opts.fmt]
    created = []
    main_path = out_dir / f"{base}{ext}"
    main_path.write_text(main, encoding="utf-8")
    created.append(str(main_path))
    if sep:
        sep_path = out_dir / f"{base}_thoughts{ext}"
        sep_path.write_text(sep, encoding="utf-8")
        created.append(str(sep_path))
    return created


COPY_ALL = "all"
COPY_PROMPTS = "prompts"
COPY_ANSWERS = "answers"
COPY_THOUGHTS = "thoughts"


def chat_to_clipboard_text(chat: ChatLog, which: str = COPY_ALL,
                           opts: Optional[ExportOptions] = None) -> str:
    """Текст для копирования: весь чат / промты / ответы / размышления."""
    opts = opts or ExportOptions(fmt="txt", metadata=False,
                                 system_instruction=False)
    if which == COPY_ALL:
        o = ExportOptions(**{**opts.__dict__, "fmt": "txt",
                             "content": CONTENT_ALL})
        return export_txt(chat, o)[0]

    labels = effective_labels(chat, opts)
    out = []
    for num, msg in enumerate(chat.messages, 1):
        if which == COPY_PROMPTS and not msg.is_user:
            continue
        if which == COPY_ANSWERS and msg.is_user:
            continue
        if which == COPY_THOUGHTS and not msg.has_thoughts:
            continue
        chunk = []
        if opts.numbering:
            label = _msg_label(msg, num, opts, labels)
            chunk.append(f"--- {label} ---")
        if which == COPY_THOUGHTS:
            chunk.extend(t.strip() for t in msg.thoughts)
            out.append("\n".join(chunk))
            continue
        if msg.has_thoughts and opts.thoughts == THOUGHTS_INCLUDE:
            chunk.append(f"[{tr('core_thoughts_tag')}]")
            chunk.extend(t.strip() for t in msg.thoughts)
            chunk.append(f"[/{tr('core_thoughts_tag')}]")
        if opts.attachments and msg.attachments:
            chunk.extend(_attachment_lines(msg))
        if msg.text.strip():
            chunk.append(msg.text.strip())
        if len(chunk) > (1 if opts.numbering else 0):
            out.append("\n".join(chunk))
    return "\n\n".join(out).strip() + ("\n" if out else "")


def message_copy_text(msg: Message, include_thoughts: bool = False,
                      thoughts_only: bool = False) -> str:
    """Текст одного сообщения для кнопок «Копировать»."""
    if thoughts_only:
        return "\n\n".join(t.strip() for t in msg.thoughts)
    parts = []
    if include_thoughts and msg.has_thoughts:
        parts.append(f"[{tr('core_thoughts_tag')}]")
        parts.extend(t.strip() for t in msg.thoughts)
        parts.append(f"[/{tr('core_thoughts_tag')}]")
    for ln in _attachment_lines(msg):
        parts.append(ln)
    if msg.text.strip():
        parts.append(msg.text.strip())
    return "\n".join(parts)
