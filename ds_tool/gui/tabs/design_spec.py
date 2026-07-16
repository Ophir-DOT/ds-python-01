"""Tab 1 — Design Specification: pick objects + profiles, generate PDF/Excel."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...excel.export import export_workbook
from ..actions import build_demo_specs, collect_specs, render_specs
from ..selection_config import build_selection_payload, parse_selection_payload
from ..async_bridge import run_async
from ..state import AppState
from ..widgets.dual_list import DualList
from ..widgets.log_panel import LogPanel

_COMING_SOON = "Not yet available — planned for a later phase."


class DesignSpecTab(QWidget):
    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state

        self._all_objects = []  # full ObjectRef catalog from the connected org

        self.objects = DualList("Available Objects", "Selected Objects")
        self.objects.setObjectName("ds_objects")
        self.profiles = DualList("Profiles / Permission Sets", "Selected (empty = auto-detect)")
        self.profiles.setObjectName("ds_profiles")

        self.compsuite_only = QCheckBox("Show CompSuite objects only")
        self.compsuite_only.setObjectName("ds_compsuite_filter")
        self.compsuite_only.setToolTip("Filter the available list to CompSuite-related objects.")
        self.compsuite_only.toggled.connect(self._apply_object_filter)

        obj_box = QGroupBox("Objects")
        obj_layout = QVBoxLayout(obj_box)
        obj_layout.addWidget(self.compsuite_only)
        obj_layout.addWidget(self.objects)
        prof_box = QGroupBox("Profiles / Permission Sets  (leave empty to auto-detect)")
        QVBoxLayout(prof_box).addWidget(self.profiles)

        # Output dir row
        self.out_label = QLabel(str(self._state.out_dir))
        change_btn = QPushButton("Change…")
        change_btn.clicked.connect(self._choose_out_dir)
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output folder:"))
        out_row.addWidget(self.out_label, 1)
        out_row.addWidget(change_btn)

        self.show_datetime = QCheckBox("Display generated date/time")
        self.show_datetime.setChecked(False)
        self.show_datetime.setEnabled(False)  # not yet wired into the renderer
        self.show_datetime.setToolTip(_COMING_SOON)

        # Action buttons
        self.generate_btn = QPushButton("Generate Report")
        self.generate_btn.setObjectName("ds_generate")
        self.excel_btn = QPushButton("Excel Export")
        self.excel_btn.setObjectName("ds_excel")
        self.profiles_btn = QPushButton("Generate Profiles && Permission Sets")
        self.profiles_btn.setObjectName("ds_profiles_only")
        self.custom_settings_btn = QPushButton("Generate Custom Settings")
        self.custom_settings_btn.setObjectName("ds_custom_settings")
        self.custom_mdt_btn = QPushButton("Generate Custom Metadata Types")
        self.custom_mdt_btn.setObjectName("ds_custom_mdt")

        # Disabled: no backend collector implemented yet (later phase).
        for btn in (self.custom_settings_btn, self.custom_mdt_btn):
            btn.setEnabled(False)
            btn.setToolTip(_COMING_SOON)

        # Give the action buttons a comfortable click target height.
        for btn in (
            self.generate_btn,
            self.excel_btn,
            self.profiles_btn,
            self.custom_settings_btn,
            self.custom_mdt_btn,
        ):
            btn.setMinimumHeight(38)

        # Selection config — export/import the chosen objects + profiles/permission
        # sets so a selection can be saved and reused later or on another machine.
        self.import_btn = QPushButton("Import Selection…")
        self.import_btn.setObjectName("ds_import_selection")
        self.import_btn.setToolTip("Load a previously exported selection (objects + profiles/permission sets).")
        self.export_btn = QPushButton("Export Selection…")
        self.export_btn.setObjectName("ds_export_selection")
        self.export_btn.setToolTip("Save the current objects + profiles/permission sets selection to a JSON file.")
        for b in (self.import_btn, self.export_btn):
            b.setMinimumHeight(34)
        self.import_btn.clicked.connect(self._on_import_config)
        self.export_btn.clicked.connect(self._on_export_config)
        cfg_row = QHBoxLayout()
        cfg_row.addWidget(QLabel("Selection config:"))
        cfg_row.addWidget(self.import_btn)
        cfg_row.addWidget(self.export_btn)
        cfg_row.addStretch(1)

        self.generate_btn.clicked.connect(self._on_generate)
        self.excel_btn.clicked.connect(self._on_excel)
        self.profiles_btn.clicked.connect(lambda: self._on_generate(profiles_focus=True))

        btns = QGridLayout()
        btns.addWidget(self.generate_btn, 0, 0)
        btns.addWidget(self.excel_btn, 0, 1)
        btns.addWidget(self.profiles_btn, 0, 2)
        btns.addWidget(self.custom_settings_btn, 1, 0)
        btns.addWidget(self.custom_mdt_btn, 1, 1)
        btn_box = QGroupBox("Generate")
        btn_box.setLayout(btns)

        self.log = LogPanel("Output")

        # All content lives inside a scroll area so a short window scrolls instead
        # of squashing the list panes and buttons below a usable size.
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(obj_box, 2)
        layout.addWidget(prof_box, 2)
        layout.addLayout(cfg_row)
        layout.addLayout(out_row)
        layout.addWidget(self.show_datetime)
        layout.addWidget(btn_box)
        layout.addWidget(self.log, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ---- connection hook --------------------------------------------------

    def on_source_connected(self) -> None:
        conn = self._state.source
        if conn is None:
            return
        self._all_objects = list(conn.objects)
        self.objects.set_items([(o.api_name, o.label) for o in self._all_objects])
        self.profiles.set_items([(p.name, f"{p.label} ({p.kind})") for p in conn.profiles])
        n_cs = sum(1 for o in self._all_objects if "compsuite" in o.api_name.lower())
        self.log.append(
            f"Source connected — {len(self._all_objects)} objects available "
            f"({n_cs} CompSuite)."
        )

    def _apply_object_filter(self) -> None:
        """Re-filter the Available objects list per the CompSuite toggle."""
        objs = self._all_objects
        if self.compsuite_only.isChecked():
            objs = [o for o in objs if "compsuite" in o.api_name.lower()]
        self.objects.set_available_items([(o.api_name, o.label) for o in objs])

    # ---- helpers ----------------------------------------------------------

    def _require_source(self) -> bool:
        if not self._state.source_connected:
            QMessageBox.warning(self, "Not connected", "Connect a Source org first.")
            return False
        return True

    def _selected_filters(self) -> tuple[tuple[str, ...] | None, tuple[str, ...] | None]:
        keys = set(self.profiles.selected_keys())
        if not keys:
            return None, None
        conn = self._state.source
        kind = {p.name: p.kind for p in (conn.profiles if conn else [])}
        profiles = tuple(k for k in self.profiles.selected_keys() if kind.get(k) == "Profile")
        permsets = tuple(
            k for k in self.profiles.selected_keys() if kind.get(k) == "PermissionSet"
        )
        return (profiles or None, permsets or None)

    def _out_dir(self) -> Path:
        conn = self._state.source
        slug = (conn.creds.org_id or conn.creds.alias or "org") if conn else "org"
        return self._state.out_dir / slug

    def _choose_out_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Output folder", str(self._state.out_dir))
        if chosen:
            self._state.out_dir = Path(chosen)
            self.out_label.setText(chosen)

    # ---- selection config (export / import) -------------------------------

    def _on_export_config(self) -> None:
        """Write the current objects + profiles/permission-set selection to JSON."""
        objects = self.objects.selected_keys()
        profiles = self.profiles.selected_keys()
        if not objects and not profiles:
            QMessageBox.information(
                self,
                "Nothing to export",
                "Select at least one object or profile/permission set first.",
            )
            return
        default = str(self._state.out_dir / "ds-selection.json")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export selection", default, "JSON files (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        payload = build_selection_payload(objects, profiles)
        try:
            Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.log.append(
            f"Exported selection ({len(objects)} object(s), "
            f"{len(profiles)} profile/permission set(s)) → {path}"
        )

    def _on_import_config(self) -> None:
        """Load a previously exported selection and apply it to both lists."""
        if not self._require_source():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import selection", str(self._state.out_dir), "JSON files (*.json)"
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Import failed", f"Could not read file:\n{exc}")
            return
        try:
            objects, profiles = parse_selection_payload(data)
        except ValueError as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return

        # Show the full object list so items hidden by the CompSuite filter can match.
        if self.compsuite_only.isChecked():
            self.compsuite_only.setChecked(False)  # triggers _apply_object_filter

        # Import is authoritative: clear what's selected, then apply the file.
        self.objects.clear_selection()
        self.profiles.clear_selection()
        self.objects.select_keys(objects)
        self.profiles.select_keys(profiles)

        selected_objs = set(self.objects.selected_keys())
        selected_profs = set(self.profiles.selected_keys())
        missing = [k for k in objects if k not in selected_objs] + [
            k for k in profiles if k not in selected_profs
        ]
        self.log.append(
            f"Imported selection: {len(selected_objs)} object(s), "
            f"{len(selected_profs)} profile/permission set(s)."
            + (f"  Skipped (not in org): {', '.join(missing)}" if missing else "")
        )
        if missing:
            QMessageBox.warning(
                self,
                "Some entries skipped",
                "These were not found in the connected org and were skipped:\n\n"
                + "\n".join(missing),
            )

    # ---- actions ----------------------------------------------------------

    def _on_generate(self, profiles_focus: bool = False) -> None:
        if not self._require_source():
            return
        objects = self.objects.selected_keys()
        if not objects:
            QMessageBox.warning(self, "No objects", "Select at least one object.")
            return

        profiles, permsets = self._selected_filters()
        out_dir = self._out_dir()
        settings = self._state.settings
        conn = self._state.source
        demo = self._state.demo
        label = "profiles & permission sets" if profiles_focus else "report"
        self.log.append(f"Generating {label} for {len(objects)} object(s)…")

        async def _coro(progress):
            specs = (
                build_demo_specs(conn, objects)
                if demo
                else await collect_specs(conn, objects, profiles, permsets, 8, progress)
            )
            return render_specs(specs, out_dir, settings, progress, conn)

        run_async(
            self,
            _coro,
            on_progress=self.log.append,
            on_done=lambda res: self._on_generated(res, out_dir),
            on_error=self._on_error,
            sync=demo,
        )

    def _on_generated(self, result, out_dir: Path) -> None:
        written, fmt = result
        self.log.append(f"Done — wrote {len(written)} {fmt} file(s) to {out_dir}")
        self.log.set_output_dir(out_dir)

    def _on_excel(self) -> None:
        if not self._require_source():
            return
        objects = self.objects.selected_keys()
        if not objects:
            QMessageBox.warning(self, "No objects", "Select at least one object.")
            return
        profiles, permsets = self._selected_filters()
        out_dir = self._out_dir()
        conn = self._state.source
        demo = self._state.demo
        out_path = out_dir / "DesignSpec.xlsx"
        self.log.append(f"Exporting Excel for {len(objects)} object(s)…")

        async def _coro(progress):
            specs = (
                build_demo_specs(conn, objects)
                if demo
                else await collect_specs(conn, objects, profiles, permsets, 8, progress)
            )
            export_workbook(list(specs.values()), out_path)
            progress(f"Wrote {out_path.name}")
            return out_path

        run_async(
            self,
            _coro,
            on_progress=self.log.append,
            on_done=lambda _p: (self.log.append(f"Done — {out_path}"), self.log.set_output_dir(out_dir)),
            on_error=self._on_error,
            sync=demo,
        )

    def _on_error(self, exc: Exception) -> None:
        self.log.append(f"ERROR: {exc}")
        QMessageBox.critical(self, "Generation failed", str(exc))
