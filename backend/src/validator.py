from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from src.models import CaptionSet


class InvalidModelResponseError(ValueError):
    """Raised when a model response cannot be parsed into the expected schema."""


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            payload = json.loads(cleaned[start : end + 1])
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError as exc:
            raise InvalidModelResponseError(f"Invalid JSON returned by model: {exc}") from exc

    raise InvalidModelResponseError("Model response did not contain a JSON object")


def validate_vision_payload(text: str) -> tuple[str, str, list[str]]:
    payload = extract_json_object(text)
    description = str(payload.get("factual_description") or payload.get("description") or "").strip()
    neutral = str(payload.get("neutral_caption") or payload.get("neutral") or "").strip()
    raw_timeline = payload.get("scene_timeline") or payload.get("timeline") or []
    timeline = [str(item).strip() for item in raw_timeline if str(item).strip()] if isinstance(raw_timeline, list) else []
    if not description or not neutral:
        raise InvalidModelResponseError(
            "Vision response must include factual_description and neutral_caption"
        )
    return description, neutral, timeline


def validate_caption_set(text: str) -> CaptionSet:
    payload = extract_json_object(text)
    try:
        return CaptionSet.model_validate(payload)
    except ValidationError as exc:
        raise InvalidModelResponseError(f"Styled captions failed schema validation: {exc}") from exc
