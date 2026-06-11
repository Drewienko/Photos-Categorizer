from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from photos_categorizer.db.manager import DatabaseManager


class SettingsDialog(QDialog):
    def __init__(self, db: DatabaseManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self._setup_ui()
        self._load()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(16)

        root.addWidget(self._make_engine_group())
        root.addWidget(self._make_credentials_group())
        root.addWidget(self._make_labels_group())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ── Engine group ──────────────────────────────────────────────────────────

    def _make_engine_group(self) -> QGroupBox:
        box = QGroupBox("Default tagging engine")
        layout = QHBoxLayout(box)
        layout.setSpacing(24)
        self._clip_radio = QRadioButton("CLIP (offline)")
        self._vision_radio = QRadioButton("Google Vision (online)")
        layout.addWidget(self._clip_radio)
        layout.addWidget(self._vision_radio)
        layout.addStretch()
        return box

    # ── Credentials group ─────────────────────────────────────────────────────

    def _make_credentials_group(self) -> QGroupBox:
        box = QGroupBox("Google Vision credentials")
        layout = QVBoxLayout(box)

        hint = QLabel(
            "Path to a service account JSON file "
            "(GOOGLE_APPLICATION_CREDENTIALS). Only needed for Google Vision."
        )
        hint.setObjectName("labelMuted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        self._creds_edit = QLineEdit()
        self._creds_edit.setPlaceholderText("e.g. /home/user/my-project-key.json")
        browse_btn = QLabel('<a href="#">Browse…</a>')
        browse_btn.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        browse_btn.linkActivated.connect(self._browse_credentials)
        row.addWidget(self._creds_edit, stretch=1)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        return box

    # ── CLIP labels group ─────────────────────────────────────────────────────

    def _make_labels_group(self) -> QGroupBox:
        box = QGroupBox("CLIP label vocabulary")
        layout = QVBoxLayout(box)

        hint = QLabel("One label per line (or comma-separated). Used as CLIP zero-shot prompts.")
        hint.setObjectName("labelMuted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._labels_edit = QPlainTextEdit()
        self._labels_edit.setFixedHeight(140)
        self._labels_edit.setPlaceholderText("nature\npeople\narchitecture\n...")
        layout.addWidget(self._labels_edit)

        return box

    # ── Load / Save ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        engine = self._db.get_setting("engine")
        if engine == "vision":
            self._vision_radio.setChecked(True)
        else:
            self._clip_radio.setChecked(True)

        self._creds_edit.setText(self._db.get_setting("vision_credentials"))

        raw = self._db.get_setting("clip_labels")
        labels = [s.strip() for s in raw.replace(",", "\n").splitlines() if s.strip()]
        self._labels_edit.setPlainText("\n".join(labels))

    def _save(self) -> None:
        engine = "vision" if self._vision_radio.isChecked() else "clip"
        self._db.set_setting("engine", engine)

        creds = self._creds_edit.text().strip()
        self._db.set_setting("vision_credentials", creds)

        raw = self._labels_edit.toPlainText()
        labels = [s.strip() for s in raw.replace(",", "\n").splitlines() if s.strip()]
        self._db.set_setting("clip_labels", ",".join(labels))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _browse_credentials(self, _: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select service account JSON", "", "JSON files (*.json)"
        )
        if path and Path(path).exists():
            self._creds_edit.setText(path)
