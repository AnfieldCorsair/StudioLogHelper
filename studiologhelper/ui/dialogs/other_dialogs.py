# -*- coding: utf-8 -*-
from __future__ import annotations

import re

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QTextEdit,
    QComboBox, QDialogButtonBox, QCheckBox, QLineEdit, QSpinBox
)

from ...core.parsers.base import TextParseOptions


class TextSeparatorsDialog(QDialog):
    def __init__(self, parent, settings, tr_func):
        super().__init__(parent)
        self._tr = tr_func
        self.setWindowTitle(self._tr("sep_title"))
        self.setMinimumWidth(560)
        self._s = settings

        lay = QVBoxLayout(self)
        hint = QLabel(self._tr("sep_hint"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        form = QFormLayout()
        self.ed_user = QTextEdit()
        self.ed_user.setAcceptRichText(False)
        self.ed_user.setMinimumHeight(86)
        self.ed_model = QTextEdit()
        self.ed_model.setAcceptRichText(False)
        self.ed_model.setMinimumHeight(86)
        self.cmb_num = QComboBox()
        self.cmb_num.addItem(self._tr("sep_num_alternating"), "alternating")
        self.cmb_num.addItem(self._tr("sep_num_model"), "model")
        self.cmb_num.addItem(self._tr("sep_num_user"), "user")
        form.addRow(self._tr("sep_user_headers"), self.ed_user)
        form.addRow(self._tr("sep_model_headers"), self.ed_model)
        form.addRow(self._tr("sep_numbered_mode"), self.cmb_num)
        lay.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(self._tr("sep_save"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(self._tr("cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._load()

    def _load(self):
        self.ed_user.setPlainText(self._s.value("parse/user_headers", ""))
        self.ed_model.setPlainText(self._s.value("parse/model_headers", ""))
        mode = self._s.value("parse/numbered_mode", "model")
        i = self.cmb_num.findData(mode)
        self.cmb_num.setCurrentIndex(i if i >= 0 else 0)

    def options(self) -> TextParseOptions:
        def lines(txt):
            return [x.strip() for x in txt.splitlines() if x.strip()]

        opts = TextParseOptions(
            user_headers=lines(self.ed_user.toPlainText()),
            model_headers=lines(self.ed_model.toPlainText()),
            numbered_mode=self.cmb_num.currentData(),
        )
        self._s.setValue("parse/user_headers", "\n".join(opts.user_headers))
        self._s.setValue("parse/model_headers", "\n".join(opts.model_headers))
        self._s.setValue("parse/numbered_mode", opts.numbered_mode)
        return opts


class CopySettingsDialog(QDialog):
    def __init__(self, parent, settings, tr_func):
        super().__init__(parent)
        self._tr = tr_func
        self.setWindowTitle(self._tr("copy_settings_title"))
        self.setMinimumWidth(460)
        self._s = settings
        lay = QVBoxLayout(self)
        self.chk_service = QCheckBox(self._tr("copy_include_service"))
        self.chk_service.setChecked(self._s.value("copy/include_service", "true") == "true")
        lay.addWidget(self.chk_service)
        form = QFormLayout()
        self.cmb_sep = QComboBox()
        self.cmb_sep.addItem(self._tr("copy_sep_blank"), "blank")
        self.cmb_sep.addItem(self._tr("copy_sep_double"), "double")
        self.cmb_sep.addItem(self._tr("copy_sep_long"), "long")
        self.cmb_sep.addItem(self._tr("copy_sep_custom"), "custom")
        cur = self._s.value("copy/separator", "blank")
        i = self.cmb_sep.findData(cur)
        self.cmb_sep.setCurrentIndex(i if i >= 0 else 0)
        self.ed_custom = QLineEdit()
        self.ed_custom.setText(self._s.value("copy/custom_separator", "\\n---\\n"))
        form.addRow(self._tr("copy_separator"), self.cmb_sep)
        form.addRow(self._tr("copy_custom_separator"), self.ed_custom)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(self._tr("sep_save"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(self._tr("cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def save(self):
        self._s.setValue("copy/include_service", "true" if self.chk_service.isChecked() else "false")
        self._s.setValue("copy/separator", self.cmb_sep.currentData())
        self._s.setValue("copy/custom_separator", self.ed_custom.text())


class BatchExportDialog(QDialog):
    def __init__(self, parent, settings, selected_count: int, all_count: int, categories: set, tr_func):
        super().__init__(parent)
        self._tr = tr_func
        self.setWindowTitle(self._tr("batch_title"))
        self.setMinimumWidth(520)
        self._s = settings
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.cmb_source = QComboBox()
        self.cmb_source.addItem(self._tr("batch_selected", n=selected_count), "selected")
        self.cmb_source.addItem(self._tr("batch_all_loaded", n=all_count), "all")
        if selected_count <= 0:
            self.cmb_source.setCurrentIndex(1)
        form.addRow(self._tr("batch_source"), self.cmb_source)
        self.ed_cat = QLineEdit()
        if categories:
            self.ed_cat.setText(sorted(categories)[0])
        form.addRow(self._tr("batch_result_category"), self.ed_cat)
        self.ed_note = QLineEdit()
        form.addRow(self._tr("batch_note"), self.ed_note)
        self.ed_tags = QLineEdit()
        form.addRow(self._tr("tags_label"), self.ed_tags)
        lay.addLayout(form)
        self.chk_load = QCheckBox(self._tr("batch_load_results"))
        self.chk_load.setChecked(True)
        self.chk_index = QCheckBox(self._tr("batch_index_results"))
        self.chk_index.setChecked(True)
        lay.addWidget(self.chk_load)
        lay.addWidget(self.chk_index)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(self._tr("exp_ok"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(self._tr("cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def result_options(self):
        return {
            "source": self.cmb_source.currentData(),
            "category": self.ed_cat.text().strip(),
            "note": self.ed_note.text().strip(),
            "tags": [x.strip().lstrip("#") for x in re.split(r"[,;]", self.ed_tags.text()) if x.strip()],
            "load": self.chk_load.isChecked(),
            "index": self.chk_index.isChecked(),
        }


class CollapseSettingsDialog(QDialog):
    def __init__(self, parent, settings, tr_func):
        super().__init__(parent)
        self._tr = tr_func
        self.setWindowTitle(self._tr("collapse_settings_title"))
        self.setMinimumWidth(420)
        self._s = settings
        lay = QVBoxLayout(self)
        self.chk_auto = QCheckBox(self._tr("auto_collapse_long"))
        self.chk_auto.setChecked(self._s.value("ui/auto_collapse_long", "true") == "true")
        lay.addWidget(self.chk_auto)
        form = QFormLayout()
        self.spin_chars = QSpinBox()
        self.spin_chars.setRange(800, 50000)
        self.spin_chars.setSingleStep(500)
        try:
            val = int(self._s.value("ui/collapse_preview_chars", 5000))
        except (TypeError, ValueError):
            val = 5000
        self.spin_chars.setValue(max(800, min(50000, val)))
        form.addRow(self._tr("collapse_preview_chars"), self.spin_chars)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(self._tr("sep_save"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(self._tr("cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def save(self):
        self._s.setValue("ui/auto_collapse_long", "true" if self.chk_auto.isChecked() else "false")
        self._s.setValue("ui/collapse_preview_chars", self.spin_chars.value())
        return self.chk_auto.isChecked(), self.spin_chars.value()
