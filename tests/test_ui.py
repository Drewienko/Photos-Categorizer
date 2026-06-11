"""
UI tests using pytest-qt (qtbot fixture).
Tests widget state and signals — no rendering, no screenshots.
"""

import datetime
from collections.abc import Generator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QPushButton

from photos_categorizer.db.manager import DatabaseManager
from photos_categorizer.importer.importer import FileResult
from photos_categorizer.models.photo import Photo, TagResult

ASSETS = Path(__file__).parent / "assets"


# ── Shared helpers ─────────────────────────────────────────────────────────────


@pytest.fixture()
def db(tmp_path: Path) -> Generator[DatabaseManager, None, None]:
    manager = DatabaseManager(tmp_path / "test.db")
    yield manager
    manager.close()


def _insert_photo(
    db: DatabaseManager,
    path: Path,
    filename: str | None = None,
) -> Photo:
    """Insert a Photo with a dummy thumbnail into the DB."""
    photo = Photo(
        id=0,
        path=path,
        filename=filename or path.name,
        width=640,
        height=480,
        imported_at=datetime.datetime.now(datetime.UTC).isoformat(),
        date_taken="",
    )
    photo_id = db.save_photo(photo)
    db.save_thumbnail(photo_id, b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    result = db.get_photo_by_id(photo_id)
    assert result is not None
    return result


# ── GalleryView ────────────────────────────────────────────────────────────────


class TestGalleryView:
    def test_refresh_empty_db_shows_no_items(self, qtbot: object, db: DatabaseManager) -> None:
        from photos_categorizer.ui.gallery_view import GalleryView

        view = GalleryView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.refresh()
        assert view._grid.count() == 0

    def test_refresh_populates_grid(self, qtbot: object, db: DatabaseManager) -> None:
        from photos_categorizer.ui.gallery_view import GalleryView

        _insert_photo(db, ASSETS / "car.jpg")
        _insert_photo(db, ASSETS / "pizza.png")
        view = GalleryView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.refresh()
        assert view._grid.count() == 2

    def test_add_photo_increments_grid(self, qtbot: object, db: DatabaseManager) -> None:
        from photos_categorizer.ui.gallery_view import GalleryView

        view = GalleryView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.refresh()
        assert view._grid.count() == 0
        photo = _insert_photo(db, ASSETS / "car.jpg")
        view.add_photo(photo)
        assert view._grid.count() == 1

    def test_starred_filter_shows_only_starred(self, qtbot: object, db: DatabaseManager) -> None:
        from photos_categorizer.ui.gallery_view import GalleryView

        p1 = _insert_photo(db, ASSETS / "car.jpg", "car.jpg")
        _insert_photo(db, ASSETS / "pizza.png", "pizza.png")
        db.set_starred(p1.id, True)

        view = GalleryView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.refresh()
        assert view._grid.count() == 2

        view._filter_list.setCurrentRow(1)  # "★  Starred"
        assert view._grid.count() == 1
        item = view._grid.item(0)
        assert item is not None
        assert item.data(Qt.ItemDataRole.UserRole) == p1.id

    def test_tag_filter_narrows_results(self, qtbot: object, db: DatabaseManager) -> None:
        from photos_categorizer.ui.gallery_view import GalleryView

        p1 = _insert_photo(db, ASSETS / "car.jpg", "car.jpg")
        p2 = _insert_photo(db, ASSETS / "pizza.png", "pizza.png")
        db.save_tags(p1.id, [TagResult("vehicle", 0.9, "clip")])
        db.save_tags(p2.id, [TagResult("food", 0.9, "clip")])

        view = GalleryView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.refresh()
        assert view._grid.count() == 2

        view._active_tag = "vehicle"
        view._filter_list.clearSelection()
        view._apply_filter()
        assert view._grid.count() == 1

    def test_click_emits_open_detail(self, qtbot: object, db: DatabaseManager) -> None:
        from photos_categorizer.ui.gallery_view import GalleryView

        photo = _insert_photo(db, ASSETS / "car.jpg")
        view = GalleryView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.refresh()

        with qtbot.waitSignal(view.open_detail, timeout=1000) as blocker:  # type: ignore[attr-defined]
            view._grid.itemClicked.emit(view._grid.item(0))

        assert blocker.args[0] == photo.id

    def test_open_import_signal_on_button(self, qtbot: object, db: DatabaseManager) -> None:
        from photos_categorizer.ui.gallery_view import GalleryView

        view = GalleryView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]

        btn = view.findChild(QPushButton, "btnAccent")
        assert btn is not None
        with qtbot.waitSignal(view.open_import, timeout=1000):  # type: ignore[attr-defined]
            btn.click()


