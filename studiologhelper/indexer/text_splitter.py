# -*- coding: utf-8 -*-
import re

BLOCK_TARGET = 1500


def split_text_blocks(text: str, target: int = BLOCK_TARGET) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text)
    blocks: list[str] = []
    buf: list[str] = []
    size = 0
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        while len(p) > target * 2:
            blocks.append(p[: target * 2])
            p = p[target * 2 :]
        if size + len(p) > target and buf:
            blocks.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(p)
        size += len(p)
    if buf:
        blocks.append("\n\n".join(buf))
    return blocks
