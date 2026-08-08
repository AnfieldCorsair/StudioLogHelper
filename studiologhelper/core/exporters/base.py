# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field

THOUGHTS_EXCLUDE = "exclude"
THOUGHTS_INCLUDE = "include"
THOUGHTS_SEPARATE = "separate"

CONTENT_ALL = "all"
CONTENT_PROMPTS = "prompts"
CONTENT_ANSWERS = "answers"
CONTENT_THOUGHTS = "thoughts"

EXT = {"txt": ".txt", "html": ".html", "md": ".md", "json": ".json", "jsonl": ".jsonl"}
CONTENT_SUFFIX = {
    CONTENT_PROMPTS: "_prompts",
    CONTENT_ANSWERS: "_answers",
    CONTENT_THOUGHTS: "_thoughts_only",
}


@dataclass(slots=True)
class ExportOptions:
    fmt: str = "txt"
    numbering: bool = True
    thoughts: str = THOUGHTS_EXCLUDE
    content: str = CONTENT_ALL
    timestamps: bool = False
    metadata: bool = True
    attachments: bool = True
    system_instruction: bool = True
    render_markdown: bool = True
    user_label: str = "USER"
    model_label: str = "MODEL"
    auto_model_label: bool = True

    def effective_labels(self, chat):
        user = self.user_label or "USER"
        model = self.model_label or "MODEL"
        if self.auto_model_label and getattr(chat, "model", ""):
            model = chat.model
        return user, model
