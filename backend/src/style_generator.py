from __future__ import annotations

import re
from typing import Any

from config import settings
from src.fireworks_client import FireworksClient
from src.models import CaptionSet
from src.validator import InvalidModelResponseError, clean_caption_text, validate_caption_set


class StyleGenerator:
    def __init__(self, client: FireworksClient | None = None) -> None:
        self.client = client or FireworksClient()
        self.prompt = (settings.prompts_dir / "rewrite_prompt.txt").read_text(encoding="utf-8")

    def generate(
        self,
        neutral_caption: str,
        factual_description: str = "",
        scene_timeline: list[str] | None = None,
    ) -> tuple[CaptionSet, dict[str, Any]]:
        timeline = "\n".join(f"- {item}" for item in scene_timeline or [])
        factual_context = (
            "Use the factual context below as the source of truth. Preserve the same event order.\n\n"
            f"Factual description:\n{factual_description or neutral_caption}\n\n"
            f"Scene timeline:\n{timeline or 'No separate timeline provided.'}\n\n"
            f"Neutral caption:\n{neutral_caption}"
        )
        raw, meta = self.client.chat_completion(
            model=settings.text_model,
            messages=[
                {"role": "system", "content": self.prompt},
                {
                    "role": "user",
                    "content": (
                        "/no_think\n"
                        "Rewrite the video summary into the four required styles. "
                        "Each style should be 3-5 sentences when enough detail is available. "
                        "Make the four styles clearly different in voice while preserving every visible fact.\n\n"
                        f"{factual_context}"
                    ),
                },
            ],
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            return validate_caption_set(raw), meta
        except InvalidModelResponseError as first_error:
            try:
                regenerated, regenerate_meta = self._regenerate_style_json(factual_context)
                meta["regenerate"] = regenerate_meta
                return validate_caption_set(regenerated), meta
            except InvalidModelResponseError as regenerate_error:
                meta["regenerate_error"] = str(regenerate_error)

            try:
                repaired, repair_meta = self._repair_style_json(raw)
                meta["repair"] = repair_meta
                return validate_caption_set(repaired), meta
            except InvalidModelResponseError as repair_error:
                meta["fallback"] = {
                    "first_error": str(first_error),
                    "repair_error": str(repair_error),
                }
                return self._fallback_styles(
                    neutral_caption,
                    factual_description=factual_description,
                    scene_timeline=scene_timeline,
                ), meta

    def _regenerate_style_json(self, factual_context: str) -> tuple[str, dict[str, Any]]:
        return self.client.chat_completion(
            model=settings.text_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return valid JSON only. Create four clearly distinct captions from the factual video context. "
                        "Formal must sound objective and documentary-like. Sarcastic must sound dry and playful. "
                        "Humorous-tech must include clear software/developer metaphors. Humorous-non-tech must be casual everyday humor. "
                        "All four must preserve every fact and event order. Do not include analysis or markdown."
                    ),
                },
                {"role": "user", "content": f"/no_think\n{factual_context}"},
            ],
            temperature=min(settings.temperature + 0.15, 0.7),
            max_tokens=settings.max_tokens,
            response_format={"type": "json_object"},
        )

    def _repair_style_json(self, raw_response: str) -> tuple[str, dict[str, Any]]:
        return self.client.chat_completion(
            model=settings.text_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Convert the user's styled captions into valid JSON only. Do not add facts. "
                        "Do not include thinking, analysis, markdown, or explanations. "
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
    def _fallback_styles(
        neutral_caption: str,
        factual_description: str = "",
        scene_timeline: list[str] | None = None,
    ) -> CaptionSet:
        source = StyleGenerator._source_summary(neutral_caption, factual_description, scene_timeline)
        return CaptionSet(
            formal=(
                "The video presents a continuous visible sequence with the main subjects moving through a series of connected actions. "
                f"{source} The description follows the events in chronological order and keeps attention on the visible interaction, objects, and final movement."
            ),
            sarcastic=(
                "Because apparently a simple moment was not enough, the scene turns into a full little chain reaction. "
                f"{source} Naturally, the visible props and movements all get dragged into the situation, and the whole sequence commits to its tiny escalation with impressive seriousness."
            ),
            humorous_tech=(
                "The clip boots like a visual event loop: subjects load, props initialize, and the action keeps passing state from one moment to the next. "
                f"{source} The sequence preserves its execution order, the interaction thread stays active, and the ending lands like the final process completing after several very visible callbacks."
            ),
            humorous_non_tech=(
                "The video plays like a small everyday commotion that keeps finding new ways to get busier. "
                f"{source} Everyone and everything in view seems pulled into the moment, making the sequence feel like a tiny scene where the action keeps saying, 'wait, there is more.'"
            ),
        )

    @staticmethod
    def _source_summary(
        neutral_caption: str,
        factual_description: str = "",
        scene_timeline: list[str] | None = None,
    ) -> str:
        timeline = " ".join(item.rstrip(".") + "." for item in scene_timeline or [])
        source = factual_description.strip() or neutral_caption.strip()
        if len(re.findall(r"[A-Za-z0-9]+", source)) < 45 and timeline:
            source = " ".join(part for part in (source, timeline) if part).strip()
        source = clean_caption_text(source)
        if not source:
            return "The main visible subjects move through the scene in a chronological sequence of actions."
        return source[:1400]
