from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from config import settings


@dataclass(frozen=True)
class FrameSample:
    index: int
    timestamp_seconds: float
    image_base64: str


class FrameExtractionError(RuntimeError):
    """Raised when OpenCV cannot read useful frames from a video."""


def _target_frame_count(duration_seconds: float) -> int:
    min_frames = max(settings.min_frames, 12)
    max_frames = max(settings.max_frames, min_frames)
    if duration_seconds <= 0:
        return min_frames
    if duration_seconds < 10:
        return min(max_frames, max(min_frames, 14))
    if duration_seconds > 45:
        return max_frames
    return max(min_frames, min(max_frames, round(duration_seconds / 3)))


def _average_hash(frame: np.ndarray, hash_size: int = 8) -> int:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    mean = resized.mean()
    bits = resized > mean
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return value


def _hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def _is_low_quality_frame(frame: np.ndarray) -> bool:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return brightness < 18 or brightness > 238 or blur_score < 18


def extract_representative_frames(video_path: Path) -> list[FrameSample]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise FrameExtractionError(f"Could not open video: {video_path.name}")

    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
        if frame_count <= 0 or fps <= 0:
            raise FrameExtractionError(f"Video has invalid frame metadata: {video_path.name}")

        duration = frame_count / fps
        requested = _target_frame_count(duration)
        indexes = np.linspace(0, max(frame_count - 1, 0), num=requested, dtype=int)

        samples: list[FrameSample] = []
        seen_hashes: list[int] = []
        fallback_frames: list[tuple[int, float, np.ndarray]] = []

        for index in dict.fromkeys(indexes.tolist()):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok or frame is None:
                continue

            timestamp = round(index / fps, 2)
            fallback_frames.append((int(index), timestamp, frame))

            if _is_low_quality_frame(frame):
                continue

            frame_hash = _average_hash(frame)
            if any(_hamming_distance(frame_hash, previous) < 5 for previous in seen_hashes):
                continue
            seen_hashes.append(frame_hash)

            encoded = _encode_frame(frame)
            samples.append(FrameSample(int(index), timestamp, encoded))

        if not samples and fallback_frames:
            index, timestamp, frame = fallback_frames[0]
            samples.append(FrameSample(index, timestamp, _encode_frame(frame)))

        minimum_samples = min(requested, max(10, settings.min_frames))
        if len(samples) < minimum_samples:
            used_indexes = {sample.index for sample in samples}
            for index, timestamp, frame in fallback_frames:
                if index in used_indexes:
                    continue
                samples.append(FrameSample(index, timestamp, _encode_frame(frame)))
                used_indexes.add(index)
                if len(samples) >= minimum_samples:
                    break

        if not samples:
            raise FrameExtractionError(f"No readable frames found in {video_path.name}")

        return samples
    finally:
        capture.release()


def _encode_frame(frame: np.ndarray) -> str:
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), settings.jpeg_quality]
    ok, buffer = cv2.imencode(".jpg", frame, encode_params)
    if not ok:
        raise FrameExtractionError("Failed to encode video frame as JPEG")
    return base64.b64encode(buffer).decode("ascii")