# ── DetailView ─────────────────────────────────────────────────────────────────


class TestDetailView:
    @pytest.fixture()
    def car_photo(self, db: DatabaseManager) -> Photo:
        photo = _insert_photo(db, ASSETS / "car.jpg", "car.jpg")
        db.save_tags(
            photo.id,
            [
                TagResult("vehicle", 0.92, "clip"),
                TagResult("road", 0.80, "vision"),
            ],
        )
        return photo

    def test_load_photo_sets_name(
        self, qtbot: object, db: DatabaseManager, car_photo: Photo
    ) -> None:
        from photos_categorizer.ui.detail_view import DetailView

        view = DetailView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.load_photo(car_photo.id)
        assert view._name_label.text() == "car.jpg"

    def test_load_photo_shows_tag_badges(
        self, qtbot: object, db: DatabaseManager, car_photo: Photo
    ) -> None:
        from photos_categorizer.ui.detail_view import DetailView
        from photos_categorizer.ui.widgets.tag_badge import TagBadge

        view = DetailView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.load_photo(car_photo.id)
        badges = view._tags_widget.findChildren(TagBadge)
        assert len(badges) == 2

    def test_load_nonexistent_photo_is_noop(self, qtbot: object, db: DatabaseManager) -> None:
        from photos_categorizer.ui.detail_view import DetailView

        view = DetailView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.load_photo(99999)  # should not raise
        assert view._photo is None

    def test_star_toggle_persists(
        self, qtbot: object, db: DatabaseManager, car_photo: Photo
    ) -> None:
        from photos_categorizer.ui.detail_view import DetailView

        view = DetailView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.load_photo(car_photo.id)
        assert not car_photo.starred

        view._toggle_star()

        updated = db.get_photo_by_id(car_photo.id)
        assert updated is not None and updated.starred

    def test_add_tag_creates_badge(
        self,
        qtbot: object,
        db: DatabaseManager,
        car_photo: Photo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from photos_categorizer.ui.detail_view import DetailView
        from photos_categorizer.ui.widgets.tag_badge import TagBadge

        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("newtag", True))

        view = DetailView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.load_photo(car_photo.id)
        before = len(view._tags_widget.findChildren(TagBadge))

        view._add_tag()

        after = len(view._tags_widget.findChildren(TagBadge))
        assert after == before + 1
        tags = db.get_tags_for_photo(car_photo.id)
        assert any(t.name == "newtag" and t.source == "manual" for t in tags)

    def test_remove_tag_removes_badge(
        self, qtbot: object, db: DatabaseManager, car_photo: Photo
    ) -> None:
        from photos_categorizer.ui.detail_view import DetailView
        from photos_categorizer.ui.widgets.tag_badge import TagBadge

        view = DetailView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view.load_photo(car_photo.id)
        before = len(view._tags_widget.findChildren(TagBadge))
        assert before == 2

        first_tag = db.get_tags_for_photo(car_photo.id)[0]
        view._remove_tag(first_tag.id)

        after = len(view._tags_widget.findChildren(TagBadge))
        assert after == before - 1


# ── ImportView ────────────────────────────────────────────────────────────────


