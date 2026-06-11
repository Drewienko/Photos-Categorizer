from typing import cast

from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from photos_categorizer.db.manager import DatabaseManager
from photos_categorizer.models.photo import Photo
from photos_categorizer.ui.widgets.thumbnail import load_thumbnail

_ICON_SIZE = 180
_SIDEBAR_W = 210


class GalleryView(QWidget):
    open_detail = Signal(int)  # photo_id
    open_import = Signal()

    def __init__(self, db: DatabaseManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._photos: list[Photo] = []
        self._active_tag: str | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_sidebar())

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._subbar = self._make_subbar()
        right_layout.addWidget(self._subbar)

        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(self._make_grid())  # 0: grid
        self._content_stack.addWidget(self._make_empty_state())  # 1: empty
        right_layout.addWidget(self._content_stack, stretch=1)

        root.addWidget(right, stretch=1)

    # ── Subbar ────────────────────────────────────────────────────────────────

    def _make_subbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("subbar")
        bar.setFixedHeight(36)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        self._breadcrumb_lbl = QLabel("Library")
        self._breadcrumb_lbl.setObjectName("labelMuted")
        layout.addWidget(self._breadcrumb_lbl)

        layout.addStretch()

        self._subbar_count = QLabel("")
        self._subbar_count.setObjectName("labelMuted")
        layout.addWidget(self._subbar_count)

        return bar

    def _update_subbar(self, n: int) -> None:
        search = self._search_edit.text().strip() if hasattr(self, "_search_edit") else ""
        row = self._filter_list.currentRow()

        if search:
            crumb = f'Search · "{search}"'
        elif row == 1:
            crumb = "Library › Starred"
        elif row == 2:
            crumb = "Library › Untagged"
        elif self._active_tag:
            crumb = f"Library › {self._active_tag}"
        else:
            crumb = "Library"

        self._breadcrumb_lbl.setText(crumb)
        self._subbar_count.setText(f"{n} photo{'s' if n != 1 else ''}")

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _make_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(_SIDEBAR_W)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(8)

        import_btn = QPushButton("+ Import Folder")
        import_btn.setObjectName("btnAccent")
        import_btn.clicked.connect(self.open_import)
        layout.addWidget(import_btn)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search photos…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search_edit)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        self._filter_list = QListWidget()
        self._filter_list.setFixedHeight(90)
        for label in ("All photos", "★  Starred", "○  Untagged"):
            self._filter_list.addItem(label)
        self._filter_list.setCurrentRow(0)
        self._filter_list.currentRowChanged.connect(self._on_filter_changed)
        layout.addWidget(self._filter_list)

        tag_section = QLabel("TAGS")
        tag_section.setObjectName("labelSection")
        layout.addWidget(tag_section)

        self._tag_list = QListWidget()
        self._tag_list.currentItemChanged.connect(self._on_tag_selected)
        layout.addWidget(self._tag_list, stretch=1)

        self._status_label = QLabel("No photos")
        self._status_label.setObjectName("labelMuted")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        return sidebar

    # ── Empty state ───────────────────────────────────────────────────────────

    def _make_empty_state(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        icon_lbl = QLabel("📂")
        icon_lbl.setStyleSheet("font-size: 48px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        title = QLabel("No photos yet")
        title.setStyleSheet("font-size: 18px; font-weight: 600; color: #e6e8ec;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = QLabel("Import a folder to start tagging.\nClick any thumbnail to open it.")
        hint.setObjectName("labelMuted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        btn = QPushButton("+ Import Folder")
        btn.setObjectName("btnAccent")
        btn.clicked.connect(self.open_import)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        return w

    # ── Grid ──────────────────────────────────────────────────────────────────

    def _make_grid(self) -> QListWidget:
        self._grid = QListWidget()
        self._grid.setObjectName("galleryGrid")
        self._grid.setViewMode(QListWidget.ViewMode.IconMode)
        self._grid.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        self._grid.setResizeMode(QListView.ResizeMode.Adjust)
        self._grid.setMovement(QListWidget.Movement.Static)
        self._grid.setSpacing(6)
        self._grid.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._grid.setUniformItemSizes(True)
        self._grid.itemClicked.connect(self._on_item_clicked)
        return self._grid

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def photos(self) -> list[Photo]:
        return self._photos

    def refresh(self) -> None:
        self._photos = self._db.get_all_photos()
        self._populate_tag_list()
        self._apply_filter()
        self._content_stack.setCurrentIndex(0 if self._photos else 1)

    def add_photo(self, photo: Photo) -> None:
        """Add a single photo without full reload — called during import."""
        self._photos.insert(0, photo)
        self._add_grid_item(photo)
        self._update_status()
        self._content_stack.setCurrentIndex(0)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _populate_tag_list(self) -> None:
        self._tag_list.blockSignals(True)
        self._tag_list.clear()
        for name, count in self._db.get_all_tag_names():
            self._tag_list.addItem(f"{name}  ({count})")
        self._tag_list.blockSignals(False)

    def _apply_filter(self) -> None:
        search = self._search_edit.text().strip() if hasattr(self, "_search_edit") else ""

        if search:
            photos = self._db.search_photos(search)
        else:
            row = self._filter_list.currentRow()
            if row == 1:
                photos = self._db.get_starred_photos()
            elif row == 2:
                all_p = self._db.get_all_photos()
                tagged_ids = {
                    p.id
                    for name, _ in self._db.get_all_tag_names()
                    for p in self._db.get_photos_by_tag(name)
                }
                photos = [p for p in all_p if p.id not in tagged_ids]
            elif self._active_tag:
                photos = self._db.get_photos_by_tag(self._active_tag)
            else:
                photos = self._photos

        self._grid.clear()
        for photo in photos:
            self._add_grid_item(photo)
        n = len(photos)
        self._update_status(n)
        self._update_subbar(n)

    def _add_grid_item(self, photo: Photo) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, photo.id)
        item.setText(photo.filename)
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        pixmap = load_thumbnail(photo.id, self._db)
        if not pixmap.isNull():
            item.setIcon(QIcon(pixmap))
        self._grid.addItem(item)

    def _update_status(self, count: int | None = None) -> None:
        n = count if count is not None else len(self._photos)
        self._status_label.setText(f"{n} photo{'s' if n != 1 else ''}")

    @Slot(str)
    def _on_search_changed(self, _text: str) -> None:
        self._active_tag = None
        self._tag_list.blockSignals(True)
        self._tag_list.setCurrentRow(-1)
        self._tag_list.blockSignals(False)
        self._filter_list.blockSignals(True)
        self._filter_list.setCurrentRow(-1)
        self._filter_list.blockSignals(False)
        self._apply_filter()

    @Slot(int)
    def _on_filter_changed(self, row: int) -> None:
        if row != -1:
            self._tag_list.blockSignals(True)
            self._tag_list.setCurrentRow(-1)
            self._tag_list.blockSignals(False)
            self._active_tag = None
            self._apply_filter()

    @Slot()
    def _on_tag_selected(self) -> None:
        item = cast("QListWidgetItem | None", self._tag_list.currentItem())
        if item is None:
            self._active_tag = None
        else:
            self._active_tag = item.text().rsplit("  (", 1)[0]
            self._filter_list.blockSignals(True)
            self._filter_list.setCurrentRow(-1)
            self._filter_list.blockSignals(False)
        self._apply_filter()

    @Slot(QListWidgetItem)
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        photo_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(photo_id, int):
            self.open_detail.emit(photo_id)
