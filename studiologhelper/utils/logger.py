# -*- coding: utf-8 -*-
"""Логи через loguru + fallback на logging."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from loguru import logger as _loguru_logger
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False
    import logging

    _loguru_logger = logging.getLogger("StudioLogHelper")
    if not _loguru_logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        _loguru_logger.addHandler(h)
        _loguru_logger.setLevel(logging.INFO)

from .paths import get_app_data_dir

_configured = False


def setup_logger(app_name: str = "StudioLogHelper", level: str = "INFO", log_to_file: bool = True):
    global _configured
    if _configured:
        return _loguru_logger

    if HAS_LOGURU:
        from loguru import logger

        logger.remove()
        logger.add(sys.stderr, level=level, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>")

        if log_to_file:
            try:
                log_dir = get_app_data_dir(app_name)
                log_file = log_dir / "studio_log_helper.log"
                logger.add(str(log_file), level="DEBUG", rotation="10 MB", retention="7 days", compression="zip", format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}")
            except Exception:
                pass

        _configured = True
        return logger
    else:
        # std logging fallback already set
        _configured = True
        return _loguru_logger


def get_logger():
    if not _configured:
        return setup_logger()
    return _loguru_logger


# Удобные алиасы
logger = get_logger()
