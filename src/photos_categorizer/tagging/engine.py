from pathlib import Path
from typing import Protocol

from photos_categorizer.models.photo import TagResult


class TaggingEngine(Protocol):
    def analyze(self, image_path: Path) -> list[TagResult]: ...
