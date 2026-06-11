from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class TagResult:
    label: str
    confidence: float  # 0.0–1.0
    source: str  # "clip" | "vision"


@dataclass(slots=True, frozen=True)
class Tag:
    id: int
    name: str
    source: str  # "clip" | "vision" | "manual"
    confidence: float


@dataclass(slots=True, frozen=True)
class PhotoTag:
    photo_id: int
    tag_id: int


@dataclass(slots=True, frozen=True)
class Photo:
    id: int
    path: Path
    filename: str
    width: int
    height: int
    imported_at: str  # ISO datetime
    date_taken: str  # ISO date from EXIF, empty string if unavailable
    starred: bool = False
