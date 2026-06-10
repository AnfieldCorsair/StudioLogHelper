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

# ----------------------------------------------------------------------------
# Модель данных
# ----------------------------------------------------------------------------

ATTACHMENT_KINDS = {
    "driveImage": "Изображение",
    "driveDocument": "Документ",
    "driveVideo": "Видео",
    "driveAudio": "Аудио",
    "driveFile": "Файл",
    "youtubeVideo": "YouTube-видео",
}


@dataclass
class Attachment:
    kind: str                 # ключ из JSON (driveImage и т.п.)
    drive_id: str = ""

    @property
    def label(self) -> str:
        return ATTACHMENT_KINDS.get(self.kind, "Вложение")

    @property
    def url(self) -> str:
        if not self.drive_id:
            return ""
        if self.kind == "youtubeVideo":
            return f"https://www.youtube.com/watch?v={self.drive_id}"
        return f"https://drive.google.com/file/d/{self.drive_id}/view"


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
        return sum(1 for m in self.messages if not m.is_user)

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
        raise ParseError("Корень JSON — не объект; это не похоже на лог AI Studio.")

    chat = ChatLog(path=path, raw=data)
    chat.title = Path(path).stem if path else "Без названия"

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
        raise ParseError(
            "Не найден список сообщений (chunkedPrompt.chunks). "
            "Файл не похож на лог Google AI Studio."
        )

    pending_thoughts: list = []
    pending_meta: dict = {}

    for idx, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            chat.warnings.append(f"Чанк #{idx}: не объект, пропущен.")
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
        chat.warnings.append(
            "В конце лога есть размышления без итогового ответа модели."
        )

    if not chat.messages:
        chat.warnings.append("Лог не содержит сообщений.")
    return chat


def parse_file(path) -> ChatLog:
    """Читает и парсит файл (расширение не важно — поддержки файлов без него)."""
    p = Path(path)
    raw_bytes = p.read_bytes()
    data = None
    last_err = None
    for enc in ("utf-8", "utf-8-sig", "utf-16", "cp1251"):
        try:
            data = json.loads(raw_bytes.decode(enc))
            break
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            last_err = e
    if data is None:
        raise ParseError(f"Не удалось прочитать JSON: {last_err}")
    return parse_data(data, str(p))


def looks_like_log(path) -> bool:
    """Быстрая эвристика: стоит ли пытаться парсить файл из папки."""
    p = Path(path)
    if not p.is_file():
        return False
    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".zip", ".exe",
                            ".pdf", ".mp4", ".mp3", ".docx", ".xlsx"}:
        return False
    try:
        head = p.read_bytes()[:4096].decode("utf-8", errors="ignore").lstrip()
    except OSError:
        return False
    return head.startswith("{") and (
        '"chunkedPrompt"' in head or '"runSettings"' in head or '"chunks"' in head
    )


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
    lines.append(f"  Чат: {chat.title}")
    if chat.model:
        lines.append(f"  Модель: {chat.model}")
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
        lines.append(f"  Параметры: {', '.join(extra)}")
    lines.append(f"  Сообщений: {len(chat.messages)} "
                 f"(промтов: {chat.user_count}, ответов: {chat.model_count})")
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
            out.append(f"[Вложение: {a.label}] {a.url}")
        else:
            out.append(f"[Вложение: {a.label}]")
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
        out.append("--- СИСТЕМНАЯ ИНСТРУКЦИЯ " + "-" * 44)
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
            out.append("[Размышления]")
            for t in msg.thoughts:
                out.append(t.strip())
            out.append("[/Размышления]")
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
            out.append("[пустое сообщение]")
        out.append("")

    main = "\n".join(out).rstrip() + "\n"
    sep = None
    if (not only_thoughts and opts.thoughts == THOUGHTS_SEPARATE
            and thoughts_out):
        head = f"РАЗМЫШЛЕНИЯ МОДЕЛИ — {chat.title}\n" + "=" * 70 + "\n"
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
            meta.append(f"**Модель:** `{chat.model}`")
        meta.append(f"**Сообщений:** {len(chat.messages)} "
                    f"(промтов: {chat.user_count}, ответов: {chat.model_count})")
        out.append("  \n".join(meta))
        out.append("")

    if (opts.system_instruction and chat.system_instruction
            and opts.content == CONTENT_ALL):
        out.append("## Системная инструкция")
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
                out.append("> **Размышления:**")
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
                    out.append(f"*[Вложение: {a.label}]({a.url})*")
                else:
                    out.append(f"*[Вложение: {a.label}]*")
            out.append("")

        if msg.text.strip():
            out.append(msg.text.strip())
        out.append("")

    main = "\n".join(out).rstrip() + "\n"
    sep = None
    if (not only_thoughts and opts.thoughts == THOUGHTS_SEPARATE
            and thoughts_out):
        sep = (f"# Размышления модели — {chat.title}\n\n"
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
            meta.append(f"Модель: <b>{_html.escape(chat.model)}</b>")
        rs = chat.run_settings
        if "temperature" in rs:
            meta.append(f"temperature={rs['temperature']}")
        meta.append(f"сообщений: {len(chat.messages)} "
                    f"(промтов: {chat.user_count}, ответов: {chat.model_count})")
        out.append(f"<div class='meta'>{' &middot; '.join(meta)}</div>")

    if (opts.system_instruction and chat.system_instruction
            and opts.content == CONTENT_ALL):
        out.append("<div class='sysinstr'><div class='hdr'>Системная инструкция</div>")
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
            out.append("<details class='thought'><summary>Размышления модели</summary>")
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
                    out.append(f"<span class='att'>📎 <a href='{a.url}' "
                               f"target='_blank'>{a.label}</a></span>")
                else:
                    out.append(f"<span class='att'>📎 {a.label}</span>")

        if msg.text.strip():
            out.append(_body_html(msg.text.strip(), opts))
        elif not msg.attachments and not msg.has_thoughts:
            out.append("<div class='empty'>[пустое сообщение]</div>")

        out.append("</div>")

    out.append("</div></body></html>")
    main = "\n".join(out)

    sep = None
    if (not only_thoughts and opts.thoughts == THOUGHTS_SEPARATE
            and thoughts_out):
        sep = ("<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>"
               f"<title>Размышления — {_html.escape(chat.title)}</title>"
               f"<style>{_HTML_CSS}</style></head><body><div class='wrap'>"
               f"<h1 class='title'>Размышления модели — {_html.escape(chat.title)}</h1>"
               + "\n".join(thoughts_out) + "</div></body></html>")
    return main, sep


# ----------------------------------------------------------------------------
# Универсальный экспорт и копирование
# ----------------------------------------------------------------------------

_EXPORTERS = {"txt": export_txt, "html": export_html, "md": export_md}
EXT = {"txt": ".txt", "html": ".html", "md": ".md"}


def export_chat(chat: ChatLog, opts: ExportOptions):
    """Возвращает (основной_документ, документ_размышлений_или_None)."""
    fn = _EXPORTERS.get(opts.fmt)
    if fn is None:
        raise ValueError(f"Неизвестный формат: {opts.fmt}")
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
            chunk.append("[Размышления]")
            chunk.extend(t.strip() for t in msg.thoughts)
            chunk.append("[/Размышления]")
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
        parts.append("[Размышления]")
        parts.extend(t.strip() for t in msg.thoughts)
        parts.append("[/Размышления]")
    for ln in _attachment_lines(msg):
        parts.append(ln)
    if msg.text.strip():
        parts.append(msg.text.strip())
    return "\n".join(parts)
