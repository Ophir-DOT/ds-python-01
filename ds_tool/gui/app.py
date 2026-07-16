"""QApplication bootstrap for the Design Specification Tool GUI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .state import AppState
from .theme import apply_theme


def _demo_enabled(argv: list[str]) -> bool:
    return "--demo" in argv or os.environ.get("DS_TOOL_DEMO") == "1"


def main() -> int:
    argv = sys.argv
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("Design Specification Tool")
    apply_theme(app)

    state = AppState(demo=_demo_enabled(argv), out_dir=Path.cwd() / "out")
    window = MainWindow(state)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
