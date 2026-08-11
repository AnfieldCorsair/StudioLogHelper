# -*- coding: utf-8 -*-
"""Entry point PyQt6"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from ..core.plugins import set_safe_mode
from ..core.scanner import scan_folder
from .main_window import MainWindow
from .widgets.message_card import load_icon


def main():
    # Проверяем флаги безопасного режима до запуска GUI
    if any(arg in ("--safe-mode", "--disable-plugins") for arg in sys.argv[1:]):
        set_safe_mode(True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    ic = load_icon("app_logo.png")
    if not ic.isNull():
        app.setWindowIcon(ic)
    from .main_window import APP_NAME, ORG, BASE_FONT_PT
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG)
    f = app.font()
    f.setPointSizeF(BASE_FONT_PT)
    app.setFont(f)

    win = MainWindow()
    win.show()

    # Фильтруем аргументы путей к файлам/папкам
    raw_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    args = [a for a in raw_args if Path(a).exists()]
    files = []
    for a in args:
        p = Path(a)
        files.extend(scan_folder(p) if p.is_dir() else [str(p)])
    if files:
        win.load_paths(files)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
