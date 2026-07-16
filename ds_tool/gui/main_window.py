"""Main window: connection bar on top, the four feature tabs below."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from .state import AppState
from .tabs.design_spec import DesignSpecTab
from .tabs.multiple_compare import MultipleCompareTab
from .tabs.settings import SettingsTab
from .tabs.traceability import TraceabilityTab
from .widgets.connection_bar import ConnectionBar
from .widgets.header import BrandHeader

APP_VERSION = "DS-Python-1.0"


class MainWindow(QMainWindow):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        title = "Design Specification Tool"
        if state.demo:
            title += "  —  DEMO MODE"
        self.setWindowTitle(title)

        self.connection = ConnectionBar(state)
        self.connection.connected.connect(self._on_connected)

        self.design = DesignSpecTab(state)
        self.traceability = TraceabilityTab(state)
        self.multiple = MultipleCompareTab(state)
        self.settings = SettingsTab(state)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.design, "Design Specification")
        self.tabs.addTab(self.traceability, "URS, PQ && Traceability")
        self.tabs.addTab(self.multiple, "Multiple && Compare")
        self.tabs.addTab(self.settings, "Settings")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(BrandHeader())
        layout.addWidget(self.connection)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self.resize(1060, 840)

        # Version label, bottom-left of the status bar.
        version_label = QLabel(APP_VERSION)
        version_label.setStyleSheet("color: #888; padding: 0 6px;")
        self.statusBar().addWidget(version_label)

    def _on_connected(self, role: str) -> None:
        if role == "source":
            self.design.on_source_connected()
            self.traceability.on_source_connected()
            self.settings.on_source_connected()
