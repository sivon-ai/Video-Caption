from __future__ import annotations

from pathlib import Path
from typing import Any

from config import settings
from src.fireworks_client import FireworksClient
from src.frame_extractor import FrameSample
from src.validator import validate_vision_payload


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
            f"{self.prompt}\n\n"
            f"Video file: {video_path.name}\n"
            f"Sampled frames:\n{frame_manifest}\n\n"
            "Return JSON only."
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
            response_format={"type": "json_object"},
        )
        description, neutral, timeline = validate_vision_payload(raw)
        return description, neutral, timeline, meta
