"""Tab 2 — URS, PQ and Traceability Matrix.

The full URS document backend is a later phase; this tab wires the selection UI
and emits a minimal traceability CSV so the action is demonstrably functional.
"""

from __future__ import annotations

import csv

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..state import AppState
from ..widgets.dual_list import DualList
from ..widgets.log_panel import LogPanel

_SECTIONS = "Fields;Record Types;Validation Rules;Page Layouts;Profiles"


class TraceabilityTab(QWidget):
    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state

        self.objects = DualList("Available Objects", "Selected Objects")
        self.objects.setObjectName("urs_objects")
        obj_box = QGroupBox("Objects")
        QVBoxLayout(obj_box).addWidget(self.objects)

        self.project = QLineEdit()
        self.project.setObjectName("urs_project")
        self.project.setPlaceholderText("Project name as in the internal environment (optional)")
        proj_row = QHBoxLayout()
        proj_row.addWidget(QLabel("Project Name:"))
        proj_row.addWidget(self.project, 1)

        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setObjectName("urs_generate")
        self.generate_btn.clicked.connect(self._on_generate)

        self.log = LogPanel("Output")

        banner = QLabel(
            "Not yet available — full URS / PQ / Traceability generation is "
            "planned for a later phase."
        )
        banner.setStyleSheet("color: #8a6d3b; background: #fcf8e3; padding: 8px; border: 1px solid #faebcc;")
        banner.setWordWrap(True)

        # Disable the whole tab's controls until the backend lands.
        for w in (self.objects, self.project, self.generate_btn):
            w.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(banner)
        layout.addWidget(obj_box, 1)
        layout.addLayout(proj_row)
        layout.addWidget(self.generate_btn)
        layout.addWidget(self.log, 1)

    def on_source_connected(self) -> None:
        conn = self._state.source
        if conn:
            self.objects.set_items([(o.api_name, o.label) for o in conn.objects])

    def _on_generate(self) -> None:
        if not self._state.source_connected:
            QMessageBox.warning(self, "Not connected", "Connect a Source org first.")
            return
        objects = self.objects.selected_keys()
        if not objects:
            QMessageBox.warning(self, "No objects", "Select at least one object.")
            return

        project = self.project.text().strip() or "Untitled"
        out_dir = self._state.out_dir / "URS"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"Traceability_{project.replace(' ', '_')}.csv"

        label_by_key = {o.api_name: o.label for o in self._state.source.objects}
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Object", "API Name", "Project", "Sections"])
            for api in objects:
                writer.writerow([label_by_key.get(api, api), api, project, _SECTIONS])

        self.log.append(
            f"Generated preliminary traceability matrix for {len(objects)} object(s):\n{out_path}\n"
            "(Full URS/PQ document backend is a later phase.)"
        )
        self.log.set_output_dir(out_dir)
