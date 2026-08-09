# -*- coding: utf-8 -*-
"""Простой Undo для категорий/тегов/заметок — Command pattern."""

from __future__ import annotations

from typing import Callable, Any
from dataclasses import dataclass, field

from ..utils.logger import get_logger

logger = get_logger()


@dataclass
class Command:
    name: str
    do_func: Callable[[], None]
    undo_func: Callable[[], None]
    data: Any = None


class UndoManager:
    def __init__(self, max_history: int = 50):
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self.max_history = max_history

    def execute(self, cmd: Command):
        try:
            cmd.do_func()
            self._undo_stack.append(cmd)
            self._redo_stack.clear()
            if len(self._undo_stack) > self.max_history:
                self._undo_stack.pop(0)
            logger.debug(f"Executed: {cmd.name}")
        except Exception as e:
            logger.error(f"Failed to execute {cmd.name}: {e}")

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def undo(self):
        if not self.can_undo():
            return None
        cmd = self._undo_stack.pop()
        try:
            cmd.undo_func()
            self._redo_stack.append(cmd)
            logger.debug(f"Undone: {cmd.name}")
            return cmd
        except Exception as e:
            logger.error(f"Failed to undo {cmd.name}: {e}")
            return None

    def redo(self):
        if not self.can_redo():
            return None
        cmd = self._redo_stack.pop()
        try:
            cmd.do_func()
            self._undo_stack.append(cmd)
            logger.debug(f"Redone: {cmd.name}")
            return cmd
        except Exception as e:
            logger.error(f"Failed to redo {cmd.name}: {e}")
            return None

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
