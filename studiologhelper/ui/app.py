# -*- coding: utf-8 -*-
"""Entry point PyQt6"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from .main_window import MainWindow
from .widgets.message_card import load_icon
from ..core.scanner import scan_folder


def main():
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

    args = [a for a in sys.argv[1:] if Path(a).exists()]
    files = []
    for a in args:
        p = Path(a)
        files.extend(scan_folder(p) if p.is_dir() else [str(p)])
    if files:
        win.load_paths(files)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
