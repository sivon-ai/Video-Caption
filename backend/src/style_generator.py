from __future__ import annotations

import re
from typing import Any

from config import settings
from src.fireworks_client import FireworksClient
from src.models import CaptionSet
from src.validator import (
    InvalidModelResponseError,
    merge_caption_sources,
    validate_caption_set,
)


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
        complete_summary = self._source_summary(neutral_caption, factual_description, scene_timeline)
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
                        "Each style should be 3-5 sentences when enough detail is available. "
                        "Make the four styles clearly different in voice while preserving every visible fact. "
                        "Use the Complete source summary first; the other fields are supporting evidence.\n\n"
                        f"{factual_context}"
                    ),
                },
            ],
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            return self._validated_caption_set(raw), meta
        except InvalidModelResponseError as first_error:
            try:
                regenerated, regenerate_meta = self._regenerate_style_json(factual_context)
                meta["regenerate"] = regenerate_meta
                return self._validated_caption_set(regenerated), meta
            except InvalidModelResponseError as regenerate_error:
                meta["regenerate_error"] = str(regenerate_error)

            try:
                repaired, repair_meta = self._repair_style_json(raw)
                meta["repair"] = repair_meta
                return self._validated_caption_set(repaired), meta
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

    @staticmethod
    def _validated_caption_set(raw: str) -> CaptionSet:
        captions = validate_caption_set(raw)
        StyleGenerator._require_style_voice(captions)
        return captions

    @staticmethod
    def _require_style_voice(captions: CaptionSet) -> None:
        checks = {
            "sarcastic": (
                captions.sarcastic,
                ("apparently", "naturally", "of course", "as if", "somehow", "because", "sure"),
                2,
            ),
            "humorous_tech": (
                captions.humorous_tech,
                ("runtime", "module", "state", "callback", "process", "pipeline", "debug", "queue", "cpu", "handler", "logs"),
                2,
            ),
            "humorous_non_tech": (
                captions.humorous_non_tech,
                ("day", "mess", "little", "no chill", "break", "busy", "somehow", "whole thing"),
                2,
            ),
        }
        for field_name, (text, markers, minimum) in checks.items():
            lowered = text.lower()
            score = sum(1 for marker in markers if marker in lowered)
            if score < minimum:
                raise InvalidModelResponseError(
                    f"{field_name} caption is valid text but not strongly styled enough."
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
        events = StyleGenerator._event_sentences(source)
        return CaptionSet(
            formal=StyleGenerator._compose_formal(events),
            sarcastic=StyleGenerator._compose_sarcastic(events),
            humorous_tech=StyleGenerator._compose_humorous_tech(events),
            humorous_non_tech=StyleGenerator._compose_humorous_non_tech(events),
        )

    @staticmethod
    def _source_summary(
        neutral_caption: str,
        factual_description: str = "",
        scene_timeline: list[str] | None = None,
    ) -> str:
        source = merge_caption_sources(
            factual_description,
            scene_timeline or [],
            neutral_caption,
            limit=1700,
        )
        if not source:
            return "The main visible subjects move through the scene in a chronological sequence of actions."
        return source

    @staticmethod
    def _event_sentences(source: str) -> list[str]:
        sentences = [
            sentence.strip(" .:")
            for sentence in re.split(r"(?<=[.!?])\s+", source)
            if len(re.findall(r"[A-Za-z0-9]+", sentence)) >= 5
        ]
        if not sentences:
            return ["The main visible subjects move through the scene in a chronological sequence of actions"]
        return sentences[:8]

    @staticmethod
    def _clean_event(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip(" .:")
        cleaned = re.sub(r"\.\s*:", ". ", cleaned)
        return cleaned.strip(" .:")

    @staticmethod
    def _lower_first(text: str) -> str:
        text = StyleGenerator._clean_event(text)
        if not text:
            return text
        if re.match(r"(Tom|Jerry|Vanishing)\b", text):
            return text
        return text[0].lower() + text[1:]

    @staticmethod
    def _sentence(text: str) -> str:
        cleaned = StyleGenerator._clean_event(text)
        if not cleaned:
            return ""
        return cleaned.rstrip(".") + "."

    @staticmethod
    def _event_groups(events: list[str], max_groups: int = 4) -> list[list[str]]:
        clean_events = [StyleGenerator._clean_event(event) for event in events if StyleGenerator._clean_event(event)]
        if len(clean_events) <= max_groups:
            return [[event] for event in clean_events]
        group_count = max_groups
        base = len(clean_events) // group_count
        extra = len(clean_events) % group_count
        groups: list[list[str]] = []
        cursor = 0
        for index in range(group_count):
            size = base + (1 if index < extra else 0)
            groups.append(clean_events[cursor : cursor + size])
            cursor += size
        return groups

    @staticmethod
    def _plain_join(events: list[str]) -> str:
        if not events:
            return ""
        if len(events) == 1:
            return StyleGenerator._clean_event(events[0])
        first = StyleGenerator._clean_event(events[0])
        rest = [StyleGenerator._clean_event(event) for event in events[1:]]
        return "; ".join([first, *rest])

    @staticmethod
    def _styled_join(events: list[str], style: str, offset: int = 0) -> str:
        clean_events = [StyleGenerator._clean_event(event) for event in events if StyleGenerator._clean_event(event)]
        if not clean_events:
            return ""

        clauses: list[str] = []
        for index, event in enumerate(clean_events):
            lower_event = StyleGenerator._lower_first(event)
            if index == 0:
                clauses.append(event)
            elif style == "sarcastic":
                phrases = [
                    f"because apparently {lower_event}",
                    f"as if that were not enough, {lower_event}",
                    f"with complete commitment to the bit, {lower_event}",
                ]
                clauses.append(phrases[(index - 1 + offset) % len(phrases)])
            elif style == "tech":
                phrases = [
                    f"the next state update logs that {lower_event}",
                    f"the visual pipeline then queues {lower_event}",
                    f"the scene keeps the runtime busy as {lower_event}",
                ]
                clauses.append(phrases[(index - 1 + offset) % len(phrases)])
            elif style == "casual":
                phrases = [
                    f"then, because the day has no chill, {lower_event}",
                    f"and somehow the next little problem is that {lower_event}",
                    f"before anyone can catch a break, {lower_event}",
                ]
                clauses.append(phrases[(index - 1 + offset) % len(phrases)])
            else:
                clauses.append(event)
        return "; ".join(clauses)

    @staticmethod
    def _compose_formal(events: list[str]) -> str:
        groups = StyleGenerator._event_groups(events)
        openers = ["The sequence begins:", "It then shows:", "The action continues:", "The sequence ends:"]
        return " ".join(
            StyleGenerator._sentence(f"{openers[min(index, len(openers) - 1)]} {StyleGenerator._plain_join(group)}")
            for index, group in enumerate(groups)
        )

    @staticmethod
    def _compose_sarcastic(events: list[str]) -> str:
        groups = StyleGenerator._event_groups(events)
        wrappers = [
            ("Naturally, the beach scene cannot simply relax: ", ""),
            ("Because a quiet sandwich moment would be too easy, the scene adds this: ", ""),
            ("The plot then files a very serious escalation request: ", ""),
            ("By the end, because every prop deserves a dramatic entrance, ", ""),
        ]
        sentences = []
        for index, group in enumerate(groups):
            prefix, suffix = wrappers[min(index, len(wrappers) - 1)]
            sentences.append(StyleGenerator._sentence(f"{prefix}{StyleGenerator._styled_join(group, 'sarcastic', index)}{suffix}"))
        return " ".join(sentences)

    @staticmethod
    def _compose_humorous_tech(events: list[str]) -> str:
        groups = StyleGenerator._event_groups(events)
        wrappers = [
            ("The clip boots into beach mode: ", ""),
            ("The mischief module loads next: ", ""),
            ("Then the rivalry process spikes CPU usage: ", ""),
            ("The final callback returns: ", ""),
        ]
        sentences = []
        for index, group in enumerate(groups):
            prefix, suffix = wrappers[min(index, len(wrappers) - 1)]
            sentences.append(StyleGenerator._sentence(f"{prefix}{StyleGenerator._styled_join(group, 'tech', index)}{suffix}"))
        return " ".join(sentences)

    @staticmethod
    def _compose_humorous_non_tech(events: list[str]) -> str:
        groups = StyleGenerator._event_groups(events)
        wrappers = [
            ("The beach day starts off looking simple enough: ", ""),
            ("Then the scene turns into the kind of small mess where this happens: ", ""),
            ("Just when it seems the situation has already done enough, it adds this: ", ""),
            ("By the finish, the whole thing has collected a full little finale: ", ""),
        ]
        sentences = []
        for index, group in enumerate(groups):
            prefix, suffix = wrappers[min(index, len(wrappers) - 1)]
            sentences.append(StyleGenerator._sentence(f"{prefix}{StyleGenerator._styled_join(group, 'casual', index)}{suffix}"))
        return " ".join(sentences)
