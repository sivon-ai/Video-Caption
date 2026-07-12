from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config import settings
from src.fireworks_client import ApiConfigurationError
from src.models import BatchResponse
from src.utils import download_video, safe_filename
from src.video_processor import VideoProcessor


FRONTEND_ORIGINS = ["https://video-caption-gold.vercel.app"]


app = FastAPI(title="AI Video Captioning Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[*settings.cors_origins, *FRONTEND_ORIGINS],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    settings.ensure_directories()


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "api_configured": settings.is_api_configured,
        "vision_model": settings.vision_model,
        "text_model": settings.text_model,
        "sampling": {
            "min_frames": settings.min_frames,
            "max_frames": settings.max_frames,
            "jpeg_quality": settings.jpeg_quality,
            "max_frame_edge": settings.max_frame_edge,
            "min_frame_edge": settings.min_frame_edge,
            "max_video_seconds": getattr(settings, "max_video_seconds", 65),
            "fast_style_max_seconds": getattr(settings, "fast_style_max_seconds", 8),
            "max_workers": settings.max_workers,
            "max_url_download_workers": settings.max_url_download_workers,
        },
    }


async def _download_url_videos(urls: list[str] | None, batch_dir: Path) -> list[tuple[Path, str]]:
    queued_urls = [url.strip() for url in urls or [] if url and url.strip()]
    if not queued_urls:
        return []

    max_workers = max(1, settings.max_url_download_workers)
    semaphore = asyncio.Semaphore(max_workers)

    async def download_one(url: str) -> Path:
        async with semaphore:
            try:
                return await asyncio.to_thread(download_video, url, batch_dir, settings)
            except Exception as exc:
                logger.exception("URL download failed: {}", url)
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not download {url}: {exc}",
                ) from exc

    downloaded = await asyncio.gather(*(download_one(url) for url in queued_urls))
    return [(path, "url") for path in downloaded]


@app.post("/api/captions/process", response_model=BatchResponse)
async def process_captions(
    files: Annotated[list[UploadFile] | None, File()] = None,
    urls: Annotated[list[str] | None, Form()] = None,
) -> BatchResponse:
    if not files and not urls:
        raise HTTPException(status_code=400, detail="Upload at least one video file or URL.")

    batch_dir = settings.videos_dir / "api" / uuid4().hex
    batch_dir.mkdir(parents=True, exist_ok=True)

    videos: list[tuple[Path, str]] = []
    for upload in files or []:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in settings.video_extensions:
            raise HTTPException(status_code=400, detail=f"Unsupported video type: {upload.filename}")

        target = batch_dir / safe_filename(upload.filename or "uploaded-video.mp4", suffix)
        written = 0
        max_bytes = settings.max_upload_mb * 1024 * 1024
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    target.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"{upload.filename} exceeds {settings.max_upload_mb} MB.",
                    )
                output.write(chunk)
        videos.append((target, "upload"))

    videos.extend(await _download_url_videos(urls, batch_dir))

    output_file = settings.outputs_dir / f"captions-{batch_dir.name}.json"
    try:
        processor = VideoProcessor()
        return await asyncio.to_thread(processor.process_paths, videos, output_file)
    except ApiConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
