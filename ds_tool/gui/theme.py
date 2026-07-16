"""Dot Compliance brand theme for the GUI (colors, fonts, Qt stylesheet).

Implements the "Branded baseline" direction from the DOT Spec wireframes:
the existing layout, dressed in Dot Compliance chrome — purple/pink/white
palette, Quicksand UI font, JetBrains Mono for technical text, pill-free
4px controls, one pink primary action and purple-filled secondaries.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).parent / "assets"


# ── Brand palette (Dot Compliance Brand Book 2024/2025) ──────────────────
class C:
    purple_500 = "#270648"
    purple_400 = "#540D9A"
    purple_300 = "#7D32C7"
    purple_50 = "#EDE3F8"
    purple_20 = "#F5F3F8"
    gp_500 = "#57515C"
    gp_400 = "#847C8C"
    gp_300 = "#ABA1B5"
    gp_200 = "#C6BDCF"
    gp_100 = "#DACFE5"
    gp_50 = "#EDEBF2"
    pink_500 = "#DD00B7"
    pink_600 = "#C400A3"
    pink_100 = "#FFE1FB"
    green_500 = "#38C5A2"
    gold_100 = "#F7EEE8"
    white = "#FFFFFF"


UI_FONT = "Quicksand"
MONO_FONT = "JetBrains Mono"


def _u(path: Path) -> str:
    """Absolute path with forward slashes for QSS url()."""
    return str(path).replace("\\", "/")


def load_fonts() -> tuple[str, str]:
    """Load bundled brand fonts; return (ui_family, mono_family) with fallbacks."""
    ui, mono = "Segoe UI", "Consolas"
    quick = ASSETS / "fonts" / "Quicksand.ttf"
    jb = ASSETS / "fonts" / "JetBrainsMono.ttf"
    if quick.exists():
        fid = QFontDatabase.addApplicationFont(str(quick))
        fams = QFontDatabase.applicationFontFamilies(fid)
        if fams:
            ui = fams[0]
    if jb.exists():
        fid = QFontDatabase.addApplicationFont(str(jb))
        fams = QFontDatabase.applicationFontFamilies(fid)
        if fams:
            mono = fams[0]
    return ui, mono


def tint_white(pix: QPixmap) -> QPixmap:
    """Recolor a pixmap to solid white, preserving its alpha (for dark headers)."""
    out = QPixmap(pix.size())
    out.fill(QColor(0, 0, 0, 0))
    p = QPainter(out)
    p.drawPixmap(0, 0, pix)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(out.rect(), QColor("white"))
    p.end()
    return out


def stylesheet() -> str:
    check = _u(ASSETS / "check.svg")
    return f"""
    QMainWindow, QDialog {{ background: {C.purple_20}; }}
    QWidget {{ color: {C.purple_500}; }}
    QToolTip {{ background: {C.purple_500}; color: #fff; border: 0; padding: 4px 8px; }}

    QTabWidget::pane {{ background: {C.purple_20}; border: 1px solid {C.gp_100}; border-top: 0; }}
    QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
    QTabBar::tab {{
        background: transparent; color: {C.gp_500}; padding: 9px 16px;
        font-weight: 600; border: 0; border-bottom: 2px solid transparent; margin-right: 2px;
    }}
    QTabBar::tab:selected {{ color: {C.purple_500}; border-bottom: 2px solid {C.pink_500}; background: {C.purple_20}; }}
    QTabBar::tab:hover:!selected {{ color: {C.purple_500}; }}
    QTabBar::tab:disabled {{ color: {C.gp_300}; }}

    QGroupBox {{
        background: {C.white}; border: 1px solid {C.gp_100}; border-radius: 6px;
        margin-top: 14px; padding: 14px 12px 12px; font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; subcontrol-position: top left;
        left: 12px; top: 1px; padding: 0 6px; color: {C.purple_300};
        font-family: "{MONO_FONT}"; font-size: 10px; font-weight: 600;
    }}

    QPushButton {{
        background: {C.white}; border: 1px solid {C.gp_200}; border-radius: 4px;
        color: {C.purple_500}; padding: 6px 14px; font-weight: 600; min-height: 22px;
    }}
    QPushButton:hover {{ border-color: {C.purple_300}; color: {C.purple_400}; }}
    QPushButton:disabled {{ background: #F4F2F6; color: {C.gp_300}; border-color: {C.gp_100}; }}

    /* Primary (pink) — the single most-used action */
    QPushButton#ds_generate, QPushButton#source_connect {{
        background: {C.pink_500}; border-color: {C.pink_500}; color: #fff;
    }}
    QPushButton#ds_generate:hover, QPushButton#source_connect:hover {{
        background: {C.pink_600}; border-color: {C.pink_600};
    }}
    /* Secondary (purple-filled) — live, secondary generators */
    QPushButton#ds_excel, QPushButton#ds_profiles_only, QPushButton#mc_generate_ds, QPushButton#urs_generate {{
        background: {C.purple_500}; border-color: {C.purple_500}; color: #fff;
    }}
    QPushButton#ds_excel:hover, QPushButton#ds_profiles_only:hover,
    QPushButton#mc_generate_ds:hover, QPushButton#urs_generate:hover {{
        background: {C.purple_400}; border-color: {C.purple_400};
    }}
    QPushButton#ds_excel:disabled, QPushButton#ds_profiles_only:disabled,
    QPushButton#mc_generate_ds:disabled, QPushButton#urs_generate:disabled,
    QPushButton#ds_generate:disabled, QPushButton#source_connect:disabled {{
        background: #F4F2F6; color: {C.gp_300}; border-color: {C.gp_100};
    }}

    QComboBox {{
        background: {C.white}; border: 1px solid {C.gp_200}; border-radius: 4px;
        padding: 4px 8px; color: {C.purple_500}; min-height: 24px;
    }}
    QComboBox:hover {{ border-color: {C.purple_300}; }}
    QComboBox:disabled {{ background: #F4F2F6; color: {C.gp_300}; border-color: {C.gp_100}; }}
    QComboBox::drop-down {{ border: 0; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {C.white}; border: 1px solid {C.gp_100}; outline: 0;
        selection-background-color: {C.purple_500}; selection-color: #fff;
    }}

    QListWidget, QTreeWidget {{ background: {C.white}; border: 1px solid {C.gp_100}; border-radius: 4px; outline: 0; }}
    QListWidget::item {{ padding: 4px 8px; color: {C.purple_500}; border-bottom: 1px solid {C.gp_50}; }}
    QListWidget::item:selected {{ background: {C.purple_500}; color: #fff; }}
    QListWidget::item:hover:!selected {{ background: {C.purple_20}; }}

    QLineEdit {{
        background: {C.white}; border: 1px solid {C.gp_200}; border-radius: 4px;
        padding: 5px 8px; color: {C.purple_500}; selection-background-color: {C.purple_300};
    }}
    QLineEdit:focus {{ border: 1px solid {C.purple_300}; }}
    QLineEdit:disabled {{ background: #F4F2F6; color: {C.gp_300}; }}

    QCheckBox {{ color: {C.purple_500}; spacing: 7px; }}
    QCheckBox:disabled {{ color: {C.gp_300}; }}
    QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {C.gp_200}; border-radius: 3px; background: #fff; }}
    QCheckBox::indicator:checked {{ background: {C.pink_500}; border-color: {C.pink_500}; image: url("{check}"); }}
    QCheckBox::indicator:disabled {{ background: #F4F2F6; border-color: {C.gp_100}; }}

    QTableWidget, QTableView {{
        background: {C.white}; border: 1px solid {C.gp_100}; gridline-color: {C.gp_50};
        color: {C.purple_500}; outline: 0;
    }}
    QHeaderView::section {{
        background: {C.purple_20}; color: {C.gp_400}; border: 0;
        border-bottom: 1px solid {C.gp_100}; padding: 6px 8px; font-weight: 600;
    }}
    QTableWidget::item:selected {{ background: {C.purple_500}; color: #fff; }}

    QPlainTextEdit {{
        background: {C.white}; border: 1px solid {C.gp_100}; border-radius: 4px;
        color: {C.gp_500}; font-family: "{MONO_FONT}"; font-size: 11px;
    }}

    QStatusBar {{ background: {C.purple_20}; border-top: 1px solid {C.gp_100}; color: {C.gp_500}; }}
    QStatusBar::item {{ border: 0; }}
    QStatusBar QLabel {{ color: {C.gp_500}; font-family: "{MONO_FONT}"; font-size: 10px; }}

    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {C.gp_200}; border-radius: 5px; min-height: 28px; }}
    QScrollBar::handle:vertical:hover {{ background: {C.gp_300}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; }}
    QScrollBar::handle:horizontal {{ background: {C.gp_200}; border-radius: 5px; min-width: 28px; }}
    """


def apply_theme(app: QApplication) -> None:
    ui, _mono = load_fonts()
    app.setFont(QFont(ui, 10))
    app.setStyleSheet(stylesheet())
