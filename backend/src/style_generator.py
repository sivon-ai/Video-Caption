from __future__ import annotations

from typing import Any

from config import settings
from src.fireworks_client import FireworksClient
from src.models import CaptionSet
from src.validator import InvalidModelResponseError, validate_caption_set


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
        try:
            return validate_caption_set(raw), meta
        except InvalidModelResponseError:
            try:
                repaired, repair_meta = self._repair_style_json(raw)
                meta["repair"] = repair_meta
                return validate_caption_set(repaired), meta
            except InvalidModelResponseError as repair_error:
                meta["fallback"] = {"reason": str(repair_error)}
                return self._fallback_styles(neutral_caption), meta

    def _repair_style_json(self, raw_response: str) -> tuple[str, dict[str, Any]]:
        return self.client.chat_completion(
            model=settings.text_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Convert the user's styled captions into valid JSON only. Do not add facts. "
                        "Do not use placeholders, ellipses, empty strings, or schema examples as values. "
                        "Return exactly these keys with real caption text: formal, sarcastic, "
                        "humorous_tech, humorous_non_tech."
                    ),
                },
                {"role": "user", "content": raw_response},
            ],
            temperature=0,
            max_tokens=settings.max_tokens,
            response_format={"type": "json_object"},
        )

    @staticmethod
    def _fallback_styles(neutral_caption: str) -> CaptionSet:
        neutral = neutral_caption.strip()
        return CaptionSet(
            formal=neutral,
            sarcastic=(
                "In a surprisingly eventful sequence, the visible scene proceeds exactly as shown: "
                f"{neutral}"
            ),
            humorous_tech=(
                "The video runs a clear visual sequence with the same observable facts: "
                f"{neutral} Consider it the scene's main process completing without adding new inputs."
            ),
            humorous_non_tech=(
                "The scene keeps things simple and visible: "
                f"{neutral} It has enough movement and tiny drama to carry the moment without needing extra assumptions."
            ),
        )
