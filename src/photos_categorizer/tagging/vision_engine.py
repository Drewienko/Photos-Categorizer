from pathlib import Path

import ffmpeg
from google.cloud import vision

from photos_categorizer.models.photo import TagResult

_MAX_SIZE = 1024


class GoogleVisionEngine:
    def __init__(self, credentials_path: str, threshold: float = 0.70) -> None:
        self._threshold = threshold
        self._client = vision.ImageAnnotatorClient.from_service_account_file(credentials_path)

    def analyze(self, image_path: Path) -> list[TagResult]:
        jpeg_bytes = _resize_to_jpeg(image_path, _MAX_SIZE)
        image = vision.Image(content=jpeg_bytes)
        response = self._client.label_detection(image=image)  # type: ignore[attr-defined]

        if response.error.message:
            raise RuntimeError(f"Vision API error for {image_path.name}: {response.error.message}")

        return [
            TagResult(
                label=label.description.lower(),
                confidence=round(label.score, 4),
                source="vision",
            )
            for label in response.label_annotations
            if label.score >= self._threshold
        ]


def _resize_to_jpeg(image_path: Path, max_size: int) -> bytes:
    """ffmpeg → resize (keep aspect) → JPEG bytes."""
    out, _ = (
        ffmpeg.input(str(image_path))
        .filter(
            "scale",
            max_size,
            max_size,
            force_original_aspect_ratio="decrease",
        )
        .output("pipe:", format="image2", vcodec="mjpeg", vframes=1)
        .run(capture_stdout=True, capture_stderr=True, quiet=True)
    )
    return bytes(out)
