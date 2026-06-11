import sqlite3
from pathlib import Path
from typing import Any

from photos_categorizer.models.photo import Photo, Tag, TagResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT    NOT NULL UNIQUE,
    filename    TEXT    NOT NULL,
    width       INTEGER NOT NULL,
    height      INTEGER NOT NULL,
    imported_at TEXT    NOT NULL,
    date_taken  TEXT    NOT NULL DEFAULT '',
    starred     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    confidence  REAL    NOT NULL,
    photo_id    INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS thumbnails (
    photo_id    INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
    data        BLOB    NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tags_photo ON tags(photo_id);
CREATE INDEX IF NOT EXISTS idx_tags_name  ON tags(name);
"""

_DEFAULT_SETTINGS: dict[str, str] = {
    "engine": "clip",
    "threshold": "0.70",
    "clip_labels": (
        "nature,outdoor,people,architecture,travel,food,animals,water,urban,night,"
        "portrait,mountain,interior,macro,vehicles,landscape,beach,forest,city,sport"
    ),
    "vision_credentials": "",
}


class DatabaseManager:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(_SCHEMA)
        self._seed_settings()
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ── Settings ──────────────────────────────────────────────────────────────

    def _seed_settings(self) -> None:
        for key, value in _DEFAULT_SETTINGS.items():
            self._conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

    def get_setting(self, key: str) -> str:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else ""

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    # ── Photos ────────────────────────────────────────────────────────────────

    def save_photo(self, photo: Photo) -> int:
        cur = self._conn.execute(
            """INSERT INTO photos (path, filename, width, height, imported_at, date_taken, starred)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET
                 filename=excluded.filename, width=excluded.width,
                 height=excluded.height, imported_at=excluded.imported_at,
                 date_taken=excluded.date_taken""",
            (
                str(photo.path),
                photo.filename,
                photo.width,
                photo.height,
                photo.imported_at,
                photo.date_taken,
                int(photo.starred),
            ),
        )
        self._conn.commit()
        return cur.lastrowid or self._id_for_path(photo.path)

    def get_photo_by_id(self, photo_id: int) -> Photo | None:
        row = self._conn.execute(
            "SELECT id,path,filename,width,height,imported_at,date_taken,starred "
            "FROM photos WHERE id=?",
            (photo_id,),
        ).fetchone()
        return _row_to_photo(row) if row else None

    def get_all_photos(self) -> list[Photo]:
        rows = self._conn.execute(
            "SELECT id,path,filename,width,height,imported_at,date_taken,starred "
            "FROM photos ORDER BY imported_at DESC"
        ).fetchall()
        return [_row_to_photo(r) for r in rows]

    def get_photos_by_tag(self, tag_name: str) -> list[Photo]:
        rows = self._conn.execute(
            "SELECT DISTINCT p.id,p.path,p.filename,p.width,p.height,"
            "p.imported_at,p.date_taken,p.starred "
            "FROM photos p JOIN tags t ON t.photo_id=p.id "
            "WHERE t.name=? ORDER BY p.imported_at DESC",
            (tag_name,),
        ).fetchall()
        return [_row_to_photo(r) for r in rows]

    def get_starred_photos(self) -> list[Photo]:
        rows = self._conn.execute(
            "SELECT id,path,filename,width,height,imported_at,date_taken,starred "
            "FROM photos WHERE starred=1 ORDER BY imported_at DESC"
        ).fetchall()
        return [_row_to_photo(r) for r in rows]

    def set_starred(self, photo_id: int, starred: bool) -> None:
        self._conn.execute("UPDATE photos SET starred=? WHERE id=?", (int(starred), photo_id))
        self._conn.commit()

    # ── Tags ──────────────────────────────────────────────────────────────────

    def save_tags(self, photo_id: int, results: list[TagResult]) -> list[Tag]:
        self._conn.execute("DELETE FROM tags WHERE photo_id=? AND source != 'manual'", (photo_id,))
        tags: list[Tag] = []
        for r in results:
            cur = self._conn.execute(
                "INSERT INTO tags (name, source, confidence, photo_id) VALUES (?,?,?,?)",
                (r.label, r.source, r.confidence, photo_id),
            )
            tags.append(
                Tag(id=cur.lastrowid or 0, name=r.label, source=r.source, confidence=r.confidence)
            )
        self._conn.commit()
        return tags

    def add_tag(self, photo_id: int, label: str) -> Tag:
        cur = self._conn.execute(
            "INSERT INTO tags (name, source, confidence, photo_id) VALUES (?,?,?,?)",
            (label, "manual", 1.0, photo_id),
        )
        self._conn.commit()
        return Tag(id=cur.lastrowid or 0, name=label, source="manual", confidence=1.0)

    def delete_tag(self, tag_id: int) -> None:
        self._conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))
        self._conn.commit()

    def get_tags_for_photo(self, photo_id: int) -> list[Tag]:
        rows = self._conn.execute(
            "SELECT id,name,source,confidence FROM tags WHERE photo_id=? ORDER BY confidence DESC",
            (photo_id,),
        ).fetchall()
        return [Tag(id=r[0], name=r[1], source=r[2], confidence=r[3]) for r in rows]

    def get_all_tag_names(self) -> list[tuple[str, int]]:
        """Returns (tag_name, photo_count) sorted by count desc."""
        rows = self._conn.execute(
            "SELECT name, COUNT(DISTINCT photo_id) as cnt FROM tags GROUP BY name ORDER BY cnt DESC"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def count_untagged(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM photos "
            "WHERE id NOT IN (SELECT DISTINCT photo_id FROM tags)"
        ).fetchone()
        return int(row[0]) if row else 0

    def search_photos(self, query: str) -> list[Photo]:
        like = f"%{query.lower()}%"
        rows = self._conn.execute(
            "SELECT DISTINCT p.id,p.path,p.filename,p.width,p.height,"
            "p.imported_at,p.date_taken,p.starred "
            "FROM photos p LEFT JOIN tags t ON t.photo_id=p.id "
            "WHERE LOWER(p.filename) LIKE ? OR LOWER(t.name) LIKE ? "
            "ORDER BY p.imported_at DESC",
            (like, like),
        ).fetchall()
        return [_row_to_photo(r) for r in rows]

    # ── Thumbnails ────────────────────────────────────────────────────────────

    def save_thumbnail(self, photo_id: int, data: bytes) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO thumbnails (photo_id, data) VALUES (?,?)",
            (photo_id, data),
        )
        self._conn.commit()

    def get_thumbnail(self, photo_id: int) -> bytes | None:
        row = self._conn.execute(
            "SELECT data FROM thumbnails WHERE photo_id=?", (photo_id,)
        ).fetchone()
        return bytes(row[0]) if row else None

    # ── CSV export ────────────────────────────────────────────────────────────

    def export_csv(self, out_path: Path) -> None:
        import csv

        rows = self._conn.execute(
            "SELECT p.path, t.name, t.confidence, t.source "
            "FROM tags t JOIN photos p ON p.id=t.photo_id ORDER BY p.path, t.confidence DESC"
        ).fetchall()
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["photo_path", "tag", "confidence", "source"])
            writer.writerows(rows)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _id_for_path(self, path: Path) -> int:
        row = self._conn.execute("SELECT id FROM photos WHERE path=?", (str(path),)).fetchone()
        return row[0] if row else 0


def _row_to_photo(row: Any) -> Photo:  # noqa: ANN401
    return Photo(
        id=int(row[0]),
        path=Path(str(row[1])),
        filename=str(row[2]),
        width=int(row[3]),
        height=int(row[4]),
        imported_at=str(row[5]),
        date_taken=str(row[6]),
        starred=bool(row[7]),
    )
