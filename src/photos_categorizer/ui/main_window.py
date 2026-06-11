from pathlib import Path

from PySide6.QtCore import QStandardPaths, Slot
from PySide6.QtGui import QCloseEvent, QPixmapCache
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from photos_categorizer.db.manager import DatabaseManager
from photos_categorizer.models.photo import Photo
from photos_categorizer.ui.detail_view import DetailView
from photos_categorizer.ui.gallery_view import GalleryView
from photos_categorizer.ui.import_view import ImportView
from photos_categorizer.ui.settings_dialog import SettingsDialog

_IDX_GALLERY = 0
_IDX_DETAIL = 1
_IDX_IMPORT = 2


class MainWindow(QMainWindow):
    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        QPixmapCache.setCacheLimit(102400)  # 100 MB in KB

        if db_path is None:
            db_path = (
                Path(
                    QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
                )
                / "app.db"
            )
        self._db = DatabaseManager(db_path)

        self.setWindowTitle("Photos Categorizer")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._navbar = self._make_navbar()
        root.addWidget(self._navbar)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, stretch=1)

        self._gallery = GalleryView(self._db)
        self._detail = DetailView(self._db)
        self._import = ImportView(self._db)

        self._stack.addWidget(self._gallery)  # 0
        self._stack.addWidget(self._detail)  # 1
        self._stack.addWidget(self._import)  # 2

        self._connect_signals()
        self._gallery.refresh()
        self._switch_to(_IDX_GALLERY)

    # ── Navbar ────────────────────────────────────────────────────────────────

    def _make_navbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("navbar")
        bar.setFixedHeight(44)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(4)

        logo = QLabel("TAGGER")
        logo.setStyleSheet(
            "font-weight: 700; font-size: 15px; color: #e6e8ec; letter-spacing: 1px;"
        )
        layout.addWidget(logo)

        layout.addSpacing(12)

        self._btn_gallery = self._nav_btn("Gallery")
        self._btn_import = self._nav_btn("Import")
        self._btn_gallery.clicked.connect(lambda: self._switch_to(_IDX_GALLERY))
        self._btn_import.clicked.connect(lambda: self._switch_to(_IDX_IMPORT))
        layout.addWidget(self._btn_gallery)
        layout.addWidget(self._btn_import)

        layout.addStretch(1)

        self._stats_label = QLabel()
        self._stats_label.setObjectName("labelMuted")
        layout.addWidget(self._stats_label)

        layout.addStretch(1)

        export_btn = QPushButton("↓ Export CSV")
        export_btn.setObjectName("navTab")
        export_btn.clicked.connect(self._export_csv)
        layout.addWidget(export_btn)

        settings_btn = QPushButton("⚙ Settings")
        settings_btn.setObjectName("navTab")
        settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(settings_btn)

        return bar

    def _nav_btn(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("navTab")
        btn.setCheckable(False)
        return btn

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._gallery.open_detail.connect(self._show_detail)
        self._gallery.open_import.connect(lambda: self._switch_to(_IDX_IMPORT))

        self._detail.back.connect(lambda: self._switch_to(_IDX_GALLERY))
        self._detail.open_detail.connect(self._show_detail)

        self._import.go_gallery.connect(self._on_photo_imported)
        self._import.view_results.connect(lambda: self._switch_to(_IDX_GALLERY))

    # ── Navigation ────────────────────────────────────────────────────────────

    def _switch_to(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._btn_gallery.setProperty("active", index == _IDX_GALLERY)
        self._btn_import.setProperty("active", index == _IDX_IMPORT)
        # force style refresh (Qt doesn't re-evaluate dynamic properties automatically)
        for btn in (self._btn_gallery, self._btn_import):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if index == _IDX_GALLERY:
            self._gallery.refresh()
            self._update_stats()

    @Slot(int)
    def _show_detail(self, photo_id: int) -> None:
        all_photos = self._gallery.photos  # share current filtered list for prev/next
        self._detail.load_photo(photo_id, all_photos)
        self._switch_to(_IDX_DETAIL)

    @Slot(Photo)
    def _on_photo_imported(self, photo: Photo) -> None:
        self._gallery.add_photo(photo)
        self._update_stats()

    def _update_stats(self) -> None:
        n_photos = len(self._db.get_all_photos())
        n_tags = len(self._db.get_all_tag_names())
        n_untagged = self._db.count_untagged()
        parts = [f"{n_photos} photos", f"{n_tags} tags"]
        if n_untagged:
            parts.append(f"{n_untagged} untagged")
        self._stats_label.setText("  ·  ".join(parts))

    @Slot()
    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export tags as CSV", "tags.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            self._db.export_csv(Path(path))
            QMessageBox.information(self, "Export", f"Saved to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    @Slot()
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self._db, self)
        dlg.exec()

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent) -> None:
        self._db.close()
        super().closeEvent(event)
