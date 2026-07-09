from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from loguru import logger
from tqdm import tqdm

from config import settings
from src.caption_generator import CaptionGenerator
from src.fireworks_client import FireworksClient
from src.frame_extractor import extract_representative_frames
from src.models import BatchResponse, ProcessingError, ProcessingStats, VideoCaptionResult
from src.style_generator import StyleGenerator
from src.utils import iter_video_files, timer, write_json


class VideoProcessor:
    def __init__(self) -> None:
        settings.ensure_directories()
        logger.add(
            settings.logs_dir / "backend.log",
            rotation="5 MB",
            retention="10 days",
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )
        client = FireworksClient()
        self.caption_generator = CaptionGenerator(client)
        self.style_generator = StyleGenerator(client)

    def process_video(self, video_path: Path, source: str = "local") -> VideoCaptionResult:
        logger.info("Processing video {}", video_path.name)
        with timer() as elapsed:
            frames = extract_representative_frames(video_path)
            description, neutral, timeline, vision_meta = self.caption_generator.generate(video_path, frames)
            captions, style_meta = self.style_generator.generate(
                neutral,
                factual_description=description,
                scene_timeline=timeline,
            )

            token_usage = {
                "vision": vision_meta.get("usage", {}),
                "style": style_meta.get("usage", {}),
                "latency_seconds": {
                    "vision": vision_meta.get("latency_seconds"),
                    "style": style_meta.get("latency_seconds"),
                },
            }
            result = VideoCaptionResult(
                video=video_path.name,
                neutral=neutral,
                factual_description=description,
                scene_timeline=timeline,
                source=source,
                processing_seconds=elapsed(),
                frame_count=len(frames),
                token_usage=token_usage,
                **captions.model_dump(),
            )
        logger.info(
            "Finished {} in {}s with {} frames",
            video_path.name,
            result.processing_seconds,
            result.frame_count,
        )
        return result

    def process_paths(self, videos: list[tuple[Path, str]], output_file: Path) -> BatchResponse:
        with timer() as elapsed:
            results: list[VideoCaptionResult] = []
            errors: list[ProcessingError] = []
            max_workers = max(1, settings.max_workers)

            if max_workers == 1 or len(videos) <= 1:
                for video_path, source in tqdm(videos, desc="Captioning videos", unit="video"):
                    try:
                        results.append(self.process_video(video_path, source=source))
                    except Exception as exc:
                        logger.exception("Failed to process {}", video_path.name)
                        errors.append(ProcessingError(video=video_path.name, error=str(exc)))
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(self.process_video, video_path, source): video_path
                        for video_path, source in videos
                    }
                    for future in tqdm(
                        as_completed(futures),
                        total=len(futures),
                        desc="Captioning videos",
                        unit="video",
                    ):
                        video_path = futures[future]
                        try:
                            results.append(future.result())
                        except Exception as exc:
                            logger.exception("Failed to process {}", video_path.name)
                            errors.append(ProcessingError(video=video_path.name, error=str(exc)))

            stats = ProcessingStats(
                total=len(videos),
                succeeded=len(results),
                failed=len(errors),
                processing_seconds=elapsed(),
            )
            response = BatchResponse(
                results=results,
                errors=errors,
                output_file=str(output_file),
                stats=stats,
            )
            self.write_results(output_file, response)
            return response

    @staticmethod
    def write_results(output_file: Path, response: BatchResponse) -> None:
        compact_results: list[dict[str, Any]] = [
            {
                "video": item.video,
                "neutral": item.neutral,
                "factual_description": item.factual_description,
                "scene_timeline": item.scene_timeline,
                "formal": item.formal,
                "sarcastic": item.sarcastic,
                "humorous_tech": item.humorous_tech,
                "humorous_non_tech": item.humorous_non_tech,
                "frame_count": item.frame_count,
                "processing_seconds": item.processing_seconds,
            }
            for item in response.results
        ]
        write_json(output_file, compact_results)


def process_default_video_folder() -> BatchResponse:
    settings.ensure_directories()
    videos = [(path, "folder") for path in iter_video_files(settings.videos_dir, settings.video_extensions)]
    if not videos:
        output_file = settings.outputs_dir / "captions.json"
        response = BatchResponse(
            results=[],
            errors=[],
            output_file=str(output_file),
            stats=ProcessingStats(total=0, succeeded=0, failed=0, processing_seconds=0.0),
        )
        write_json(output_file, [])
        return response

    processor = VideoProcessor()
    return processor.process_paths(videos, settings.outputs_dir / "captions.json")
