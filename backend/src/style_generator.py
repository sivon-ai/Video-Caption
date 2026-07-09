from __future__ import annotations

from typing import Any

from config import settings
from src.fireworks_client import FireworksClient
from src.models import CaptionSet
from src.validator import validate_caption_set


class StyleGenerator:
    def __init__(self, client: FireworksClient | None = None) -> None:
        self.client = client or FireworksClient()
        self.prompt = (settings.prompts_dir / "rewrite_prompt.txt").read_text(encoding="utf-8")

    def generate(self, neutral_caption: str) -> tuple[CaptionSet, dict[str, Any]]:
        raw, meta = self.client.chat_completion(
            model=settings.text_model,
            messages=[
                {"role": "system", "content": self.prompt},
                {
                    "role": "user",
                    "content": (
                        "Rewrite this neutral caption into the four required styles. "
                        f"Neutral caption: {neutral_caption}"
                    ),
                },
            ],
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            response_format={"type": "json_object"},
        )
        return validate_caption_set(raw), meta
