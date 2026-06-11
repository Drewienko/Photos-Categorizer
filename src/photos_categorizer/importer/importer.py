import datetime
import time
from dataclasses import dataclass, field
from pathlib import Path

import ffmpeg

from photos_categorizer.db.manager import DatabaseManager
from photos_categorizer.models.photo import Photo, Tag, TagResult
from photos_categorizer.tagging.engine import TaggingEngine

SUPPORTED_EXT = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tiff", ".tif", ".bmp", ".raw"}
)
_THUMB_SIZE = 256


@dataclass(frozen=True)
class FileResult:
    path: Path
    width: int
    height: int
    thumbnail: bytes
    tags: list[TagResult]
    duration_ms: int = field(default=0)


def scan_folder(folder: Path) -> list[Path]:
    return [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXT]


def process_file(path: Path, engine: TaggingEngine) -> FileResult:
    t0 = time.perf_counter()
    width, height = _get_dimensions(path)
    thumbnail = _make_thumbnail(path)
    tags = engine.analyze(path)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    return FileResult(
        path=path, width=width, height=height, thumbnail=thumbnail,
        tags=tags, duration_ms=duration_ms,
    )


def _get_dimensions(path: Path) -> tuple[int, int]:
    probe = ffmpeg.probe(str(path))
    stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    return int(stream["width"]), int(stream["height"])


def _make_thumbnail(path: Path) -> bytes:
    out, _ = (
        ffmpeg.input(str(path))
        .filter("scale", _THUMB_SIZE, _THUMB_SIZE, force_original_aspect_ratio="decrease")
        .output("pipe:", format="image2", vcodec="mjpeg", vframes=1)
        .run(capture_stdout=True, capture_stderr=True, quiet=True)
    )
    return bytes(out)


class PhotoImporter:
    """Persists FileResult from worker thread to the database (called from main thread)."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def persist(self, result: FileResult) -> tuple[Photo, list[Tag]]:
        now = datetime.datetime.now(datetime.UTC).isoformat()
        proto = Photo(
            id=0,
            path=result.path,
            filename=result.path.name,
            width=result.width,
            height=result.height,
            imported_at=now,
            date_taken="",
        )
        photo_id = self._db.save_photo(proto)
        self._db.save_thumbnail(photo_id, result.thumbnail)
        tags = self._db.save_tags(photo_id, result.tags)
        saved = self._db.get_photo_by_id(photo_id)
        return saved if saved is not None else proto, tags
