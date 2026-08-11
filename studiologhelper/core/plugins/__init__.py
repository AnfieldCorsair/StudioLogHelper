# -*- coding: utf-8 -*-
"""Plugin система для парсеров с поддержкой Safe Mode, проверкой целостности и логированием."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Protocol, Set

from ..models import ChatLog
from ...utils.logger import get_logger

logger = get_logger()

# Флаг безопасного режима (Safe Mode) — отключает сторонние пользовательские плагины
_SAFE_MODE = os.environ.get("SLH_SAFE_MODE", "0").lower() in ("1", "true", "yes")


def set_safe_mode(enabled: bool):
    global _SAFE_MODE
    _SAFE_MODE = enabled
    logger.info("Plugin Safe Mode: %s", "ENABLED (third-party plugins blocked)" if enabled else "DISABLED")


def is_safe_mode() -> bool:
    return _SAFE_MODE


def compute_file_sha256(path: Path) -> str:
    try:
        data = path.read_bytes()
        return hashlib.sha256(data).hexdigest()
    except Exception:
        return "unknown"


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
        self.loaded_plugin_files: List[dict] = []

    def register(self, plugin: ParserPlugin, source_path: Optional[Path] = None):
        if plugin not in self.plugins:
            self.plugins.append(plugin)
            src_info = f" from {source_path}" if source_path else " (builtin)"
            logger.info(f"Plugin registered: {plugin.name} - {plugin.description}{src_info}")

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
        """Загружает *.py из директории как сторонние плагины (блокируется в Safe Mode)."""
        if is_safe_mode():
            logger.info("Skipping user plugin directory (Safe Mode active): %s", plugin_dir)
            return

        plugin_dir = Path(plugin_dir)
        if not plugin_dir.exists():
            return

        for py_file in plugin_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            file_hash = compute_file_sha256(py_file)
            logger.warning(
                "SECURITY: Loading third-party user plugin '%s' [SHA256: %s] with current user privileges",
                py_file,
                file_hash,
            )

            try:
                spec = importlib.util.spec_from_file_location(f"slh_plugin_{py_file.stem}", py_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = mod
                    spec.loader.exec_module(mod)  # type: ignore

                    loaded_any = False
                    if hasattr(mod, "get_plugin"):
                        plugin = mod.get_plugin()
                        self.register(plugin, source_path=py_file)
                        loaded_any = True
                    elif hasattr(mod, "PLUGIN"):
                        self.register(mod.PLUGIN, source_path=py_file)
                        loaded_any = True
                    else:
                        for attr in dir(mod):
                            obj = getattr(mod, attr)
                            if hasattr(obj, "can_parse") and hasattr(obj, "parse") and hasattr(obj, "name"):
                                try:
                                    instance = obj() if isinstance(obj, type) else obj
                                    self.register(instance, source_path=py_file)
                                    loaded_any = True
                                except Exception:
                                    pass

                    if loaded_any:
                        self.loaded_plugin_files.append({
                            "path": str(py_file),
                            "name": py_file.name,
                            "sha256": file_hash,
                        })
            except Exception as e:
                logger.error(f"Failed to load plugin {py_file}: {e}")

    def load_builtin(self):
        """Загружает встроенные доверенные плагины."""
        from . import builtin_json, builtin_text, claude_plugin, chatgpt_plugin

        for mod in [builtin_json, builtin_text, claude_plugin, chatgpt_plugin]:
            try:
                if hasattr(mod, "get_plugin"):
                    self.register(mod.get_plugin())
            except Exception as e:
                logger.warning(f"Failed to load builtin plugin {mod.__name__}: {e}")


_global_registry: Optional[PluginRegistry] = None


def get_global_registry() -> PluginRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = PluginRegistry()
        _global_registry.load_builtin()
        try:
            from ...utils.paths import get_app_data_dir

            plugin_dir = get_app_data_dir() / "plugins"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            _global_registry.load_from_directory(plugin_dir)
        except Exception as e:
            logger.debug(f"Could not load user plugins: {e}")
    return _global_registry
