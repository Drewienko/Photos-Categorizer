import io
from pathlib import Path
from typing import Any

import ffmpeg
import torch
from PIL import Image as PILImage

from photos_categorizer.models.photo import TagResult


class CLIPEngine:
    def __init__(self, labels: list[str], threshold: float = 0.70) -> None:
        self._labels = labels
        self._threshold = threshold
        self._model: Any = None
        self._preprocess: Any = None
        self._text_features: torch.Tensor | None = None

    def load(self) -> None:
        """Load model weights. Call once before first analyze() to avoid cold start."""
        if self._model is not None:
            return
        import open_clip

        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        model.eval()

        self._model = model
        self._preprocess = preprocess
        self._text_features = self._encode_labels(tokenizer)

    def _encode_labels(self, tokenizer: Any) -> torch.Tensor:  # noqa: ANN401
        tokens = tokenizer(self._labels)
        with torch.no_grad():
            features: torch.Tensor = self._model.encode_text(tokens)
        features /= features.norm(dim=-1, keepdim=True)
        return features

    def analyze(self, image_path: Path) -> list[TagResult]:
        self.load()
        assert self._model is not None
        assert self._text_features is not None

        image_tensor = _load_image(image_path, self._preprocess)

        with torch.no_grad():
            image_features: torch.Tensor = self._model.encode_image(image_tensor)

        image_features /= image_features.norm(dim=-1, keepdim=True)
        probs = (100.0 * image_features @ self._text_features.T).softmax(dim=-1)
        scores = probs[0].tolist()

        return [
            TagResult(label=label, confidence=round(float(score), 4), source="clip")
            for label, score in zip(self._labels, scores, strict=False)
            if float(score) >= self._threshold
        ]


def _load_image(image_path: Path, preprocess: Any) -> torch.Tensor:  # noqa: ANN401
    """ffmpeg → JPEG bytes → PIL → preprocess tensor (1, C, H, W)."""
    out, _ = (
        ffmpeg.input(str(image_path))
        .output("pipe:", format="image2", vcodec="mjpeg", vframes=1)
        .run(capture_stdout=True, capture_stderr=True, quiet=True)
    )
    pil_image = PILImage.open(io.BytesIO(bytes(out))).convert("RGB")
    tensor: torch.Tensor = preprocess(pil_image)
    return tensor.unsqueeze(0)
