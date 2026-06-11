"""
Tests for PhotoImporter and import pipeline.
Uses real images from tests/assets/, real ffmpeg calls, but a mock TaggingEngine.
"""

import shutil
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from photos_categorizer.importer.importer import (
    FileResult,
    PhotoImporter,
    process_file,
    scan_folder,
)
from photos_categorizer.models.photo import TagResult

ASSETS = Path(__file__).parent / "assets"


def _make_engine(results: list[TagResult] | None = None) -> MagicMock:
    engine = MagicMock()
    engine.analyze.return_value = (
        results if results is not None else [TagResult(label="test", confidence=0.9, source="clip")]
    )
    return engine


# ── scan_folder ───────────────────────────────────────────────────────────────


def test_scan_folder_finds_images(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").touch()
    (tmp_path / "b.png").touch()
    (tmp_path / "readme.txt").touch()
    found = scan_folder(tmp_path)
    assert len(found) == 2
    assert all(p.suffix.lower() in {".jpg", ".png"} for p in found)


def test_scan_folder_recursive(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "top.jpg").touch()
    (sub / "nested.jpg").touch()
    found = scan_folder(tmp_path)
    assert len(found) == 2


def test_scan_folder_skips_non_images(tmp_path: Path) -> None:
    (tmp_path / "doc.pdf").touch()
    (tmp_path / "data.csv").touch()
    assert scan_folder(tmp_path) == []


def test_scan_folder_empty(tmp_path: Path) -> None:
    assert scan_folder(tmp_path) == []


# ── process_file ──────────────────────────────────────────────────────────────


@pytest.fixture()
def dog_image() -> Path:
    p = ASSETS / "2 dogos.jpg"
    if not p.exists():
        pytest.skip("2 dogos.jpg not found in tests/assets/")
    return p


def test_process_file_returns_file_result(dog_image: Path) -> None:
    engine = _make_engine()
    result = process_file(dog_image, engine)
    assert isinstance(result, FileResult)
    assert result.path == dog_image
    assert result.width > 0
    assert result.height > 0
    assert len(result.thumbnail) > 0
    assert result.tags == [TagResult(label="test", confidence=0.9, source="clip")]


def test_process_file_thumbnail_is_jpeg(dog_image: Path) -> None:
    result = process_file(dog_image, _make_engine())
    # JPEG magic bytes: FF D8 FF
    assert result.thumbnail[:3] == b"\xff\xd8\xff"


def test_process_file_calls_engine(dog_image: Path) -> None:
    engine = _make_engine()
    process_file(dog_image, engine)
    engine.analyze.assert_called_once_with(dog_image)


def test_process_file_dimensions_correct(dog_image: Path) -> None:
    result = process_file(dog_image, _make_engine())
    assert result.width >= 1
    assert result.height >= 1


# ── PhotoImporter.persist ─────────────────────────────────────────────────────


@pytest.fixture()
def db(tmp_path: Path) -> Generator[object, None, None]:
    from photos_categorizer.db.manager import DatabaseManager

    manager = DatabaseManager(tmp_path / "test.db")
    yield manager
    manager.close()


def test_persist_saves_photo(db: object, dog_image: Path) -> None:
    result = process_file(dog_image, _make_engine())
    importer = PhotoImporter(db)  # type: ignore[arg-type]
    photo, tags = importer.persist(result)

    assert photo.id > 0
    assert photo.filename == dog_image.name
    assert photo.width > 0
    assert len(tags) == 1
    assert tags[0].name == "test"


def test_persist_saves_thumbnail(db: object, dog_image: Path) -> None:
    result = process_file(dog_image, _make_engine())
    importer = PhotoImporter(db)  # type: ignore[arg-type]
    photo, _ = importer.persist(result)

    thumb = db.get_thumbnail(photo.id)  # type: ignore[attr-defined]
    assert thumb is not None
    assert len(thumb) > 0


def test_persist_reimport_upserts(db: object, dog_image: Path) -> None:
    """Re-importing same file updates rather than duplicating."""
    result = process_file(dog_image, _make_engine())
    importer = PhotoImporter(db)  # type: ignore[arg-type]
    photo1, _ = importer.persist(result)
    photo2, _ = importer.persist(result)

    all_photos = db.get_all_photos()  # type: ignore[attr-defined]
    assert len([p for p in all_photos if p.filename == dog_image.name]) == 1
    assert photo1.id == photo2.id


# ── ImportSession (Qt required) ───────────────────────────────────────────────


@pytest.fixture()
def app(qapp: QApplication) -> QApplication:
    return qapp


def test_import_session_all_finished(app: QApplication, tmp_path: Path) -> None:
    from photos_categorizer.importer.worker import ImportSession

    shutil.copy(ASSETS / "car.jpg", tmp_path / "car.jpg")

    engine = _make_engine()
    session = ImportSession()

    finished = []
    results: list[object] = []
    session.file_done.connect(lambda r: results.append(r))
    session.all_finished.connect(lambda: finished.append(True))

    total = session.start(tmp_path, engine)
    assert total == 1

    loop = QEventLoop()
    session.all_finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert len(finished) == 1
    assert len(results) == 1
    assert isinstance(results[0], FileResult)


def test_import_session_empty_folder(app: QApplication, tmp_path: Path) -> None:
    from photos_categorizer.importer.worker import ImportSession

    engine = _make_engine()
    session = ImportSession()

    finished = []
    session.all_finished.connect(lambda: finished.append(True))

    total = session.start(tmp_path, engine)
    assert total == 0
    assert len(finished) == 1  # emitted immediately for empty folder


def test_import_session_multiple_files(app: QApplication, tmp_path: Path) -> None:
    from photos_categorizer.importer.worker import ImportSession

    for asset in ASSETS.iterdir():
        if asset.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            shutil.copy(asset, tmp_path / asset.name)

    engine = _make_engine()
    session = ImportSession()

    results: list[object] = []
    errors: list[str] = []
    finished = []
    session.file_done.connect(lambda r: results.append(r))
    session.error.connect(lambda e: errors.append(e))
    session.all_finished.connect(lambda: finished.append(True))

    total = session.start(tmp_path, engine)
    assert total > 0

    loop = QEventLoop()
    session.all_finished.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()

    assert len(finished) == 1
    assert len(results) + len(errors) == total


# ── process_file error handling ───────────────────────────────────────────────


def test_process_file_bad_file_raises(tmp_path: Path) -> None:
    """Non-image file causes ffprobe to raise ffmpeg.Error."""
    import ffmpeg as _ffmpeg

    bad = tmp_path / "bad.jpg"
    bad.write_text("this is not an image")
    with pytest.raises(_ffmpeg.Error):
        process_file(bad, _make_engine())


# ── PhotoImporter.persist — zero tags ────────────────────────────────────────


def test_persist_with_no_tags(db: object, dog_image: Path) -> None:
    result = process_file(dog_image, _make_engine(results=[]))
    importer = PhotoImporter(db)  # type: ignore[arg-type]
    photo, tags = importer.persist(result)

    assert photo.id > 0
    assert tags == []
    assert db.get_tags_for_photo(photo.id) == []  # type: ignore[attr-defined]


# ── ImportSession error paths ──────────────────────────────────────────────────


def test_import_session_error_fires_and_finishes(app: QApplication, tmp_path: Path) -> None:
    """Engine that always raises → error signal fires, all_finished still emits."""
    from photos_categorizer.importer.worker import ImportSession

    shutil.copy(ASSETS / "car.jpg", tmp_path / "car.jpg")

    engine = _make_engine()
    engine.analyze.side_effect = RuntimeError("engine exploded")

    session = ImportSession()
    results: list[object] = []
    errors: list[str] = []
    finished: list[bool] = []
    session.file_done.connect(lambda r: results.append(r))
    session.error.connect(lambda e: errors.append(e))
    session.all_finished.connect(lambda: finished.append(True))

    total = session.start(tmp_path, engine)
    assert total == 1

    loop = QEventLoop()
    session.all_finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert len(finished) == 1
    assert len(results) == 0
    assert len(errors) == 1
    assert "car.jpg" in errors[0]


def test_import_session_mixed_done_and_error(app: QApplication, tmp_path: Path) -> None:
    """Some tasks succeed, some error — total count still reaches all_finished."""
    from photos_categorizer.importer.worker import ImportSession

    for asset in ASSETS.iterdir():
        if asset.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            shutil.copy(asset, tmp_path / asset.name)

    call_count = 0

    def alternating_analyze(path: Path) -> list[TagResult]:
        nonlocal call_count
        call_count += 1
        if call_count % 2 == 0:
            raise RuntimeError("alternating failure")
        return [TagResult(label="test", confidence=0.9, source="clip")]

    engine = _make_engine()
    engine.analyze.side_effect = alternating_analyze

    session = ImportSession()
    results: list[object] = []
    errors: list[str] = []
    finished: list[bool] = []
    session.file_done.connect(lambda r: results.append(r))
    session.error.connect(lambda e: errors.append(e))
    session.all_finished.connect(lambda: finished.append(True))

    total = session.start(tmp_path, engine)
    assert total > 0

    loop = QEventLoop()
    session.all_finished.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()

    assert len(finished) == 1
    assert len(results) + len(errors) == total
    assert len(errors) > 0
    assert len(results) > 0
