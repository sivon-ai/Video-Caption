from __future__ import annotations

from typing import Any

from config import settings
from src.fireworks_client import FireworksClient
from src.models import CaptionSet
from src.validator import (
    InvalidModelResponseError,
    merge_caption_sources,
    validate_caption_set,
)


def _style_token_budget(duration_seconds: float) -> int:
    if duration_seconds <= 8:
        return min(settings.max_tokens, 700)
    if duration_seconds <= 15:
        return min(settings.max_tokens, 900)
    return settings.max_tokens


class StyleGenerator:
    def __init__(self, client: FireworksClient | None = None) -> None:
        self.client = client or FireworksClient()
        self.prompt = (settings.prompts_dir / "rewrite_prompt.txt").read_text(encoding="utf-8")

    def generate(
        self,
        neutral_caption: str,
        factual_description: str = "",
        scene_timeline: list[str] | None = None,
        duration_seconds: float = 0.0,
    ) -> tuple[CaptionSet, dict[str, Any]]:
        timeline = "\n".join(f"- {item}" for item in scene_timeline or [])
        source_limit = 900 if duration_seconds <= 8 else 1200 if duration_seconds <= 15 else 1700
        sentence_instruction = (
            "Each style should be 1-2 concise sentences. "
            "Do not expand short videos into long paragraphs."
            if duration_seconds <= 8
            else "Each style should be 1-2 sentences when enough detail is available."
            if duration_seconds <= 15
            else "Each style should be 3-5 sentences when enough detail is available."
        )
        complete_summary = self._source_summary(
            neutral_caption,
            factual_description,
            scene_timeline,
            limit=source_limit,
        )
        factual_context = (
            "Use the factual context below as the source of truth. Preserve the same event order.\n\n"
            f"Complete source summary:\n{complete_summary}\n\n"
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
                        f"{sentence_instruction} "
                        "Make the four styles clearly different in voice while preserving every visible fact. "
                        "Use the Complete source summary first; the other fields are supporting evidence. "
                        "Use wording that fits this specific video, not reusable template phrases.\n\n"
                        f"{factual_context}"
                    ),
                },
            ],
            temperature=settings.temperature,
            max_tokens=_style_token_budget(duration_seconds),
            response_format={"type": "json_object"},
        )
        try:
            return validate_caption_set(raw), meta
        except InvalidModelResponseError as first_error:
            try:
                regenerated, regenerate_meta = self._regenerate_style_json(
                    factual_context,
                    max_tokens=_style_token_budget(duration_seconds),
                )
                meta["regenerate"] = regenerate_meta
                return validate_caption_set(regenerated), meta
            except InvalidModelResponseError as regenerate_error:
                meta["regenerate_error"] = str(regenerate_error)

            try:
                repaired, repair_meta = self._repair_style_json(
                    raw,
                    max_tokens=_style_token_budget(duration_seconds),
                )
                meta["repair"] = repair_meta
                return validate_caption_set(repaired), meta
            except InvalidModelResponseError as repair_error:
                meta["style_error"] = {
                    "first_error": str(first_error),
                    "regenerate_error": meta.get("regenerate_error"),
                    "repair_error": str(repair_error),
                }
                raise InvalidModelResponseError(
                    "Style model did not return valid complete JSON after retry and repair. "
                    "No fallback caption was generated, to avoid hardcoded or inaccurate wording."
                ) from repair_error

    def generate_fast(
        self,
        neutral_caption: str,
        factual_description: str = "",
        scene_timeline: list[str] | None = None,
    ) -> tuple[CaptionSet, dict[str, Any]]:
        source = self._source_summary(
            neutral_caption,
            factual_description,
            scene_timeline,
            limit=520,
        )
        source = source.rstrip(".") + "."
        captions = CaptionSet(
            formal=source,
            sarcastic=f"Naturally, the short clip makes a complete production out of it: {source}",
            humorous_tech=f"The video runs a compact real-world update loop: {source}",
            humorous_non_tech=f"This quick clip keeps things moving without wasting time: {source}",
        )
        return captions, {
            "latency_seconds": 0.0,
            "usage": {},
            "mode": "local_fast_style",
        }

    def _regenerate_style_json(
        self,
        factual_context: str,
        *,
        max_tokens: int,
    ) -> tuple[str, dict[str, Any]]:
        return self.client.chat_completion(
            model=settings.text_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return valid JSON only. Create four clearly distinct captions from the factual video context. "
                        "Formal must sound objective and documentary-like. Sarcastic must sound dry and playful. "
                        "Humorous-tech must include clear software/developer metaphors. Humorous-non-tech must be casual everyday humor. "
                        "All four must preserve every fact and event order. Use content-specific phrasing for this video. "
                        "Do not reuse generic template openings or mention a setting/action unless it appears in the factual context. "
                        "Do not include analysis or markdown."
                    ),
                },
                {"role": "user", "content": f"/no_think\n{factual_context}"},
            ],
            temperature=min(settings.temperature + 0.15, 0.7),
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

    def _repair_style_json(self, raw_response: str, *, max_tokens: int) -> tuple[str, dict[str, Any]]:
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
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

    @staticmethod
    def _source_summary(
        neutral_caption: str,
        factual_description: str = "",
        scene_timeline: list[str] | None = None,
        limit: int = 1700,
    ) -> str:
        source = merge_caption_sources(
            factual_description,
            scene_timeline or [],
            neutral_caption,
            limit=limit,
        )
        if not source:
            raise InvalidModelResponseError("No factual source summary is available for style generation.")
        return source
