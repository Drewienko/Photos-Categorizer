"""
Integration tests for GoogleVisionEngine.
Skipped by default to preserve API quota.
Run with: uv run pytest --vision
Requires GOOGLE_APPLICATION_CREDENTIALS env var pointing to a service account JSON.
"""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.vision

ASSETS = Path(__file__).parent / "assets"


def _images() -> list[Path]:
    return [
        p
        for p in ASSETS.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".raw"}
    ]


def _require_credentials() -> str:
    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not creds or not Path(creds).exists():
        pytest.skip("GOOGLE_APPLICATION_CREDENTIALS not set — skipping Vision API tests")
    return creds


def _require_assets() -> None:
    if not _images():
        pytest.skip("No images in tests/assets/ — add photos to run engine tests")


@pytest.fixture(scope="module")
def engine():  # type: ignore[return]
    creds = _require_credentials()
    _require_assets()
    from photos_categorizer.tagging.vision_engine import GoogleVisionEngine

    return GoogleVisionEngine(credentials_path=creds, threshold=0.0)


def test_vision_returns_results(engine) -> None:  # type: ignore[no-untyped-def]
    for image in _images():
        results = engine.analyze(image)
        assert len(results) > 0, f"No results for {image.name}"
        assert all(0.0 <= r.confidence <= 1.0 for r in results)
        assert all(r.source == "vision" for r in results)


def test_vision_labels_are_lowercase(engine) -> None:  # type: ignore[no-untyped-def]
    for image in _images():
        results = engine.analyze(image)
        assert all(r.label == r.label.lower() for r in results)


def test_vision_threshold_filters(engine) -> None:  # type: ignore[no-untyped-def]
    from photos_categorizer.tagging.vision_engine import GoogleVisionEngine

    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    strict = GoogleVisionEngine(credentials_path=creds, threshold=0.8)

    for image in _images():
        all_results = engine.analyze(image)
        filtered = strict.analyze(image)
        assert len(filtered) <= len(all_results)
        assert all(r.confidence >= 0.8 for r in filtered)
