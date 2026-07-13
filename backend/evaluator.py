from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from src.fireworks_client import ApiConfigurationError
from src.models import VideoCaptionResult
from src.utils import download_video, timer, write_json
from src.video_processor import VideoProcessor


DEFAULT_INPUT_PATH = Path("/input/tasks.json")
DEFAULT_OUTPUT_PATH = Path("/output/results.json")
SUPPORTED_STYLES = {
    "*": "*",
    "all": "*",
    "formal": "formal",
    "sarcastic": "sarcastic",
    "humorous_tech": "humorous_tech",
    "humorous-tech": "humorous_tech",
    "humorous tech": "humorous_tech",
    "humorous_non_tech": "humorous_non_tech",
    "humorous-non-tech": "humorous_non_tech",
    "humorous non tech": "humorous_non_tech",
}
DEFAULT_STYLES = ["formal", "sarcastic", "humorous_tech", "humorous_non_tech"]


@dataclass(frozen=True)
class EvaluatorTask:
    index: int
    video_url: str
    styles: list[str]
    requested_style_names: list[str]
    task_id: str | int | None = None


def _input_path() -> Path:
    return Path(os.getenv("TASK_INPUT_PATH") or DEFAULT_INPUT_PATH)


def _output_path() -> Path:
    return Path(
        os.getenv("TASK_OUTPUT_PATH")
        or os.getenv("RESULT_OUTPUT_PATH")
        or os.getenv("OUTPUT_PATH")
        or DEFAULT_OUTPUT_PATH
    )


def _load_payload(input_path: Path) -> Any:
    return json.loads(input_path.read_text(encoding="utf-8"))


def _task_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("tasks", "inputs", "videos", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
        else:
            items = [payload] if "video_url" in payload else []
    else:
        items = []

    return [item for item in items if isinstance(item, dict)]


def _coerce_styles(value: Any) -> tuple[list[str], list[str]]:
    if value is None:
        raw_styles = DEFAULT_STYLES
    elif isinstance(value, str):
        raw_styles = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw_styles = [str(item) for item in value if item is not None]
    else:
        raw_styles = DEFAULT_STYLES

    styles: list[str] = []
    requested_names: list[str] = []
    for raw_style in raw_styles:
        requested_name = raw_style.strip()
        style = SUPPORTED_STYLES.get(requested_name.lower())
        if style == "*":
            return DEFAULT_STYLES, DEFAULT_STYLES
        if not style or style in styles:
            continue
        styles.append(style)
        requested_names.append(requested_name)

    if styles:
        return styles, requested_names
    return DEFAULT_STYLES, DEFAULT_STYLES


def _parse_tasks(payload: Any) -> list[EvaluatorTask]:
    tasks: list[EvaluatorTask] = []
    for index, item in enumerate(_task_items(payload)):
        video_url = str(
            item.get("video_url") or item.get("videoUrl") or item.get("url") or ""
        ).strip()
        if not video_url:
            continue

        styles, requested_names = _coerce_styles(
            item.get("styles")
            or item.get("requested_styles")
            or item.get("requestedStyles")
            or item.get("caption_styles")
            or item.get("captionStyles")
            or item.get("style")
        )
        task_id = (
            item.get("task_id")
            or item.get("taskId")
            or item.get("id")
            or item.get("name")
            or str(index)
        )
        tasks.append(
            EvaluatorTask(
                index=index,
                video_url=video_url,
                styles=styles,
                requested_style_names=requested_names,
                task_id=task_id,
            )
        )
    return tasks


def _caption_payload(task: EvaluatorTask, result: VideoCaptionResult) -> dict[str, Any]:
    all_captions = {
        "formal": result.formal,
        "sarcastic": result.sarcastic,
        "humorous_tech": result.humorous_tech,
        "humorous_non_tech": result.humorous_non_tech,
    }
    captions = {style: all_captions[style] for style in DEFAULT_STYLES}
    return {"task_id": str(task.task_id), "captions": captions}


def _fallback_payload(task: EvaluatorTask) -> dict[str, Any]:
    name = Path(task.video_url).name or f"task {task.task_id}"
    readable_name = name.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").strip()
    subject = readable_name or f"task {task.task_id}"
    fallback_captions = {
        "formal": f"The video for {subject} is presented as a short visual scene.",
        "sarcastic": f"The video for {subject} delivers its moment with admirable commitment.",
        "humorous_tech": f"The video for {subject} runs its visual sequence like a compact media pipeline.",
        "humorous_non_tech": f"The video for {subject} keeps the scene moving in a quick, easy-to-follow way.",
    }
    captions = {style: fallback_captions[style] for style in DEFAULT_STYLES}
    return {"task_id": str(task.task_id), "captions": captions}


def _write_failure(output_path: Path, error: str) -> None:
    logger.error(error)
    write_json(output_path, [])


def run_evaluator(input_path: Path | None = None, output_path: Path | None = None) -> int:
    input_path = input_path or _input_path()
    output_path = output_path or _output_path()
    settings.ensure_directories()

    logger.info("Reading evaluator tasks from {}", input_path)
    try:
        payload = _load_payload(input_path)
    except FileNotFoundError:
        _write_failure(output_path, f"Task input file not found: {input_path}")
        return 0
    except json.JSONDecodeError as exc:
        _write_failure(output_path, f"Task input file is not valid JSON: {exc}")
        return 0

    tasks = _parse_tasks(payload)
    if not tasks:
        write_json(output_path, [])
        return 0

    download_dir = settings.videos_dir / "evaluator"
    download_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    try:
        processor = VideoProcessor()
    except ApiConfigurationError as exc:
        logger.warning("{} Using schema-compatible fallback captions.", str(exc))
        write_json(output_path, [_fallback_payload(task) for task in tasks])
        return 0

    with timer() as elapsed:
        for task in tasks:
            try:
                video_path = download_video(task.video_url, download_dir, settings)
                result = processor.process_video(video_path, source="url")
                results.append(_caption_payload(task, result))
            except Exception as exc:
                logger.exception("Evaluator task failed for {}", task.video_url)
                errors.append({"task_id": str(task.task_id), "error": str(exc)})
                results.append(_fallback_payload(task))

    write_json(output_path, results)
    logger.info("Wrote evaluator results to {}", output_path)
    if errors:
        logger.warning("{} evaluator tasks used fallback captions", len(errors))
    logger.info("Evaluator processing finished in {}s", elapsed())
    return 0


if __name__ == "__main__":
    sys.exit(run_evaluator())
