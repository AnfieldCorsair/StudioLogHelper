# -*- coding: utf-8 -*-
"""Plugin система для парсеров — расширяемость без изменения ядра."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Protocol, Optional, List

from ..models import ChatLog
from ...utils.logger import get_logger

logger = get_logger()


class ParserPlugin(Protocol):
    name: str  # e.g. "claude"
    description: str
    extensions: List[str]  # e.g. [".json"]

    def can_parse(self, path: Path, head: str) -> bool:
        """Быстрая проверка может ли парсер обработать файл."""
        ...

    def parse(self, path: Path, text_options=None) -> ChatLog:
        ...


class PluginRegistry:
    def __init__(self):
        self.plugins: List[ParserPlugin] = []

    def register(self, plugin: ParserPlugin):
        if plugin not in self.plugins:
            self.plugins.append(plugin)
            logger.info(f"Plugin registered: {plugin.name} - {plugin.description}")

    def unregister(self, name: str):
        self.plugins = [p for p in self.plugins if getattr(p, "name", "") != name]

    def find_parser(self, path: Path, head: str) -> Optional[ParserPlugin]:
        for plugin in self.plugins:
            try:
                if plugin.can_parse(path, head):
                    return plugin
            except Exception as e:
                logger.warning(f"Plugin {getattr(plugin, 'name', 'unknown')} can_parse failed: {e}")
        return None

    def parse_with_plugin(self, path: Path, head: str, text_options=None) -> Optional[ChatLog]:
        plugin = self.find_parser(path, head)
        if not plugin:
            return None
        try:
            logger.debug(f"Parsing {path} with plugin {plugin.name}")
            return plugin.parse(path, text_options)
        except Exception as e:
            logger.error(f"Plugin {plugin.name} failed to parse {path}: {e}")
            return None

    def load_from_directory(self, plugin_dir: Path):
        """Загружает *.py из директории как плагины."""
        plugin_dir = Path(plugin_dir)
        if not plugin_dir.exists():
            return
        for py_file in plugin_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"slh_plugin_{py_file.stem}", py_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = mod
                    spec.loader.exec_module(mod)  # type: ignore
                    # Ищем класс с атрибутом PLUGIN или функцию get_plugin
                    if hasattr(mod, "get_plugin"):
                        plugin = mod.get_plugin()
                        self.register(plugin)
                    elif hasattr(mod, "PLUGIN"):
                        self.register(mod.PLUGIN)
                    else:
                        # Попытка найти класс наследующий ParserPlugin по имени
                        for attr in dir(mod):
                            obj = getattr(mod, attr)
                            if hasattr(obj, "can_parse") and hasattr(obj, "parse") and hasattr(obj, "name"):
                                try:
                                    instance = obj() if isinstance(obj, type) else obj
                                    self.register(instance)
                                except Exception:
                                    pass
            except Exception as e:
                logger.warning(f"Failed to load plugin {py_file}: {e}")

    def load_builtin(self):
        """Загружает встроенные плагины."""
        from . import builtin_json, builtin_text, claude_plugin, chatgpt_plugin

        for mod in [builtin_json, builtin_text, claude_plugin, chatgpt_plugin]:
            try:
                if hasattr(mod, "get_plugin"):
                    self.register(mod.get_plugin())
            except Exception as e:
                logger.warning(f"Failed to load builtin plugin {mod.__name__}: {e}")


# Глобальный реестр
_global_registry: Optional[PluginRegistry] = None


def get_global_registry() -> PluginRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = PluginRegistry()
        _global_registry.load_builtin()
        # Пользовательская папка плагинов: AppData/plugins
        try:
            from ...utils.paths import get_app_data_dir

            plugin_dir = get_app_data_dir() / "plugins"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            _global_registry.load_from_directory(plugin_dir)
        except Exception as e:
            logger.debug(f"Could not load user plugins: {e}")
    return _global_registry
