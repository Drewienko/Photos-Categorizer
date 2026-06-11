from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from photos_categorizer.db.manager import DatabaseManager
from photos_categorizer.importer.importer import FileResult
from photos_categorizer.importer.worker import ImportTask
from photos_categorizer.models.photo import Photo
from photos_categorizer.tagging.engine import TaggingEngine
from photos_categorizer.ui.widgets.tag_badge import TagBadge
from photos_categorizer.ui.widgets.thumbnail import load_thumbnail

_SIDEBAR_W = 300
_FILMSTRIP_H = 88
_THUMB_W = 80
_THUMB_H = 60


class DetailView(QWidget):
    back = Signal()
    open_detail = Signal(int)  # photo_id (prev/next nav)

    def __init__(self, db: DatabaseManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._photo: Photo | None = None
        self._photos: list[Photo] = []
        self._reanalyze_photo_id: int = -1
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_topbar())

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)

        # Left column: image + filmstrip
        left_col = QWidget()
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._img_label.setStyleSheet("background-color: #0a0b0d;")

        img_scroll = QScrollArea()
        img_scroll.setWidget(self._img_label)
        img_scroll.setWidgetResizable(True)
        img_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_layout.addWidget(img_scroll, stretch=1)

        self._filmstrip = self._make_filmstrip()
        left_layout.addWidget(self._filmstrip)

        self._splitter.addWidget(left_col)
        self._splitter.addWidget(self._make_sidebar())
        self._splitter.setSizes([900, _SIDEBAR_W])

        root.addWidget(self._splitter, stretch=1)

    def _make_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("detailBar")
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        back_btn = QPushButton("← Gallery")
        back_btn.setObjectName("navTab")
        back_btn.clicked.connect(self.back)
        layout.addWidget(back_btn)

        self._breadcrumb = QLabel()
        self._breadcrumb.setObjectName("labelMuted")
        layout.addWidget(self._breadcrumb, stretch=1)

        self._counter_lbl = QLabel()
        self._counter_lbl.setObjectName("labelMuted")
        self._counter_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._counter_lbl)

        self._prev_btn = QPushButton("← Prev")
        self._next_btn = QPushButton("Next →")
        self._prev_btn.setToolTip("Previous photo")
        self._next_btn.setToolTip("Next photo")
        self._prev_btn.clicked.connect(self._go_prev)
        self._next_btn.clicked.connect(self._go_next)
        layout.addWidget(self._prev_btn)
        layout.addWidget(self._next_btn)

        self._star_btn = QPushButton("☆ Star")
        self._star_btn.clicked.connect(self._toggle_star)
        layout.addWidget(self._star_btn)

        return bar

    def _make_filmstrip(self) -> QListWidget:
        strip = QListWidget()
        strip.setObjectName("filmstrip")
        strip.setViewMode(QListWidget.ViewMode.IconMode)
        strip.setIconSize(QSize(_THUMB_W, _THUMB_H))
        strip.setFixedHeight(_FILMSTRIP_H)
        strip.setFlow(QListWidget.Flow.LeftToRight)
        strip.setResizeMode(QListView.ResizeMode.Fixed)
        strip.setMovement(QListWidget.Movement.Static)
        strip.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        strip.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        strip.setSpacing(3)
        strip.setWrapping(False)
        strip.itemClicked.connect(self._on_filmstrip_clicked)
        return strip

    def _make_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(_SIDEBAR_W)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self._name_label = QLabel()
        self._name_label.setObjectName("labelTitle")
        self._name_label.setWordWrap(True)
        self._name_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #e6e8ec;")
        layout.addWidget(self._name_label)

        self._meta_label = QLabel()
        self._meta_label.setObjectName("labelMeta")
        self._meta_label.setWordWrap(True)
        layout.addWidget(self._meta_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        tag_header = QHBoxLayout()
        tags_lbl = QLabel("AI TAGS")
        tags_lbl.setObjectName("labelSection")
        tag_header.addWidget(tags_lbl, stretch=1)
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_tag)
        tag_header.addWidget(add_btn)
        self._reanalyze_btn = QPushButton("Re-analyze")
        self._reanalyze_btn.setToolTip("Re-run AI tagging with current engine")
        self._reanalyze_btn.clicked.connect(self._reanalyze)
        tag_header.addWidget(self._reanalyze_btn)
        layout.addLayout(tag_header)

        self._model_pill = QLabel()
        self._model_pill.setStyleSheet(
            "color: #b6bac3; font-size: 11px;"
            "background: #1c1f24; border: 1px solid #2a2d35;"
            "border-radius: 10px; padding: 2px 8px;"
        )
        layout.addWidget(self._model_pill)

        self._tags_scroll = QScrollArea()
        self._tags_scroll.setWidgetResizable(True)
        self._tags_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._tags_widget = QWidget()
        self._tags_layout = QVBoxLayout(self._tags_widget)
        self._tags_layout.setContentsMargins(0, 0, 0, 0)
        self._tags_layout.setSpacing(4)
        self._tags_layout.addStretch()
        self._tags_scroll.setWidget(self._tags_widget)
        layout.addWidget(self._tags_scroll, stretch=1)

        return sidebar

    # ── Public ────────────────────────────────────────────────────────────────

    def load_photo(self, photo_id: int, all_photos: list[Photo] | None = None) -> None:
        photo = self._db.get_photo_by_id(photo_id)
        if photo is None:
            return
        self._photo = photo
        if all_photos is not None:
            self._photos = all_photos
            self._load_filmstrip()

        self._breadcrumb.setText(photo.filename)
        self._name_label.setText(photo.filename)
        self._meta_label.setText(
            f"{photo.width} × {photo.height} px\n"
            f"{Path(str(photo.path)).stat().st_size // 1024} KB\n"
            f"Imported: {photo.imported_at[:10]}"
        )
        star = "★" if photo.starred else "☆"
        self._star_btn.setText(f"{star} Star")

        self._load_image(photo)
        self._load_tags(photo_id)
        self._update_nav_buttons()
        self._update_filmstrip_selection()
        self._update_model_pill()

    def _update_model_pill(self) -> None:
        engine = self._db.get_setting("engine")
        if engine == "vision":
            self._model_pill.setText("Google Vision · cloud")
        else:
            self._model_pill.setText("CLIP ViT-B/32 · local")

    # ── Image loading ─────────────────────────────────────────────────────────

    def _load_image(self, photo: Photo) -> None:
        pixmap = QPixmap(str(photo.path))
        if pixmap.isNull():
            self._img_label.setText("Cannot load image")
            return
        self._img_label.setPixmap(
            pixmap.scaled(
                self._img_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._photo and not self._img_label.pixmap().isNull():
            self._load_image(self._photo)

    # ── Filmstrip ─────────────────────────────────────────────────────────────

    def _load_filmstrip(self) -> None:
        self._filmstrip.clear()
        for photo in self._photos:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, photo.id)
            pixmap = load_thumbnail(photo.id, self._db)
            if not pixmap.isNull():
                item.setIcon(QIcon(pixmap.scaled(
                    QSize(_THUMB_W, _THUMB_H),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )))
            self._filmstrip.addItem(item)
        self._update_filmstrip_selection()

    def _update_filmstrip_selection(self) -> None:
        if self._photo is None:
            return
        idx = self._current_index()
        if idx >= 0:
            item = self._filmstrip.item(idx)
            if item:
                self._filmstrip.setCurrentItem(item)
                self._filmstrip.scrollToItem(item)
        # update counter
        total = len(self._photos)
        if total > 0 and idx >= 0:
            self._counter_lbl.setText(f"{idx + 1} / {total}")
        else:
            self._counter_lbl.setText("")

    @Slot(QListWidgetItem)
    def _on_filmstrip_clicked(self, item: QListWidgetItem) -> None:
        photo_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(photo_id, int):
            self.open_detail.emit(photo_id)

    # ── Tags ──────────────────────────────────────────────────────────────────

    def _load_tags(self, photo_id: int) -> None:
        while self._tags_layout.count() > 1:  # keep the stretch
            item = self._tags_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.hide()
                    w.setParent(None)  # type: ignore[call-overload]

        tags = self._db.get_tags_for_photo(photo_id)
        for tag in tags:
            badge = TagBadge(tag)
            badge.removed.connect(self._remove_tag)
            self._tags_layout.insertWidget(self._tags_layout.count() - 1, badge)

    @Slot()
    def _add_tag(self) -> None:
        if self._photo is None:
            return
        text, ok = QInputDialog.getText(self, "Add Tag", "Tag name:")
        if ok and text.strip():
            self._db.add_tag(self._photo.id, text.strip().lower())
            self._load_tags(self._photo.id)

    @Slot(int)
    def _remove_tag(self, tag_id: int) -> None:
        self._db.delete_tag(tag_id)
        if self._photo:
            self._load_tags(self._photo.id)

    @Slot()
    def _reanalyze(self) -> None:
        if self._photo is None:
            return
        engine = self._build_engine()
        if engine is None:
            return

        self._reanalyze_photo_id = self._photo.id
        photo_path = self._photo.path
        self._reanalyze_btn.setEnabled(False)
        self._reanalyze_btn.setText("Analyzing…")

        task = ImportTask(photo_path, engine)
        task.signals.file_done.connect(self._on_reanalyzed)
        task.signals.error.connect(self._on_reanalyze_error)
        QThreadPool.globalInstance().start(task)

    def _build_engine(self) -> TaggingEngine | None:
        raw_engine = self._db.get_setting("engine")
        threshold = float(self._db.get_setting("threshold") or "0.70")
        if raw_engine == "vision":
            creds = self._db.get_setting("vision_credentials")
            if not creds or not Path(creds).exists():
                QMessageBox.warning(
                    self, "No credentials", "Configure Google Vision credentials in Settings."
                )
                return None
            from photos_categorizer.tagging.vision_engine import GoogleVisionEngine

            return GoogleVisionEngine(credentials_path=creds, threshold=threshold)
        else:
            raw = self._db.get_setting("clip_labels")
            labels = [s.strip() for s in raw.split(",") if s.strip()]
            from photos_categorizer.tagging.clip_engine import CLIPEngine

            return CLIPEngine(labels=labels, threshold=threshold)

    @Slot(object)
    def _on_reanalyzed(self, result: object) -> None:
        self._reanalyze_btn.setEnabled(True)
        self._reanalyze_btn.setText("Re-analyze")
        if not isinstance(result, FileResult):
            return
        photo_id = self._reanalyze_photo_id
        self._db.save_tags(photo_id, result.tags)
        if self._photo and self._photo.id == photo_id:
            self._load_tags(photo_id)

    @Slot(str)
    def _on_reanalyze_error(self, msg: str) -> None:
        self._reanalyze_btn.setEnabled(True)
        self._reanalyze_btn.setText("Re-analyze")
        QMessageBox.critical(self, "Re-analyze failed", msg)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _current_index(self) -> int:
        if self._photo is None or not self._photos:
            return -1
        ids = [p.id for p in self._photos]
        try:
            return ids.index(self._photo.id)
        except ValueError:
            return -1

    def _update_nav_buttons(self) -> None:
        idx = self._current_index()
        self._prev_btn.setEnabled(idx > 0)
        self._next_btn.setEnabled(0 <= idx < len(self._photos) - 1)

    @Slot()
    def _go_prev(self) -> None:
        idx = self._current_index()
        if idx > 0:
            self.open_detail.emit(self._photos[idx - 1].id)

    @Slot()
    def _go_next(self) -> None:
        idx = self._current_index()
        if 0 <= idx < len(self._photos) - 1:
            self.open_detail.emit(self._photos[idx + 1].id)

    @Slot()
    def _toggle_star(self) -> None:
        if self._photo is None:
            return
        new_val = not self._photo.starred
        self._db.set_starred(self._photo.id, new_val)
        self._photo = self._db.get_photo_by_id(self._photo.id)
        if self._photo:
            star = "★" if self._photo.starred else "☆"
            self._star_btn.setText(f"{star} Star")
