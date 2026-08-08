# -*- coding: utf-8 -*-
from __future__ import annotations

import json

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QPushButton,
    QComboBox, QCheckBox, QLineEdit, QDialogButtonBox, QLabel, QInputDialog
)

from ...core.exporters.base import ExportOptions, THOUGHTS_EXCLUDE, THOUGHTS_INCLUDE, THOUGHTS_SEPARATE, CONTENT_ALL, CONTENT_PROMPTS, CONTENT_ANSWERS, CONTENT_THOUGHTS


class ExportDialog(QDialog):
    def __init__(self, parent, settings, tr_func, batch_count: int = 1):
        super().__init__(parent)
        self._tr = tr_func
        self.setWindowTitle(self._tr("exp_title"))
        self.setMinimumWidth(460)
        self._s = settings

        lay = QVBoxLayout(self)

        prof_row = QHBoxLayout()
        prof_row.addWidget(QLabel(self._tr("export_profiles")))
        self.cmb_profile = QComboBox()
        self.cmb_profile.addItem(self._tr("profile_none"), None)
        self.cmb_profile.addItem(self._tr("profile_answers_txt"), {"fmt": "txt", "content": CONTENT_ANSWERS, "thoughts": THOUGHTS_EXCLUDE})
        self.cmb_profile.addItem(self._tr("profile_full_txt"), {"fmt": "txt", "content": CONTENT_ALL, "thoughts": THOUGHTS_EXCLUDE})
        self.cmb_profile.addItem(self._tr("profile_full_md"), {"fmt": "md", "content": CONTENT_ALL, "thoughts": THOUGHTS_EXCLUDE})
        self.cmb_profile.addItem(self._tr("profile_prompts_txt"), {"fmt": "txt", "content": CONTENT_PROMPTS, "thoughts": THOUGHTS_EXCLUDE})
        try:
            for name, data in json.loads(self._s.value("exp/profiles", "{}")).items():
                if isinstance(data, dict):
                    self.cmb_profile.addItem(name, data)
        except Exception:
            pass
        b_save_profile = QPushButton(self._tr("profile_save"))
        b_save_profile.clicked.connect(self._save_profile_from_current)
        prof_row.addWidget(self.cmb_profile, 1)
        prof_row.addWidget(b_save_profile)
        lay.addLayout(prof_row)

        gb_fmt = QGroupBox(self._tr("exp_format"))
        f = QFormLayout(gb_fmt)
        self.cmb_fmt = QComboBox()
        self.cmb_fmt.addItem(self._tr("exp_fmt_txt"), "txt")
        self.cmb_fmt.addItem(self._tr("exp_fmt_html"), "html")
        self.cmb_fmt.addItem(self._tr("exp_fmt_md"), "md")
        self.cmb_fmt.addItem(self._tr("exp_fmt_json"), "json")
        self.cmb_fmt.addItem(self._tr("exp_fmt_jsonl"), "jsonl")
        f.addRow(self._tr("exp_format_file"), self.cmb_fmt)
        self.cmb_content = QComboBox()
        self.cmb_content.addItem(self._tr("exp_content_all"), CONTENT_ALL)
        self.cmb_content.addItem(self._tr("exp_content_prompts"), CONTENT_PROMPTS)
        self.cmb_content.addItem(self._tr("exp_content_answers"), CONTENT_ANSWERS)
        self.cmb_content.addItem(self._tr("exp_content_thoughts"), CONTENT_THOUGHTS)
        f.addRow(self._tr("exp_content_what"), self.cmb_content)
        lay.addWidget(gb_fmt)

        gb_opt = QGroupBox(self._tr("exp_content"))
        v = QVBoxLayout(gb_opt)
        self.chk_num = QCheckBox(self._tr("exp_numbering"))
        self.chk_time = QCheckBox(self._tr("exp_timestamps"))
        self.chk_meta = QCheckBox(self._tr("exp_metadata"))
        self.chk_sys = QCheckBox(self._tr("exp_sysinstr"))
        self.chk_att = QCheckBox(self._tr("exp_attachments"))
        self.chk_md = QCheckBox(self._tr("exp_render_md"))
        for w in (self.chk_num, self.chk_time, self.chk_meta, self.chk_sys, self.chk_att, self.chk_md):
            v.addWidget(w)
        f2 = QFormLayout()
        self.cmb_th = QComboBox()
        self.cmb_th.addItem(self._tr("exp_th_exclude"), THOUGHTS_EXCLUDE)
        self.cmb_th.addItem(self._tr("exp_th_include"), THOUGHTS_INCLUDE)
        self.cmb_th.addItem(self._tr("exp_th_separate"), THOUGHTS_SEPARATE)
        f2.addRow(self._tr("exp_thoughts"), self.cmb_th)
        v.addLayout(f2)
        lay.addWidget(gb_opt)

        gb_lbl = QGroupBox(self._tr("exp_labels"))
        vl = QVBoxLayout(gb_lbl)
        self.chk_auto_model = QCheckBox(self._tr("exp_auto_model"))
        vl.addWidget(self.chk_auto_model)
        fl = QFormLayout()
        self.ed_user = QLineEdit()
        self.ed_model = QLineEdit()
        fl.addRow(self._tr("exp_label_user"), self.ed_user)
        fl.addRow(self._tr("exp_label_model"), self.ed_model)
        vl.addLayout(fl)
        self.chk_auto_model.toggled.connect(lambda on: self.ed_model.setEnabled(not on))
        lay.addWidget(gb_lbl)

        if batch_count > 1:
            note = QLabel(self._tr("exp_batch_note", n=batch_count))
            note.setObjectName("muted")
            lay.addWidget(note)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(self._tr("exp_ok"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(self._tr("cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._load()
        self.cmb_profile.currentIndexChanged.connect(self._apply_profile)

    def _set_combo_data(self, cmb, value):
        i = cmb.findData(value)
        if i >= 0:
            cmb.setCurrentIndex(i)

    def _apply_profile(self):
        data = self.cmb_profile.currentData()
        if not isinstance(data, dict):
            return
        self._set_combo_data(self.cmb_fmt, data.get("fmt", "txt"))
        self._set_combo_data(self.cmb_content, data.get("content", CONTENT_ALL))
        self._set_combo_data(self.cmb_th, data.get("thoughts", THOUGHTS_EXCLUDE))
        if "numbering" in data:
            self.chk_num.setChecked(bool(data["numbering"]))
        if "timestamps" in data:
            self.chk_time.setChecked(bool(data["timestamps"]))
        if "metadata" in data:
            self.chk_meta.setChecked(bool(data["metadata"]))

    def _save_profile_from_current(self):
        name, ok = QInputDialog.getText(self, self._tr("exp_title"), self._tr("profile_name"))
        name = name.strip()
        if not ok or not name:
            return
        try:
            profiles = json.loads(self._s.value("exp/profiles", "{}"))
            if not isinstance(profiles, dict):
                profiles = {}
        except Exception:
            profiles = {}
        profiles[name] = {
            "fmt": self.cmb_fmt.currentData(),
            "content": self.cmb_content.currentData(),
            "thoughts": self.cmb_th.currentData(),
            "numbering": self.chk_num.isChecked(),
            "timestamps": self.chk_time.isChecked(),
            "metadata": self.chk_meta.isChecked(),
        }
        self._s.setValue("exp/profiles", json.dumps(profiles, ensure_ascii=False))
        self.cmb_profile.addItem(name, profiles[name])
        self.cmb_profile.setCurrentIndex(self.cmb_profile.count() - 1)
        if self.parent():
            self.parent().statusBar().showMessage(self._tr("profile_saved", name=name), 4000)

    def _load(self):
        s = self._s

        def idx(cmb, val):
            i = cmb.findData(val)
            return i if i >= 0 else 0

        self.cmb_fmt.setCurrentIndex(idx(self.cmb_fmt, s.value("exp/fmt", "txt")))
        self.cmb_content.setCurrentIndex(idx(self.cmb_content, s.value("exp/content", CONTENT_ALL)))
        self.cmb_th.setCurrentIndex(idx(self.cmb_th, s.value("exp/thoughts", THOUGHTS_EXCLUDE)))
        self.chk_num.setChecked(s.value("exp/num", "true") == "true")
        self.chk_time.setChecked(s.value("exp/time", "false") == "true")
        self.chk_meta.setChecked(s.value("exp/meta", "true") == "true")
        self.chk_sys.setChecked(s.value("exp/sys", "true") == "true")
        self.chk_att.setChecked(s.value("exp/att", "true") == "true")
        self.chk_md.setChecked(s.value("exp/md", "true") == "true")
        self.chk_auto_model.setChecked(s.value("exp/auto_model", "true") == "true")
        self.ed_user.setText(s.value("exp/user_label", self._tr("user")))
        self.ed_model.setText(s.value("exp/model_label", self._tr("model")))
        self.ed_model.setEnabled(not self.chk_auto_model.isChecked())

    def options(self) -> ExportOptions:
        s = self._s
        opts = ExportOptions(
            fmt=self.cmb_fmt.currentData(),
            content=self.cmb_content.currentData(),
            numbering=self.chk_num.isChecked(),
            thoughts=self.cmb_th.currentData(),
            timestamps=self.chk_time.isChecked(),
            metadata=self.chk_meta.isChecked(),
            attachments=self.chk_att.isChecked(),
            system_instruction=self.chk_sys.isChecked(),
            render_markdown=self.chk_md.isChecked(),
            user_label=self.ed_user.text().strip() or self._tr("user"),
            model_label=self.ed_model.text().strip() or self._tr("model"),
            auto_model_label=self.chk_auto_model.isChecked(),
        )
        s.setValue("exp/fmt", opts.fmt)
        s.setValue("exp/content", opts.content)
        s.setValue("exp/thoughts", opts.thoughts)
        s.setValue("exp/num", "true" if opts.numbering else "false")
        s.setValue("exp/time", "true" if opts.timestamps else "false")
        s.setValue("exp/meta", "true" if opts.metadata else "false")
        s.setValue("exp/sys", "true" if opts.system_instruction else "false")
        s.setValue("exp/att", "true" if opts.attachments else "false")
        s.setValue("exp/md", "true" if opts.render_markdown else "false")
        s.setValue("exp/auto_model", "true" if opts.auto_model_label else "false")
        s.setValue("exp/user_label", opts.user_label)
        s.setValue("exp/model_label", opts.model_label)
        return opts
