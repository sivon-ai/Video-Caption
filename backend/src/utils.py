from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import unquote, urlparse
from uuid import uuid4

import requests

from config import Settings


def safe_filename(name: str, fallback_suffix: str = ".mp4") -> str:
    stem = Path(name).stem or f"video-{uuid4().hex[:8]}"
    suffix = Path(name).suffix.lower() or fallback_suffix
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")
    return f"{cleaned or 'video'}-{uuid4().hex[:8]}{suffix}"


def iter_video_files(directory: Path, extensions: tuple[str, ...]) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in extensions
    )


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


@contextmanager
def timer() -> Iterator[Callable[[], float]]:
    started = time.perf_counter()

    def elapsed() -> float:
        return round(time.perf_counter() - started, 3)

    yield elapsed


def download_video(url: str, destination_dir: Path, settings: Settings) -> Path:
    parsed = urlparse(url)
    raw_name = unquote(Path(parsed.path).name) or "downloaded-video.mp4"
    target = destination_dir / safe_filename(raw_name)
    max_bytes = settings.max_url_download_mb * 1024 * 1024

    with requests.get(url, stream=True, timeout=settings.request_timeout) as response:
        response.raise_for_status()
        total = 0
        with target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    target.unlink(missing_ok=True)
                    raise ValueError(
                        f"URL download exceeds {settings.max_url_download_mb} MB limit"
                    )
                file.write(chunk)

    return target
