# -*- coding: utf-8 -*-
"""ExportService — сервисный слой для экспорта одного или множества логов с прогрессом."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PyQt6.QtCore import QObject, QSettings, Qt
from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox, QProgressDialog, QWidget

from ...core.exporters.base import ExportOptions
from ...core.exporters.manager import export_to_files
from ...core.models import ChatLog
from ...i18n.translator import Translator
from ...utils.logger import get_logger
from ..dialogs.export_dialog import ExportDialog
from ..workers.export_worker import ExportWorker

logger = get_logger()


class ExportService:
    """Сервис экспорта логов и управления воркерами экспорта."""

    @classmethod
    def export_chats(
        cls,
        parent: QWidget,
        chats: List[ChatLog],
        settings: QSettings,
        translator: Translator,
        on_success: Optional[Callable[[List[str], Path], None]] = None,
        status_cb: Optional[Callable[[str], None]] = None,
    ):
        if not chats:
            QMessageBox.information(parent, "StudioLogHelper", translator.tr("list_empty"))
            return

        dlg = ExportDialog(parent, settings, translator.tr, batch_count=len(chats))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dlg.options()

        last_dir = settings.value("ui/export_dir", settings.value("ui/last_dir", str(Path.home())))
        out_dir_str = QFileDialog.getExistingDirectory(parent, translator.tr("dlg_save_dir"), last_dir)
        if not out_dir_str:
            return
        out_dir = Path(out_dir_str)
        settings.setValue("ui/export_dir", str(out_dir))

        # Если файлов много — запускаем асинхронный воркер в потоке
        if len(chats) > 5:
            prog = QProgressDialog(translator.tr("export_done"), translator.tr("cancel"), 0, len(chats), parent)
            prog.setWindowModality(Qt.WindowModality.WindowModal)
            prog.setMinimumDuration(200)

            worker = ExportWorker(chats, opts, out_dir)
            created_all: List[str] = []
            errors: List[str] = []

            def on_prog(done, total, title):
                prog.setMaximum(total)
                prog.setValue(done)
                prog.setLabelText(f"Exporting {title}")

            def on_file_done(title, paths):
                created_all.extend(paths)

            def on_err(title, err):
                errors.append(f"{title}: {err}")

            def on_all_done(created, errs):
                prog.setValue(len(chats))
                prog.close()
                msg = translator.tr("export_result", n=len(created_all), dir=str(out_dir))
                if errs or errors:
                    msg += "\n\n" + translator.tr("export_errors") + "\n" + "\n".join((errs + errors)[:10])
                QMessageBox.information(parent, translator.tr("export_done"), msg)
                if status_cb:
                    status_cb(translator.tr("exported_n", n=len(created_all)))
                if on_success:
                    on_success(created_all, out_dir)

            prog.canceled.connect(worker.abort)
            worker.progress.connect(on_prog)
            worker.fileDone.connect(on_file_done)
            worker.error.connect(on_err)
            worker.allDone.connect(on_all_done)
            worker.start()
            # keep reference on parent
            setattr(parent, "_active_export_worker", worker)
        else:
            created: List[str] = []
            errors: List[str] = []
            for chat in chats:
                try:
                    created.extend(export_to_files(chat, opts, out_dir))
                except Exception as ex:
                    errors.append(f"{chat.title}: {ex}")
                    logger.warning("Export failed for %s: %s", chat.title, ex)

            msg = translator.tr("export_result", n=len(created), dir=str(out_dir))
            if errors:
                msg += "\n\n" + translator.tr("export_errors") + "\n" + "\n".join(errors[:10])
            QMessageBox.information(parent, translator.tr("export_done"), msg)
            if status_cb:
                status_cb(translator.tr("exported_n", n=len(created)))
            if on_success:
                on_success(created, out_dir)
