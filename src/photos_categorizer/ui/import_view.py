import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from photos_categorizer.db.manager import DatabaseManager
from photos_categorizer.importer.importer import FileResult, PhotoImporter
from photos_categorizer.importer.importer import scan_folder as _scan_folder
from photos_categorizer.importer.worker import ImportSession
from photos_categorizer.models.photo import Photo
from photos_categorizer.tagging.engine import TaggingEngine


class ImportView(QWidget):
    go_gallery = Signal(Photo)  # emitted after each file so gallery can add it live
    view_results = Signal()     # emitted when "View Gallery →" clicked

    def __init__(self, db: DatabaseManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._session: ImportSession | None = None
        self._importer = PhotoImporter(db)
        self._total = 0
        self._done = 0
        self._tagged = 0
        self._start_time: float = 0.0
        self._pulse_state = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(600)
        self._pulse_timer.timeout.connect(self._pulse_dot)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Import & analyze folder")
        title.setObjectName("labelTitle")
        header.addWidget(title)
        header.addStretch()
        self._status_chip = QLabel("● Idle")
        self._status_chip.setStyleSheet("color: #4a4d55; font-size: 12px;")
        header.addWidget(self._status_chip)
        root.addLayout(header)

        desc = QLabel(
            "Recursively scan a directory, generate thumbnails, "
            "and assign tags above the confidence threshold."
        )
        desc.setObjectName("labelMuted")
        desc.setWordWrap(True)
        root.addWidget(desc)

        root.addWidget(self._make_config_group())

        self._progress_group = self._make_progress_group()
        self._progress_group.setVisible(False)
        root.addWidget(self._progress_group)

        log_box = QGroupBox("Processing log")
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(8, 8, 8, 8)
        log_layout.setSpacing(6)

        # Log header: entry count + filter buttons
        log_header = QHBoxLayout()
        self._log_count_lbl = QLabel("0 entries")
        self._log_count_lbl.setObjectName("labelMuted")
        log_header.addWidget(self._log_count_lbl)
        log_header.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._log.clear if hasattr(self, "_log") else lambda: None)
        log_header.addWidget(clear_btn)
        log_layout.addLayout(log_header)

        self._log = QListWidget()
        self._log.setObjectName("importLog")
        # wire clear_btn now that _log exists
        clear_btn.clicked.disconnect()
        clear_btn.clicked.connect(self._clear_log)
        log_layout.addWidget(self._log)

        root.addWidget(log_box, stretch=1)

    # ── Config group ──────────────────────────────────────────────────────────

    def _make_config_group(self) -> QGroupBox:
        box = QGroupBox("Source")
        layout = QVBoxLayout(box)
        layout.setSpacing(12)

        folder_row = QHBoxLayout()
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select folder…")
        self._folder_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(self._folder_edit, stretch=1)
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)

        options_row = QHBoxLayout()
        options_row.setSpacing(24)

        engine_frame = QFrame()
        engine_layout = QHBoxLayout(engine_frame)
        engine_layout.setContentsMargins(0, 0, 0, 0)
        engine_layout.setSpacing(12)
        engine_lbl = QLabel("Model:")
        self._clip_radio = QRadioButton("CLIP (offline)")
        self._vision_radio = QRadioButton("Google Vision")
        self._clip_radio.setChecked(self._db.get_setting("engine") != "vision")
        self._vision_radio.setChecked(self._db.get_setting("engine") == "vision")
        engine_layout.addWidget(engine_lbl)
        engine_layout.addWidget(self._clip_radio)
        engine_layout.addWidget(self._vision_radio)
        options_row.addWidget(engine_frame)

        options_row.addStretch()

        thresh_frame = QFrame()
        thresh_layout = QHBoxLayout(thresh_frame)
        thresh_layout.setContentsMargins(0, 0, 0, 0)
        thresh_layout.setSpacing(10)
        thresh_lbl = QLabel("Confidence:")
        self._thresh_slider = QSlider(Qt.Orientation.Horizontal)
        self._thresh_slider.setRange(0, 100)
        saved = int(float(self._db.get_setting("threshold") or "0.70") * 100)
        self._thresh_slider.setValue(saved)
        self._thresh_slider.setFixedWidth(120)
        self._thresh_val = QLabel(f"{saved}%")
        self._thresh_val.setFixedWidth(32)
        self._thresh_slider.valueChanged.connect(self._on_threshold_changed)
        thresh_layout.addWidget(thresh_lbl)
        thresh_layout.addWidget(self._thresh_slider)
        thresh_layout.addWidget(self._thresh_val)
        options_row.addWidget(thresh_frame)

        layout.addLayout(options_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._start_btn = QPushButton("Begin analysis")
        self._start_btn.setObjectName("btnAccent")
        self._start_btn.clicked.connect(self._start_import)
        btn_row.addWidget(self._start_btn)
        layout.addLayout(btn_row)

        return box

    # ── Progress group ────────────────────────────────────────────────────────

    def _make_progress_group(self) -> QGroupBox:
        box = QGroupBox("Progress")
        layout = QVBoxLayout(box)
        layout.setSpacing(10)

        stats_row = QHBoxLayout()
        self._stat_processed = self._stat_label("0", "PROCESSED")
        self._stat_total = self._stat_label("0", "TOTAL")
        self._stat_tagged = self._stat_label("0", "TAGGED")
        self._stat_failed = self._stat_label("0", "FAILED")
        self._stat_elapsed = self._stat_label("0:00", "ELAPSED")
        self._stat_eta = self._stat_label("—", "ETA")
        for w in (
            self._stat_processed, self._stat_total, self._stat_tagged,
            self._stat_failed, self._stat_elapsed, self._stat_eta,
        ):
            stats_row.addWidget(w)
        stats_row.addStretch()

        action_col = QVBoxLayout()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("btnDanger")
        self._cancel_btn.clicked.connect(self._cancel_import)
        self._view_btn = QPushButton("View Gallery →")
        self._view_btn.setObjectName("btnAccent")
        self._view_btn.setVisible(False)
        self._view_btn.clicked.connect(self.view_results)
        action_col.addWidget(self._cancel_btn)
        action_col.addWidget(self._view_btn)
        stats_row.addLayout(action_col)
        layout.addLayout(stats_row)

        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        layout.addWidget(self._progress_bar)

        return box

    def _stat_label(self, value: str, name: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("panel")
        vl = QVBoxLayout(frame)
        vl.setContentsMargins(10, 8, 10, 8)
        vl.setSpacing(2)
        val = QLabel(value)
        val.setStyleSheet("font-size: 20px; font-weight: 700; color: #e6e8ec;")
        val.setObjectName(f"stat_{name.lower()}")
        lbl = QLabel(name)
        lbl.setObjectName("labelSection")
        vl.addWidget(val)
        vl.addWidget(lbl)
        frame.setFixedWidth(90)
        return frame

    def _find_stat(self, name: str) -> QLabel | None:
        return self._progress_group.findChild(QLabel, f"stat_{name}")

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot()
    def _pulse_dot(self) -> None:
        self._pulse_state = not self._pulse_state
        dot = "●" if self._pulse_state else "○"
        self._status_chip.setText(f"{dot} Processing")

    @Slot(int)
    def _on_threshold_changed(self, value: int) -> None:
        self._thresh_val.setText(f"{value}%")

    @Slot()
    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder")
        if folder:
            self._folder_edit.setText(folder)

    @Slot()
    def _clear_log(self) -> None:
        self._log.clear()
        self._log_count_lbl.setText("0 entries")

    @Slot()
    def _start_import(self) -> None:
        folder = self._folder_edit.text().strip()
        if not folder or not Path(folder).is_dir():
            self._log_entry("error", "Select a valid folder first.")
            return

        paths = _scan_folder(Path(folder))
        if not paths:
            self._log_entry("info", "No supported images found.")
            return

        self._log.clear()
        self._log_count_lbl.setText("0 entries")
        self._done = 0
        self._tagged = 0
        self._total = len(paths)
        self._start_time = time.monotonic()
        self._start_btn.setEnabled(False)
        self._view_btn.setVisible(False)
        self._cancel_btn.setVisible(True)
        self._status_chip.setText("● Processing")
        self._status_chip.setStyleSheet("color: #2a9df4; font-size: 12px;")
        self._pulse_state = True
        self._pulse_timer.start()
        self._progress_group.setVisible(True)
        self._progress_bar.setValue(0)

        engine = self._build_engine()
        if engine is None:
            self._start_btn.setEnabled(True)
            return

        self._session = ImportSession()
        self._session.file_done.connect(self._on_file_done)
        self._session.error.connect(self._on_error)
        self._session.all_finished.connect(self._on_finished)
        self._session.start(Path(folder), engine)

        self._update_stat("total", str(self._total))
        self._update_stat("processed", "0")
        self._update_stat("tagged", "0")
        self._update_stat("failed", "0")
        self._update_stat("elapsed", "0:00")
        self._update_stat("eta", "—")

    def _build_engine(self) -> TaggingEngine | None:
        threshold = self._thresh_slider.value() / 100.0
        if self._vision_radio.isChecked():
            creds = self._db.get_setting("vision_credentials")
            if not creds or not Path(creds).exists():
                self._log_entry("error", "Google credentials not configured. Go to Settings.")
                return None
            from photos_categorizer.tagging.vision_engine import GoogleVisionEngine

            return GoogleVisionEngine(credentials_path=creds, threshold=threshold)
        else:
            raw = self._db.get_setting("clip_labels")
            labels = [s.strip() for s in raw.split(",") if s.strip()]
            from photos_categorizer.tagging.clip_engine import CLIPEngine

            return CLIPEngine(labels=labels, threshold=threshold)

    @Slot(object)
    def _on_file_done(self, result: object) -> None:
        if not isinstance(result, FileResult):
            return
        try:
            photo, tags = self._importer.persist(result)
        except Exception as exc:
            self._on_error(f"{result.path.name}: {exc}")
            return

        self._done += 1
        if tags:
            self._tagged += 1

        tag_names = ", ".join(t.name for t in tags[:5])
        ms = f"  {result.duration_ms}ms" if result.duration_ms else ""
        self._log_entry("ok", f"{result.path.name}  →  {tag_names or 'no tags'}{ms}")

        self._update_stat("processed", str(self._done))
        self._update_stat("tagged", str(self._tagged))
        self._progress_bar.setValue(int(self._done / self._total * 100) if self._total else 0)
        self._update_timers()
        self.go_gallery.emit(photo)

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._done += 1
        lbl = self._find_stat("failed")
        failed = int(lbl.text()) + 1 if lbl else 1
        self._update_stat("failed", str(failed))
        self._log_entry("error", msg)
        self._progress_bar.setValue(int(self._done / self._total * 100) if self._total else 0)
        self._update_timers()

    @Slot()
    def _on_finished(self) -> None:
        self._pulse_timer.stop()
        self._start_btn.setEnabled(True)
        self._cancel_btn.setVisible(False)
        self._view_btn.setVisible(True)
        self._status_chip.setText("● Done")
        self._status_chip.setStyleSheet("color: #4ec07a; font-size: 12px;")
        elapsed = time.monotonic() - self._start_time
        self._update_stat("elapsed", _fmt_time(elapsed))
        self._update_stat("eta", "0:00")
        self._log_entry("info", f"Done — {self._done} file(s) processed.")

    @Slot()
    def _cancel_import(self) -> None:
        self._pulse_timer.stop()
        if self._session:
            from PySide6.QtCore import QThreadPool

            QThreadPool.globalInstance().clear()
        self._start_btn.setEnabled(True)
        self._status_chip.setText("● Idle")
        self._status_chip.setStyleSheet("color: #4a4d55; font-size: 12px;")
        self._log_entry("info", "Import cancelled.")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _update_timers(self) -> None:
        elapsed = time.monotonic() - self._start_time
        self._update_stat("elapsed", _fmt_time(elapsed))
        if self._done > 0 and self._total > self._done:
            rate = self._done / elapsed
            remaining = (self._total - self._done) / rate
            self._update_stat("eta", _fmt_time(remaining))

    def _log_entry(self, level: str, text: str) -> None:
        prefixes = {"ok": "[OK] ", "error": "[ERR]", "info": "[INF]"}
        colors = {"ok": "#4ec07a", "error": "#e25c5c", "info": "#b6bac3"}
        ts = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"{ts}  {prefixes.get(level, '')}  {text}")
        item.setForeground(QColor(colors.get(level, "#b6bac3")))
        self._log.addItem(item)
        self._log.scrollToBottom()
        count = self._log.count()
        self._log_count_lbl.setText(f"{count} {'entry' if count == 1 else 'entries'}")

    def _update_stat(self, name: str, value: str) -> None:
        lbl = self._find_stat(name)
        if lbl:
            lbl.setText(value)


def _fmt_time(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"
