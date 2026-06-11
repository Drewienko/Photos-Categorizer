from pathlib import Path

import pytest

from photos_categorizer.db.manager import DatabaseManager
from photos_categorizer.models.photo import Photo, TagResult


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(tmp_path / "test.db")


@pytest.fixture
def sample_photo() -> Photo:
    return Photo(
        id=0,
        path=Path("/tmp/dog.jpg"),
        filename="dog.jpg",
        width=1920,
        height=1080,
        imported_at="2026-06-07T12:00:00",
        date_taken="2026-06-01",
    )


# ── Schema ────────────────────────────────────────────────────────────────────


def test_schema_creates_tables(db: DatabaseManager) -> None:
    tables = {
        row[0]
        for row in db._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"photos", "tags", "thumbnails", "settings"}.issubset(tables)


# ── Settings ──────────────────────────────────────────────────────────────────


def test_default_settings_seeded(db: DatabaseManager) -> None:
    assert db.get_setting("engine") == "clip"
    assert db.get_setting("threshold") == "0.70"
    assert db.get_setting("clip_labels") != ""


def test_set_and_get_setting(db: DatabaseManager) -> None:
    db.set_setting("engine", "vision")
    assert db.get_setting("engine") == "vision"


def test_get_missing_setting_returns_empty(db: DatabaseManager) -> None:
    assert db.get_setting("nonexistent") == ""


# ── Photos ────────────────────────────────────────────────────────────────────


def test_save_and_get_photo(db: DatabaseManager, sample_photo: Photo) -> None:
    photo_id = db.save_photo(sample_photo)
    assert photo_id > 0

    fetched = db.get_photo_by_id(photo_id)
    assert fetched is not None
    assert fetched.filename == "dog.jpg"
    assert fetched.width == 1920
    assert fetched.path == Path("/tmp/dog.jpg")


def test_save_photo_upserts_on_duplicate_path(db: DatabaseManager, sample_photo: Photo) -> None:
    id1 = db.save_photo(sample_photo)
    id2 = db.save_photo(sample_photo)
    assert id1 == id2
    assert len(db.get_all_photos()) == 1


def test_get_photo_by_id_missing_returns_none(db: DatabaseManager) -> None:
    assert db.get_photo_by_id(999) is None


def test_get_all_photos(db: DatabaseManager, sample_photo: Photo) -> None:
    db.save_photo(sample_photo)
    photos = db.get_all_photos()
    assert len(photos) == 1


def test_set_starred(db: DatabaseManager, sample_photo: Photo) -> None:
    photo_id = db.save_photo(sample_photo)
    db.set_starred(photo_id, True)
    assert db.get_photo_by_id(photo_id).starred is True  # type: ignore[union-attr]
    db.set_starred(photo_id, False)
    assert db.get_photo_by_id(photo_id).starred is False  # type: ignore[union-attr]


def test_get_starred_photos(db: DatabaseManager, sample_photo: Photo) -> None:
    photo_id = db.save_photo(sample_photo)
    assert db.get_starred_photos() == []
    db.set_starred(photo_id, True)
    assert len(db.get_starred_photos()) == 1


# ── Tags ──────────────────────────────────────────────────────────────────────


def test_save_and_get_tags(db: DatabaseManager, sample_photo: Photo) -> None:
    photo_id = db.save_photo(sample_photo)
    results = [
        TagResult(label="dog", confidence=0.95, source="clip"),
        TagResult(label="outdoor", confidence=0.80, source="clip"),
    ]
    tags = db.save_tags(photo_id, results)
    assert len(tags) == 2
    assert {t.name for t in tags} == {"dog", "outdoor"}

    fetched = db.get_tags_for_photo(photo_id)
    assert len(fetched) == 2
    assert fetched[0].confidence >= fetched[1].confidence  # sorted desc


def test_save_tags_replaces_non_manual(db: DatabaseManager, sample_photo: Photo) -> None:
    photo_id = db.save_photo(sample_photo)
    db.save_tags(photo_id, [TagResult("dog", 0.9, "clip")])
    db.save_tags(photo_id, [TagResult("cat", 0.8, "clip")])
    tags = db.get_tags_for_photo(photo_id)
    assert len(tags) == 1
    assert tags[0].name == "cat"


def test_save_tags_preserves_manual(db: DatabaseManager, sample_photo: Photo) -> None:
    photo_id = db.save_photo(sample_photo)
    db.save_tags(photo_id, [TagResult("dog", 0.9, "clip")])
    db.add_tag(photo_id, "my-tag")
    db.save_tags(photo_id, [TagResult("cat", 0.8, "clip")])
    names = {t.name for t in db.get_tags_for_photo(photo_id)}
    assert "my-tag" in names
    assert "dog" not in names


def test_add_and_delete_tag(db: DatabaseManager, sample_photo: Photo) -> None:
    photo_id = db.save_photo(sample_photo)
    tag = db.add_tag(photo_id, "manual-label")
    assert tag.source == "manual"
    assert tag.confidence == 1.0

    db.delete_tag(tag.id)
    assert db.get_tags_for_photo(photo_id) == []


def test_get_photos_by_tag(db: DatabaseManager, sample_photo: Photo) -> None:
    photo_id = db.save_photo(sample_photo)
    db.save_tags(photo_id, [TagResult("dog", 0.9, "clip")])
    assert len(db.get_photos_by_tag("dog")) == 1
    assert db.get_photos_by_tag("cat") == []


def test_get_all_tag_names(db: DatabaseManager, sample_photo: Photo) -> None:
    photo_id = db.save_photo(sample_photo)
    db.save_tags(
        photo_id,
        [
            TagResult("dog", 0.9, "clip"),
            TagResult("outdoor", 0.7, "clip"),
        ],
    )
    names = [name for name, _ in db.get_all_tag_names()]
    assert "dog" in names
    assert "outdoor" in names


# ── Thumbnails ────────────────────────────────────────────────────────────────


def test_save_and_get_thumbnail(db: DatabaseManager, sample_photo: Photo) -> None:
    photo_id = db.save_photo(sample_photo)
    data = b"\xff\xd8\xff" + b"\x00" * 100  # fake JPEG bytes
    db.save_thumbnail(photo_id, data)
    assert db.get_thumbnail(photo_id) == data


def test_get_thumbnail_missing_returns_none(db: DatabaseManager) -> None:
    assert db.get_thumbnail(999) is None


def test_save_thumbnail_overwrites(db: DatabaseManager, sample_photo: Photo) -> None:
    photo_id = db.save_photo(sample_photo)
    db.save_thumbnail(photo_id, b"old")
    db.save_thumbnail(photo_id, b"new")
    assert db.get_thumbnail(photo_id) == b"new"


def test_get_photos_by_tag_no_match(db: DatabaseManager) -> None:
    assert db.get_photos_by_tag("nonexistent_tag") == []


# ── CSV export ────────────────────────────────────────────────────────────────


def test_export_csv(db: DatabaseManager, sample_photo: Photo, tmp_path: Path) -> None:
    photo_id = db.save_photo(sample_photo)
    db.save_tags(photo_id, [TagResult("dog", 0.95, "clip")])

    out = tmp_path / "export.csv"
    db.export_csv(out)

    lines = out.read_text().splitlines()
    assert lines[0] == "photo_path,tag,confidence,source"
    assert "dog" in lines[1]
    assert "0.95" in lines[1]
