# -*- coding: utf-8 -*-
from __future__ import annotations

import html as _html

from .base import CONTENT_THOUGHTS, THOUGHTS_INCLUDE, THOUGHTS_SEPARATE
from .txt import _iter_export_messages, _msg_label
from ..markdown import markdown_to_html

HTML_CSS = """
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
  padding: 1px 5px; font-family: Consolas, monospace; font-size: 13.5px; }
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


def _body_html(text: str, opts) -> str:
    if opts.render_markdown:
        return f'<div class="body md">{markdown_to_html(text)}</div>'
    return f'<div class="body">{_html.escape(text)}</div>'


class HtmlExporter:
    def export(self, chat, opts):
        out: list[str] = []
        thoughts_out: list[str] = []
        labels = opts.effective_labels(chat)
        only_thoughts = opts.content == CONTENT_THOUGHTS

        out.append("<!DOCTYPE html>")
        out.append('<html lang="en"><head><meta charset="utf-8">')
        out.append(f"<title>{_html.escape(chat.title)}</title>")
        out.append(f"<style>{HTML_CSS}</style></head><body><div class='wrap'>")

        if opts.metadata:
            out.append(f"<h1 class='title'>{_html.escape(chat.title)}</h1>")
            meta = []
            if chat.model:
                meta.append(f"Model: <b>{_html.escape(chat.model)}</b>")
            meta.append(f"Messages: {len(chat.messages)} (prompts: {chat.user_count}, answers: {chat.model_count})")
            out.append(f"<div class='meta'>{' &middot; '.join(meta)}</div>")

        if opts.system_instruction and chat.system_instruction and opts.content == "all":
            out.append(f"<div class='sysinstr'><div class='hdr'>SYSTEM INSTRUCTION</div>")
            out.append(_body_html(chat.system_instruction, opts))
            out.append("</div>")

        for num, msg in _iter_export_messages(chat, opts):
            cls = "user" if msg.is_user else "model"
            who = labels[0] if msg.is_user else labels[1]
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
                out.append(f"<details class='thought'><summary>Model thoughts</summary>")
                for t in msg.thoughts:
                    out.append(_body_html(t.strip(), opts))
                out.append("</details>")
            if msg.has_thoughts and opts.thoughts == THOUGHTS_SEPARATE:
                label = _msg_label(msg, num if opts.numbering else None, opts, labels)
                thoughts_out.append(f"<div class='msg model'><div class='hdr'><span class='who'>{_html.escape(label)}</span></div>")
                for t in msg.thoughts:
                    thoughts_out.append(_body_html(t.strip(), opts))
                thoughts_out.append("</div>")

            if opts.attachments and msg.attachments:
                for a in msg.attachments:
                    if a.url:
                        out.append(f"<span class='att'>📎 <a href='{_html.escape(a.url, quote=True)}' target='_blank'>{_html.escape(a.label_key)}</a></span>")
                    else:
                        out.append(f"<span class='att'>📎 {_html.escape(a.label_key)}</span>")

            if msg.text.strip():
                out.append(_body_html(msg.text.strip(), opts))
            elif not msg.attachments and not msg.has_thoughts:
                out.append(f"<div class='empty'>[empty message]</div>")

            out.append("</div>")

        out.append("</div></body></html>")
        main = "\n".join(out)
        sep = None
        if not only_thoughts and opts.thoughts == THOUGHTS_SEPARATE and thoughts_out:
            sep = (
                "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
                f"<title>Thoughts — {_html.escape(chat.title)}</title>"
                f"<style>{HTML_CSS}</style></head><body><div class='wrap'>"
                f"<h1 class='title'>Thoughts — {_html.escape(chat.title)}</h1>"
                + "\n".join(thoughts_out) + "</div></body></html>"
            )
        return main, sep
