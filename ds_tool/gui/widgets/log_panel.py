"""Embeddable, non-modal output log with an 'open output folder' button."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LogPanel(QGroupBox):
    def __init__(self, title: str = "Output", parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self._last_dir: Path | None = None

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(120)

        self.open_btn = QPushButton("Open output folder")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._log.clear)

        buttons = QHBoxLayout()
        buttons.addWidget(self.open_btn)
        buttons.addWidget(self.clear_btn)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._log, 1)
        layout.addLayout(buttons)

    def append(self, message: str) -> None:
        self._log.appendPlainText(message)
        bar = self._log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def set_output_dir(self, path: Path) -> None:
        self._last_dir = path
        self.open_btn.setEnabled(True)

    def _open(self) -> None:
        if self._last_dir is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_dir)))
