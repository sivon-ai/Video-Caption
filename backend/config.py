from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    root_dir: Path = ROOT_DIR
    videos_dir: Path = ROOT_DIR / "videos"
    outputs_dir: Path = ROOT_DIR / "outputs"
    logs_dir: Path = ROOT_DIR / "logs"
    prompts_dir: Path = ROOT_DIR / "prompts"

    api_key: str = field(
        default_factory=lambda: os.getenv("API_KEY")
        or os.getenv("FIREWORKS_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    )
    api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "API_BASE_URL", "https://api.fireworks.ai/inference/v1"
        ).rstrip("/")
    )
    vision_model: str = field(default_factory=lambda: os.getenv("VISION_MODEL", ""))
    text_model: str = field(default_factory=lambda: os.getenv("TEXT_MODEL", ""))
    temperature: float = field(default_factory=lambda: float(os.getenv("TEMPERATURE", "0.3")))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("MAX_TOKENS", "1800")))
    request_timeout: int = field(default_factory=lambda: int(os.getenv("REQUEST_TIMEOUT", "90")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    max_workers: int = field(default_factory=lambda: int(os.getenv("MAX_WORKERS", "1")))

    min_frames: int = field(default_factory=lambda: int(os.getenv("MIN_FRAMES", "14")))
    max_frames: int = field(default_factory=lambda: int(os.getenv("MAX_FRAMES", "20")))
    jpeg_quality: int = field(default_factory=lambda: int(os.getenv("JPEG_QUALITY", "82")))
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "500")))
    max_url_download_mb: int = field(
        default_factory=lambda: int(os.getenv("MAX_URL_DOWNLOAD_MB", "500"))
    )

    cors_origins: list[str] = field(
        default_factory=lambda: _csv(
            os.getenv(
                "CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
            )
        )
    )
    video_extensions: tuple[str, ...] = (
        ".mp4",
        ".webm",
        ".mov",
        ".mkv",
        ".avi",
        ".mpeg",
        ".mpg",
    )

    def ensure_directories(self) -> None:
        for directory in (self.videos_dir, self.outputs_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def is_api_configured(self) -> bool:
        return bool(self.api_key and self.vision_model and self.text_model)


settings = Settings()