class TestImportView:
    def test_no_folder_logs_error(self, qtbot: object, db: DatabaseManager) -> None:
        from photos_categorizer.ui.import_view import ImportView

        view = ImportView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view._start_import()
        assert view._log.count() == 1
        assert "valid folder" in view._log.item(0).text().lower()

    def test_nonexistent_folder_logs_error(self, qtbot: object, db: DatabaseManager) -> None:
        from photos_categorizer.ui.import_view import ImportView

        view = ImportView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view._folder_edit.setText("/nonexistent/path/that/does/not/exist")
        view._start_import()
        assert view._log.count() == 1

    def test_empty_folder_logs_no_images(
        self, qtbot: object, db: DatabaseManager, tmp_path: Path
    ) -> None:
        from photos_categorizer.ui.import_view import ImportView

        view = ImportView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view._folder_edit.setText(str(tmp_path))
        view._start_import()
        assert view._log.count() == 1
        assert "no supported" in view._log.item(0).text().lower()

    def test_go_gallery_signal_on_file_done(self, qtbot: object, db: DatabaseManager) -> None:
        """go_gallery fires when _on_file_done successfully persists a FileResult."""
        from photos_categorizer.ui.import_view import ImportView

        result = FileResult(
            path=ASSETS / "car.jpg",
            width=640,
            height=480,
            thumbnail=b"\xff\xd8\xff\xe0" + b"\x00" * 32,
            tags=[TagResult("test", 0.9, "clip")],
        )

        view = ImportView(db)
        qtbot.addWidget(view)  # type: ignore[attr-defined]
        view._total = 1  # avoid ZeroDivisionError in progress calc

        emitted: list[Photo] = []
        view.go_gallery.connect(lambda p: emitted.append(p))
        view._on_file_done(result)

        assert len(emitted) == 1
        assert emitted[0].filename == "car.jpg"


# ── MainWindow ────────────────────────────────────────────────────────────────


class TestMainWindow:
    def test_starts_on_gallery(self, qtbot: object, tmp_path: Path) -> None:
        from photos_categorizer.ui.main_window import MainWindow

        win = MainWindow(db_path=tmp_path / "app.db")
        qtbot.addWidget(win)  # type: ignore[attr-defined]
        assert win._stack.currentIndex() == 0

    def test_nav_switches_to_import(self, qtbot: object, tmp_path: Path) -> None:
        from photos_categorizer.ui.main_window import MainWindow

        win = MainWindow(db_path=tmp_path / "app.db")
        qtbot.addWidget(win)  # type: ignore[attr-defined]
        win._btn_import.click()
        assert win._stack.currentIndex() == 2

    def test_nav_back_to_gallery(self, qtbot: object, tmp_path: Path) -> None:
        from photos_categorizer.ui.main_window import MainWindow

        win = MainWindow(db_path=tmp_path / "app.db")
        qtbot.addWidget(win)  # type: ignore[attr-defined]
        win._btn_import.click()
        win._btn_gallery.click()
        assert win._stack.currentIndex() == 0

    def test_show_detail_switches_stack(self, qtbot: object, tmp_path: Path) -> None:
        from photos_categorizer.ui.main_window import MainWindow

        win = MainWindow(db_path=tmp_path / "app.db")
        qtbot.addWidget(win)  # type: ignore[attr-defined]
        photo = _insert_photo(win._db, ASSETS / "car.jpg")
        win._show_detail(photo.id)
        assert win._stack.currentIndex() == 1

    def test_import_view_back_returns_gallery(self, qtbot: object, tmp_path: Path) -> None:
        from photos_categorizer.ui.main_window import MainWindow

        win = MainWindow(db_path=tmp_path / "app.db")
        qtbot.addWidget(win)  # type: ignore[attr-defined]
        win._btn_import.click()
        assert win._stack.currentIndex() == 2
        win._detail.back.emit()  # back signal goes to gallery
        assert win._stack.currentIndex() == 0
