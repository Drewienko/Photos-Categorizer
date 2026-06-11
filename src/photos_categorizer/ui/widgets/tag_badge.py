from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QToolButton,
    QWidget,
)

from photos_categorizer.models.photo import Tag


def source_color(source: str) -> str:
    match source:
        case "clip":
            return "#2a9df4"
        case "vision":
            return "#4ec07a"
        case "manual":
            return "#f0a637"
        case _:
            return "#b6bac3"


def conf_color(confidence: float) -> str:
    if confidence >= 0.85:
        return "#2a9df4"
    if confidence >= 0.70:
        return "#f0a637"
    return "#e25c5c"


class TagBadge(QFrame):
    removed = Signal(int)  # tag_id

    def __init__(self, tag: Tag, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tag = tag
        src_color = source_color(tag.source)
        bar_color = conf_color(tag.confidence)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 6, 5)
        layout.setSpacing(8)

        dot = QLabel("●")
        dot.setFixedWidth(10)
        dot.setStyleSheet(
            f"color: {src_color}; font-size: 8px; background: transparent; border: none;"
        )
        layout.addWidget(dot)

        name_lbl = QLabel(tag.name)
        name_lbl.setStyleSheet(
            "color: #e6e8ec; font-size: 13px; background: transparent; border: none;"
        )
        layout.addWidget(name_lbl)

        if tag.source == "manual":
            badge = QLabel("manual")
            badge.setStyleSheet(
                "color: #f0a637; font-size: 10px; font-weight: 500;"
                "background: #f0a63720; border: 1px solid #f0a63750;"
                "border-radius: 3px; padding: 1px 5px;"
            )
            layout.addWidget(badge)

        layout.addStretch()

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(tag.confidence * 100))
        bar.setTextVisible(False)
        bar.setFixedSize(72, 6)
        bar.setStyleSheet(
            f"QProgressBar {{ background: #1c1f24; border: none; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {bar_color}; border-radius: 3px; }}"
        )
        layout.addWidget(bar, alignment=Qt.AlignmentFlag.AlignVCenter)

        pct = QLabel(f"{tag.confidence:.0%}")
        pct.setFixedWidth(34)
        pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        pct.setStyleSheet(
            f"color: {bar_color}; font-size: 11px; font-weight: 600;"
            "background: transparent; border: none;"
        )
        layout.addWidget(pct)

        btn = QToolButton()
        btn.setText("×")
        btn.setFixedSize(18, 18)
        btn.setStyleSheet(
            "color: #4a4d55; font-size: 14px; background: transparent; border: none;"
        )
        btn.clicked.connect(lambda: self.removed.emit(self._tag.id))
        layout.addWidget(btn)

        self.setStyleSheet(
            "QFrame { background-color: #14161a; border: 1px solid #1c1f24; border-radius: 6px; }"
            "QFrame:hover { border-color: #2a2d35; background-color: #16181e; }"
        )
