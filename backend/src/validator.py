from __future__ import annotations

import ast
import json
import re
from typing import Any

from pydantic import ValidationError

from src.models import CaptionSet


class InvalidModelResponseError(ValueError):
    """Raised when a model response cannot be parsed into the expected schema."""


def response_preview(text: str, limit: int = 500) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    return cleaned[:limit] if cleaned else "<empty response>"


def clean_caption_text(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"\bCaption\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bActually,?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:I'll|I will)\s+include[^.!?]*(?:[.!?]|$)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^.!?]*\bweirdly placed\b[^.!?]*(?:[.!?]|$)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^.!?]*\bspliced in\b[^.!?]*(?:[.!?]|$)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^.!?]*\bspecific gag\b[^.!?]*(?:[.!?]|$)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\((?:maybe|possibly|probably)[^)]*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\blooking at (?:the )?(?:frame|image)[^.!?]*(?:[.!?]|$)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:frame|image)\s+\d+(?:\s+at\s+\d+(?:\.\d+)?s)?\s*:?", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+(?:\.\d+)?s\s*\([^)]*\)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+(?:\.\d+)?s\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bthe frames? (?:are|is) listed[^.!?]*(?:[.!?]|$)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bprompt list\b", "sampled sequence", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bWait,?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bThis loo\b.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bthis looks like a different scene or a transition\b", "the scene changes", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\.\s*:", ". ", cleaned)
    cleaned = re.sub(r":\s*(?=[A-Z])", ". ", cleaned)
    cleaned = re.sub(r"\.\s*,\s*", ". ", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    return cleaned.strip(" -")


def _word_count(value: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+", value))


def _sentence_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _content_words(value: str) -> set[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "in",
        "is",
        "it",
        "near",
        "of",
        "on",
        "the",
        "to",
        "with",
    }
    return {
        word.lower()
        for word in re.findall(r"[A-Za-z0-9]+", value)
        if len(word) > 2 and word.lower() not in stopwords
    }


def merge_caption_sources(*parts: object, limit: int = 1600) -> str:
    """Merge model caption fields without repeating the same visible event."""
    sentences: list[str] = []
    seen: set[str] = set()

    def add_text(text: str) -> None:
        cleaned = clean_caption_text(text)
        if not cleaned:
            return
        chunks = re.split(r"(?<=[.!?])\s+", cleaned)
        if len(chunks) == 1:
            chunks = re.split(r"\s+(?=(?:Then|Next|After|Later|Finally|By the end)\b)", cleaned)
        for chunk in chunks:
            sentence = clean_caption_text(chunk).strip(" .")
            if _word_count(sentence) < 5:
                continue
            key = _sentence_key(sentence)
            if not key or key in seen:
                continue
            words = _content_words(sentence)
            if any(
                words
                and existing_words
                and len(words & existing_words) / max(1, min(len(words), len(existing_words))) >= 0.85
                for existing_words in (_content_words(existing) for existing in sentences)
            ):
                continue
            seen.add(key)
            sentences.append(sentence.rstrip(".") + ".")

    for part in parts:
        if isinstance(part, list):
            for item in part:
                add_text(str(item))
        elif part:
            add_text(str(part))

    merged = " ".join(sentences)
    return merged[:limit].rstrip()


def _is_meaningful_text(value: str, min_words: int = 6) -> bool:
    cleaned = clean_caption_text(value)
    if not cleaned:
        return False
    if cleaned in {"...", "…", ".", "-", "n/a", "N/A", "null", "None"}:
        return False
    lowered = cleaned.lower()
    banned_fragments = (
        "construct the json",
        "return json",
        "return only valid json",
        "thinking process",
        "main_event",
        "neutral_caption",
        "factual_description",
    )
    if any(fragment in lowered for fragment in banned_fragments):
        return False
    if cleaned.startswith(("{", "[")) or cleaned.endswith(("}", "]")):
        return False
    words = re.findall(r"[A-Za-z0-9]+", cleaned)
    return len(words) >= min_words


def _require_meaningful(value: str, field_name: str, min_words: int = 6) -> None:
    if not _is_meaningful_text(value, min_words=min_words):
        raise InvalidModelResponseError(
            f"Model returned placeholder, partial JSON, or too-short text for {field_name}: {value!r}"
        )


def _parse_mapping(candidate: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(candidate)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    try:
        payload = ast.literal_eval(candidate)
        if isinstance(payload, dict):
            return payload
    except (ValueError, SyntaxError):
        pass

    return None


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    payload = _parse_mapping(cleaned)
    if payload is not None:
        return payload

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        payload = _parse_mapping(cleaned[start : end + 1])
        if payload is not None:
            return payload
        raise InvalidModelResponseError(
            f"Invalid JSON/Python mapping returned by model. Response preview: {response_preview(text)}"
        )

    raise InvalidModelResponseError(
        f"Model response did not contain a JSON object. Response preview: {response_preview(text)}"
    )


def validate_vision_payload(text: str) -> tuple[str, str, list[str]]:
    payload = extract_json_object(text)
    main_event = clean_caption_text(str(payload.get("main_event") or ""))
    description = clean_caption_text(str(payload.get("factual_description") or payload.get("description") or ""))
    neutral = clean_caption_text(str(payload.get("neutral_caption") or payload.get("neutral") or ""))
    raw_timeline = payload.get("scene_timeline") or payload.get("timeline") or []
    timeline = [
        clean_caption_text(_timeline_item_text(item))
        for item in raw_timeline
        if clean_caption_text(_timeline_item_text(item))
    ] if isinstance(raw_timeline, list) else []

    merged = merge_caption_sources(description or main_event, timeline, neutral, limit=1800)
    if merged:
        description = merged
        neutral = _compact_neutral_summary(merged, limit=1000)
    elif not neutral and description:
        neutral = _synthesize_neutral_caption(main_event, description, timeline)
    elif not description and neutral:
        description = neutral

    if not description or not neutral:
        raise InvalidModelResponseError(
            "Vision response must include factual_description and neutral_caption"
        )
    _require_meaningful(description, "factual_description", min_words=18)
    _require_meaningful(neutral, "neutral_caption", min_words=18)
    return description, neutral, timeline


def _timeline_item_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(
            item.get("description")
            or item.get("event")
            or item.get("caption")
            or item.get("text")
            or ""
        )
    return str(item)


def _synthesize_neutral_caption(main_event: str, description: str, timeline: list[str]) -> str:
    parts = []
    if main_event:
        parts.append(main_event.rstrip(".") + ".")
    if timeline:
        sequence = " Then ".join(item.rstrip(".") for item in timeline[:5])
        parts.append(f"The visible sequence shows {sequence}.")
    parts.append(description)
    return " ".join(parts)


def _compact_neutral_summary(source: str, limit: int = 1000) -> str:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", source)
        if _word_count(sentence) >= 5
    ]
    if not sentences:
        return source[:limit].rstrip()

    summary = ""
    for sentence in sentences:
        candidate = f"{summary} {sentence}".strip()
        if len(candidate) > limit:
            break
        summary = candidate
    return summary or source[:limit].rstrip()


def validate_caption_set(text: str) -> CaptionSet:
    payload = extract_json_object(text)
    try:
        captions = CaptionSet.model_validate(
            {key: clean_caption_text(str(value)) for key, value in payload.items()}
        )
    except ValidationError as exc:
        raise InvalidModelResponseError(f"Styled captions failed schema validation: {exc}") from exc
    for field_name, value in captions.model_dump().items():
        _require_meaningful(str(value), field_name, min_words=18)
    return captions
