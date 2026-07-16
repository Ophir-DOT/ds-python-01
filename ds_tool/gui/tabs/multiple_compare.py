"""Tab 3 — Multiple & Compare: CSV-driven batch generation + org compare.

Batch 'Generate DS' is wired to the real render pipeline (demo: synthetic specs).
Org-to-org compare backends are a later phase and report status for now.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..actions import build_demo_specs, collect_specs, render_specs
from ..async_bridge import run_async
from ..state import AppState
from ..widgets.log_panel import LogPanel

_TEMPLATE_HEADER = ["Object Label Name", "Profiles/Permission Set (Separated by ;)"]
_EXAMPLE_ROWS = [
    ["Account", "System Administrator;Standard User"],
    ["Claim__c", "System Administrator"],
]
_COLUMNS = ["Object", "Profiles/Permission Sets", "Output", "Equal"]
_COMING_SOON = "Not yet available — org-to-org compare is planned for a later phase."


class MultipleCompareTab(QWidget):
    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state

        # CSV buttons
        self.export_template_btn = QPushButton("Export All Object CSV Template")
        self.export_template_btn.setObjectName("mc_export_template")
        self.export_example_btn = QPushButton("Export Request Example")
        self.export_example_btn.setObjectName("mc_export_example")
        self.import_btn = QPushButton("Import Request")
        self.import_btn.setObjectName("mc_import")
        self.export_template_btn.clicked.connect(self._export_template)
        self.export_example_btn.clicked.connect(self._export_example)
        self.import_btn.clicked.connect(self._pick_and_import)

        # Compare buttons (disabled — org-to-org compare backend is a later phase)
        self.compare_apex_btn = QPushButton("Compare Apex Classes")
        self.compare_apex_btn.setObjectName("mc_compare_apex")
        self.compare_profiles_btn = QPushButton("Compare Profile + Permission Set")
        self.compare_profiles_btn.setObjectName("mc_compare_profiles")

        # Batch buttons
        self.generate_ds_btn = QPushButton("Generate DS")
        self.generate_ds_btn.setObjectName("mc_generate_ds")
        self.compare_btn = QPushButton("Compare")
        self.compare_btn.setObjectName("mc_compare")
        self.retry_btn = QPushButton("Retry")
        self.retry_btn.setObjectName("mc_retry")
        self.generate_ds_btn.clicked.connect(self._generate_ds)

        for btn in (self.compare_apex_btn, self.compare_profiles_btn, self.compare_btn, self.retry_btn):
            btn.setEnabled(False)
            btn.setToolTip(_COMING_SOON)

        grid = QGridLayout()
        grid.addWidget(self.export_template_btn, 0, 0)
        grid.addWidget(self.export_example_btn, 0, 1)
        grid.addWidget(self.import_btn, 0, 2)
        grid.addWidget(self.compare_apex_btn, 1, 0)
        grid.addWidget(self.compare_profiles_btn, 1, 1)
        grid.addWidget(self.generate_ds_btn, 2, 0)
        grid.addWidget(self.compare_btn, 2, 1)
        grid.addWidget(self.retry_btn, 2, 2)
        btn_box = QGroupBox("Actions")
        btn_box.setLayout(grid)

        self.compare_note = QLabel("Compare features (org-to-org) are coming in a later phase.")
        self.compare_note.setStyleSheet("color: #777;")

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setObjectName("mc_table")
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.log = LogPanel("Output")

        layout = QVBoxLayout(self)
        layout.addWidget(btn_box)
        layout.addWidget(self.compare_note)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.log, 1)

    # ---- CSV import/export -----------------------------------------------

    def _export_template(self) -> None:
        path = self._state.out_dir / "All_Object_Request_Template.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        objects = self._state.source.objects if self._state.source_connected else []
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(_TEMPLATE_HEADER)
            for o in objects:
                writer.writerow([o.label, ""])
        self.log.append(f"Wrote template: {path}")
        self.log.set_output_dir(path.parent)

    def _export_example(self) -> None:
        path = self._state.out_dir / "Request_Example.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(_TEMPLATE_HEADER)
            writer.writerows(_EXAMPLE_ROWS)
        self.log.append(f"Wrote example: {path}")
        self.log.set_output_dir(path.parent)

    def _pick_and_import(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Import request CSV", str(self._state.out_dir), "CSV files (*.csv)"
        )
        if chosen:
            self.import_csv(Path(chosen))

    def import_csv(self, path: Path) -> None:
        """Parse a request CSV into the results table. Public for scripted tests."""
        rows: list[tuple[str, str]] = []
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            next(reader, None)  # skip header row
            for raw in reader:
                if not raw or not raw[0].strip():
                    continue
                rows.append((raw[0].strip(), raw[1].strip() if len(raw) > 1 else ""))

        self.table.setRowCount(len(rows))
        for r, (obj, profiles) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(obj))
            self.table.setItem(r, 1, QTableWidgetItem(profiles))
            self.table.setItem(r, 2, QTableWidgetItem("—"))
            self.table.setItem(r, 3, QTableWidgetItem("—"))
        self.log.append(f"Imported {len(rows)} request row(s) from {path.name}")

    # ---- batch actions ----------------------------------------------------

    def _row_objects(self) -> list[str]:
        return [
            self.table.item(r, 0).text()
            for r in range(self.table.rowCount())
            if self.table.item(r, 0)
        ]

    def _resolve_api_names(self, labels: list[str]) -> list[str]:
        if not self._state.source_connected:
            return labels
        by_label = {o.label: o.api_name for o in self._state.source.objects}
        by_api = {o.api_name for o in self._state.source.objects}
        out = []
        for label in labels:
            out.append(by_label.get(label, label if label in by_api else label))
        return out

    def _generate_ds(self) -> None:
        if not self._state.source_connected:
            QMessageBox.warning(self, "Not connected", "Connect a Source org first.")
            return
        labels = self._row_objects()
        if not labels:
            QMessageBox.warning(self, "No rows", "Import a request CSV first.")
            return
        objects = self._resolve_api_names(labels)
        out_dir = self._state.out_dir / "batch"
        conn = self._state.source
        demo = self._state.demo
        settings = self._state.settings
        self.log.append(f"Batch generating DS for {len(objects)} object(s)…")

        async def _coro(progress):
            specs = (
                build_demo_specs(conn, objects)
                if demo
                else await collect_specs(conn, objects, None, None, 8, progress)
            )
            return render_specs(specs, out_dir, settings, progress, conn)

        run_async(
            self,
            _coro,
            on_progress=self.log.append,
            on_done=lambda res: self._on_batch_done(res, out_dir),
            on_error=lambda exc: self.log.append(f"ERROR: {exc}"),
            sync=demo,
        )

    def _on_batch_done(self, result, out_dir: Path) -> None:
        written, fmt = result
        for r in range(self.table.rowCount()):
            obj = self.table.item(r, 0).text() if self.table.item(r, 0) else ""
            self.table.setItem(r, 2, QTableWidgetItem(f"{obj}_DS.{fmt.lower()}"))
        self.log.append(f"Batch done — {len(written)} {fmt} file(s) in {out_dir}")
        self.log.set_output_dir(out_dir)
