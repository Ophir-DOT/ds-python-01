"""Branded header bar — Dot Compliance purple chrome with the DOT mark."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from ..theme import ASSETS, MONO_FONT, C, tint_white


class BrandHeader(QWidget):
    def __init__(self, subtitle: str = "DESIGN SPECIFICATION TOOL", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BrandHeader")
        self.setFixedHeight(46)
        self.setStyleSheet(
            f"#BrandHeader {{ background: {C.purple_500}; }}"
            "#BrandHeader QLabel { background: transparent; color: #ffffff; }"
        )

        logo = QLabel()
        pix = QPixmap(str(ASSETS / "logo-mark.png"))
        if not pix.isNull():
            white = tint_white(pix).scaledToHeight(24, Qt.TransformationMode.SmoothTransformation)
            logo.setPixmap(white)

        name = QLabel("DOT Spec")
        name.setStyleSheet("color:#fff; font-size:15px; font-weight:600;")

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet("color: rgba(255,255,255,0.25);")

        sub = QLabel(subtitle)
        sub_font = QFont(MONO_FONT, 8)
        sub_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        sub.setFont(sub_font)
        sub.setStyleSheet("color: rgba(255,255,255,0.62);")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)
        layout.addWidget(logo)
        layout.addWidget(name)
        layout.addWidget(divider)
        layout.addWidget(sub)
        layout.addStretch(1)
