# -*- coding: utf-8 -*-
"""Оптимизированный Markdown -> HTML с защитой от сетевых запросов и зависаний."""

from __future__ import annotations

import html as _html
import re

# Precompile all regex once
RE_IMG = re.compile(r"!\[([^\]]*)\]\((https?://[^\s)]+)\)")
RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
RE_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
RE_CODE = re.compile(r"`([^`]+)`")
RE_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
RE_STRIKE = re.compile(r"~~(.+?)~~")
RE_H = re.compile(r"^(#{1,6})\s+(.*)$")
RE_HR = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")
RE_UL = re.compile(r"^[-*+]\s+(.*)$")
RE_OL = re.compile(r"^\d+[.)]\s+(.*)$")
RE_CODE_FENCE = re.compile(r"^\s*```")

try:
    import markdown as _md_lib

    def _safe_md_lib(text: str) -> str:
        # Заменяем ![alt](url) на безопасный бейдж до парсинга библиотекой markdown,
        # чтобы Qt не пытался скачивать изображения по сети и не блокировал интерфейс/интернет
        safe_text = RE_IMG.sub(r"📎 [\1](\2)", text)
        html_out = _md_lib.markdown(safe_text, extensions=["fenced_code", "tables", "nl2br"])
        # Дополнительно удаляем любые оставшиеся теги <img ...>
        html_out = re.sub(r'<img\s+[^>]*src=["\'][^"\']*["\'][^>]*>', r'📎 [Изображение]', html_out, flags=re.IGNORECASE)
        return html_out

    HAS_MARKDOWN_LIB = True
except ImportError:
    HAS_MARKDOWN_LIB = False
    _safe_md_lib = None  # type: ignore


def _inline_md(escaped: str) -> str:
    # Заменяем изображения на безопасные бейджи
    escaped = RE_IMG.sub(r"📎 [\1](\2)", escaped)
    escaped = RE_CODE.sub(r"<code>\1</code>", escaped)
    escaped = RE_BOLD.sub(r"<b>\1</b>", escaped)
    escaped = RE_ITALIC.sub(r"<i>\1</i>", escaped)
    escaped = RE_STRIKE.sub(r"<s>\1</s>", escaped)
    escaped = RE_LINK.sub(r'<a href="\2">\1</a>', escaped)
    return escaped


def markdown_to_html_builtin(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    in_code = False
    code_buf: list[str] = []
    code_lang = ""
    list_stack: list[str] = []

    def close_lists():
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    while i < len(lines):
        line = lines[i]

        if in_code:
            if RE_CODE_FENCE.match(line):
                cls = f' class="lang-{_html.escape(code_lang)}"' if code_lang else ""
                out.append(f"<pre{cls}><code>{_html.escape(chr(10).join(code_buf))}</code></pre>")
                in_code, code_buf, code_lang = False, [], ""
            else:
                code_buf.append(line)
            i += 1
            continue

        stripped = line.strip()

        if RE_CODE_FENCE.match(line):
            close_lists()
            in_code = True
            code_lang = stripped[3:].strip()
            i += 1
            continue

        if not stripped:
            close_lists()
            i += 1
            continue

        m = RE_H.match(stripped)
        if m:
            close_lists()
            lvl = min(len(m.group(1)) + 2, 6)
            out.append(f"<h{lvl}>{_inline_md(_html.escape(m.group(2)))}</h{lvl}>")
            i += 1
            continue

        if RE_HR.match(stripped):
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
            out.append("<blockquote>" + "<br>".join(_inline_md(_html.escape(q)) for q in quote) + "</blockquote>")
            continue

        m = RE_UL.match(stripped)
        if m:
            if not list_stack or list_stack[-1] != "ul":
                close_lists()
                out.append("<ul>")
                list_stack.append("ul")
            out.append(f"<li>{_inline_md(_html.escape(m.group(1)))}</li>")
            i += 1
            continue

        m = RE_OL.match(stripped)
        if m:
            if not list_stack or list_stack[-1] != "ol":
                close_lists()
                out.append("<ol>")
                list_stack.append("ol")
            out.append(f"<li>{_inline_md(_html.escape(m.group(1)))}</li>")
            i += 1
            continue

        # paragraph — collect consecutive non-special lines
        para = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt or nxt.startswith(("```", "#", ">", "- ", "* ", "+ ")) or RE_OL.match(nxt) or RE_HR.match(nxt):
                break
            para.append(nxt)
            i += 1
        close_lists()
        out.append("<p>" + "<br>".join(_inline_md(_html.escape(s)) for s in para) + "</p>")

    if in_code and code_buf:
        out.append(f"<pre><code>{_html.escape(chr(10).join(code_buf))}</code></pre>")
    close_lists()
    return "\n".join(out)


def markdown_to_html(text: str) -> str:
    """Main entry — uses safe markdown lib if available, otherwise fast builtin."""
    if not text:
        return ""
    if HAS_MARKDOWN_LIB and len(text) > 500:
        try:
            return _safe_md_lib(text)  # type: ignore
        except Exception:
            pass
    return markdown_to_html_builtin(text)
