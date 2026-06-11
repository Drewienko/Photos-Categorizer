"""
Integration tests for CLIPEngine using real images from tests/assets/.
First run downloads model weights (~350 MB, cached in ~/.cache/huggingface/).
"""

from pathlib import Path

import pytest

ASSETS = Path(__file__).parent / "assets"
LABELS = [
    "dog",
    "cat",
    "nature",
    "outdoor",
    "people",
    "architecture",
    "food",
    "animals",
    "water",
    "urban",
    "night",
    "portrait",
    "vehicles",
]


def _images() -> list[Path]:
    return [
        p
        for p in ASSETS.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".raw"}
    ]


def _require_assets() -> None:
    if not _images():
        pytest.skip("No images in tests/assets/ — add photos to run engine tests")


@pytest.fixture(scope="module")
def engine():  # type: ignore[return]
    _require_assets()
    from photos_categorizer.tagging.clip_engine import CLIPEngine

    e = CLIPEngine(labels=LABELS, threshold=0.0)  # threshold=0 to see all scores
    e.load()
    return e


def test_clip_returns_results(engine) -> None:  # type: ignore[no-untyped-def]
    for image in _images():
        results = engine.analyze(image)
        assert len(results) > 0, f"No results for {image.name}"
        assert all(0.0 <= r.confidence <= 1.0 for r in results)
        assert all(r.source == "clip" for r in results)


def test_clip_scores_sum_to_one(engine) -> None:  # type: ignore[no-untyped-def]
    """Softmax output should sum to ~1.0 across all labels."""
    for image in _images():
        results = engine.analyze(image)
        total = sum(r.confidence for r in results)
        assert abs(total - 1.0) < 0.01, f"Scores don't sum to 1.0 for {image.name}"


def test_clip_threshold_filters(engine) -> None:  # type: ignore[no-untyped-def]
    """Engine with threshold=0.5 returns fewer results than threshold=0.0."""
    from photos_categorizer.tagging.clip_engine import CLIPEngine

    strict = CLIPEngine(labels=LABELS, threshold=0.5)
    strict._model = engine._model
    strict._preprocess = engine._preprocess
    strict._text_features = engine._text_features

    for image in _images():
        all_results = engine.analyze(image)
        filtered = strict.analyze(image)
        assert len(filtered) <= len(all_results)
        assert all(r.confidence >= 0.5 for r in filtered)


def test_clip_labels_are_in_label_list(engine) -> None:  # type: ignore[no-untyped-def]
    for image in _images():
        results = engine.analyze(image)
        for r in results:
            assert r.label in LABELS


def test_clip_raises_on_nonexistent_file(engine) -> None:  # type: ignore[no-untyped-def]
    """ffmpeg fails on a missing file — exception propagates out of analyze()."""
    import ffmpeg as _ffmpeg

    with pytest.raises(_ffmpeg.Error):
        engine.analyze(Path("/nonexistent/does_not_exist.jpg"))


@pytest.mark.parametrize(
    "filename,expected_label",
    [
        ("car.jpg", "vehicles"),
        ("pizza.png", "food"),
        ("2 dogos.jpg", "dog"),
    ],
)
def test_clip_expected_label_in_top3(engine, filename: str, expected_label: str) -> None:  # type: ignore[no-untyped-def]
    """Expected label must appear in top-3 results (small label set → top-1 too strict)."""
    image = ASSETS / filename
    if not image.exists():
        pytest.skip(f"{filename} not found in tests/assets/")
    results = engine.analyze(image)
    top3 = sorted(results, key=lambda r: -r.confidence)[:3]
    top3_labels = [r.label for r in top3]
    assert expected_label in top3_labels, (
        f"{filename}: expected '{expected_label}' in top-3, "
        f"got {[(r.label, f'{r.confidence:.2%}') for r in top3]}"
    )
