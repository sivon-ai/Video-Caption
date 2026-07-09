from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from config import settings
from src.fireworks_client import FireworksClient
from src.frame_extractor import FrameSample
from src.validator import InvalidModelResponseError, clean_caption_text, validate_vision_payload


class CaptionGenerator:
    def __init__(self, client: FireworksClient | None = None) -> None:
        self.client = client or FireworksClient()
        self.prompt = (settings.prompts_dir / "vision_prompt.txt").read_text(encoding="utf-8")

    def generate(
        self, video_path: Path, frames: list[FrameSample]
    ) -> tuple[str, str, list[str], dict[str, Any]]:
        frame_manifest = "\n".join(
            f"- frame {frame.index} at {frame.timestamp_seconds}s" for frame in frames
        )
        text = (
            "/no_think\n"
            f"{self.prompt}\n\n"
            f"Video file: {video_path.name}\n"
            f"Sampled frames:\n{frame_manifest}\n\n"
            "Return final JSON only. Do not include thinking, analysis, markdown, or explanations."
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for frame in frames:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{frame.image_base64}",
                        "detail": "low",
                    },
                }
            )

        raw, meta = self.client.chat_completion(
            model=settings.vision_model,
            messages=[{"role": "user", "content": content}],
            temperature=0.1,
            max_tokens=settings.max_tokens,
            response_format=None,
        )
        try:
            description, neutral, timeline = validate_vision_payload(raw)
        except InvalidModelResponseError as first_error:
            try:
                retried, retry_meta = self._retry_vision_json(content)
                description, neutral, timeline = validate_vision_payload(retried)
                meta["retry"] = retry_meta
                return description, neutral, timeline, meta
            except InvalidModelResponseError as retry_error:
                meta["retry_error"] = str(retry_error)

            try:
                repaired, repair_meta = self._repair_vision_json(raw)
                description, neutral, timeline = validate_vision_payload(repaired)
                meta["repair"] = repair_meta
            except InvalidModelResponseError as repair_error:
                if not raw.strip() or raw.strip() in {"{}", "[]"}:
                    raise InvalidModelResponseError(
                        "Vision model returned an empty description for the sampled frames. "
                        "Try a different Fireworks vision model or rerun with fewer/smaller frames."
                    ) from repair_error
                description, neutral, timeline = self._fallback_from_text(raw)
                meta["fallback"] = {
                    "original_error": str(first_error),
                    "repair_error": str(repair_error),
                }
        return description, neutral, timeline, meta

    def _retry_vision_json(self, original_content: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        retry_content = list(original_content)
        retry_content[0] = {
            "type": "text",
            "text": (
                "/no_think\n"
                "Analyze these sampled video frames again. Return ONLY valid JSON, with no markdown or explanation. "
                "Do not return an empty object. The caption must explain the visible beginning, middle, and ending of the video. "
                "Required keys: factual_description, scene_timeline, neutral_caption. "
                "The factual_description and neutral_caption must be complete natural-language summaries, not object lists."
            ),
        }
        return self.client.chat_completion(
            model=settings.vision_model,
            messages=[{"role": "user", "content": retry_content}],
            temperature=0,
            max_tokens=settings.max_tokens,
            response_format=None,
        )

    def _repair_vision_json(self, raw_response: str) -> tuple[str, dict[str, Any]]:
        return self.client.chat_completion(
            model=settings.text_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Convert the user's video analysis into valid JSON only. Do not add facts. "
                        "Do not include thinking, analysis, markdown, or explanations. "
                        "Do not use placeholders, ellipses, empty strings, or schema examples as values. "
                        "Return exactly these keys with real content from the user's text: "
                        "factual_description, scene_timeline, neutral_caption."
                    ),
                },
                {"role": "user", "content": raw_response},
            ],
            temperature=0,
            max_tokens=settings.max_tokens,
            response_format={"type": "json_object"},
        )

    @staticmethod
    def _fallback_from_text(raw_response: str) -> tuple[str, str, list[str]]:
        cleaned = raw_response.strip()
        if not cleaned or cleaned in {"{}", "[]"}:
            raise InvalidModelResponseError("Vision model returned an empty response object.")

        frame_start = re.search(r"\bFrame\s+\d+\b", cleaned, flags=re.IGNORECASE)
        if frame_start:
            cleaned = cleaned[frame_start.start() :]

        cleaned = re.sub(r"```(?:json)?|```", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\*\*|\*", " ", cleaned)
        cleaned = re.sub(r"`", "", cleaned)
        cleaned = re.sub(r"\bThinking Process\s*:\s*", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bConstruct\s+the\s+JSON\b.*", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bReturn\s+(?:ONLY\s+)?valid\s+JSON\b.*", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bmain_event\s*:\s*", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bneutral_caption\s*:\s*", "Summary: ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bfactual_description\s*:\s*", "Description: ", cleaned, flags=re.IGNORECASE)

        rejected_prefixes = (
            "analyze the request",
            "task:",
            "constraints:",
            "valid json",
            "return exactly",
            "construct json",
            "construct the json",
            "output json",
        )
        lines = []
        for line in cleaned.splitlines():
            compact = line.strip(" -\t")
            if not compact:
                continue
            if compact.lower().startswith(rejected_prefixes):
                continue
            compact = re.sub(
                r"^Frame\s+\d+(?:\s*\([^)]+\))?\s*:\s*",
                "",
                compact,
                flags=re.IGNORECASE,
            )
            lines.append(compact)

        description = clean_caption_text(re.sub(r"\s+", " ", " ".join(lines)).strip())
        description = re.sub(r"\s+([,.!?;:])", r"\1", description)
        description = description.strip(" {}[]")
        if len(re.findall(r"[A-Za-z0-9]+", description)) < 18:
            raise InvalidModelResponseError(
                f"Vision fallback did not contain enough factual detail: {raw_response[:300]!r}"
            )

        timeline = [
            re.sub(r"\s+", " ", line).strip()
            for line in lines
            if re.search(r"\bFrame\s+\d+\b|\b\d+(?:\.\d+)?s\b", line, flags=re.IGNORECASE)
        ][:8]

        sentences = re.split(r"(?<=[.!?])\s+", description)
        meaningful = [
            sentence.strip()
            for sentence in sentences
            if len(re.findall(r"[A-Za-z0-9]+", sentence)) >= 6
            and not sentence.lower().startswith(("1.", "2.", "3.", "4."))
        ]
        neutral = " ".join(meaningful[-4:] if len(meaningful) > 4 else meaningful).strip()
        if not neutral:
            neutral = description[:900].strip()
        if len(re.findall(r"[A-Za-z0-9]+", neutral)) < 18:
            raise InvalidModelResponseError(
                f"Vision fallback did not produce a meaningful neutral caption: {neutral!r}"
            )

        return description[:1800], neutral[:1000], timeline
