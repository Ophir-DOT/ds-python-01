"""Tab 4 — Settings: render-time exclusions + profile selection."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..state import AppState
from ..widgets.dual_list import DualList

_COMING_SOON = "Not yet wired into the render pipeline — planned for a later phase."


class SettingsTab(QWidget):
    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state

        # --- exclusions ----------------------------------------------------
        self.cb_formula = QCheckBox("Exclude formula fields with an empty description.")
        self.cb_state = QCheckBox("Exclude state automations (Workflow Rules).")
        self.cb_email = QCheckBox("Exclude email notifications (Email Alerts).")
        self.cb_rules = QCheckBox("Exclude validation rules.")
        self.cb_related = QCheckBox("Exclude related lists.")
        self.cb_datetime = QCheckBox("Exclude date/time generation.")

        excl = QVBoxLayout()
        for cb in (
            self.cb_formula,
            self.cb_state,
            self.cb_email,
            self.cb_rules,
            self.cb_related,
            self.cb_datetime,
        ):
            excl.addWidget(cb)
        excl_box = QGroupBox("Report exclusions")
        excl_box.setLayout(excl)

        self.cb_formula.toggled.connect(lambda v: self._set("exclude_formula_fields_empty_desc", v))
        self.cb_state.toggled.connect(lambda v: self._set("exclude_state_automations", v))
        self.cb_email.toggled.connect(lambda v: self._set("exclude_email_alerts", v))
        self.cb_rules.toggled.connect(lambda v: self._set("exclude_validation_rules", v))
        self.cb_related.toggled.connect(lambda v: self._set("exclude_related_lists", v))
        self.cb_datetime.toggled.connect(lambda v: self._set("exclude_date_time", v))

        # --- profiles ------------------------------------------------------
        self.cb_strip_fls = QCheckBox(
            "Exclude '(Permission Set)' and '(Profile)' from the FLS labels."
        )
        self.cb_strip_fls.toggled.connect(lambda v: self._set("strip_fls_suffix", v))

        self.cb_choose = QCheckBox("I want to choose the profiles to retrieve.")
        self.cb_choose.setObjectName("settings_choose_profiles")
        self.cb_choose.toggled.connect(self._toggle_choose)

        self.profile_list = DualList("Profiles / Permission Sets", "Selected")
        self.profile_list.setObjectName("settings_profile_list")
        self.profile_list.setVisible(False)

        self.save_btn = QPushButton("Save selected profiles")
        self.save_btn.setObjectName("settings_save_profiles")
        self.save_btn.setVisible(False)
        self.save_btn.clicked.connect(self._save_profiles)

        self.saved_label = QLabel("Default: profiles/permission sets with assigned users.")

        prof = QVBoxLayout()
        prof.addWidget(self.cb_strip_fls)
        prof.addWidget(self.cb_choose)
        prof.addWidget(self.profile_list)
        prof.addWidget(self.save_btn)
        prof.addWidget(self.saved_label)
        prof_box = QGroupBox("Profiles / Permission Sets settings")
        prof_box.setLayout(prof)

        # Disabled: these options are not yet wired into the render/collect
        # pipeline. The four kept above (formula/state/email/validation) work.
        for cb in (self.cb_related, self.cb_datetime, self.cb_strip_fls, self.cb_choose):
            cb.setText(cb.text() + "   (coming soon)")
            cb.setEnabled(False)
            cb.setToolTip(_COMING_SOON)
        self.profile_list.setEnabled(False)
        self.save_btn.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(excl_box)
        layout.addWidget(prof_box)
        layout.addStretch(1)

    def on_source_connected(self) -> None:
        conn = self._state.source
        if conn:
            self.profile_list.set_items([(p.name, f"{p.label} ({p.kind})") for p in conn.profiles])

    def _set(self, attr: str, value: bool) -> None:
        setattr(self._state.settings, attr, value)

    def _toggle_choose(self, checked: bool) -> None:
        self._state.settings.choose_profiles = checked
        self.profile_list.setVisible(checked)
        self.save_btn.setVisible(checked)

    def _save_profiles(self) -> None:
        keys = tuple(self.profile_list.selected_keys())
        self._state.settings.selected_profiles = keys
        if keys:
            self.saved_label.setText(f"Selected {len(keys)}: {', '.join(keys)}")
        else:
            self.saved_label.setText("No profiles selected — will auto-detect.")
