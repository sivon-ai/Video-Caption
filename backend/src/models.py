from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class CaptionSet(BaseModel):
    formal: str = Field(min_length=1, max_length=1200)
    sarcastic: str = Field(min_length=1, max_length=1200)
    humorous_tech: str = Field(min_length=1, max_length=1200)
    humorous_non_tech: str = Field(min_length=1, max_length=1200)


class VideoCaptionResult(CaptionSet):
    video: str
    neutral: str
    factual_description: str
    scene_timeline: list[str] = Field(default_factory=list)
    source: str = "local"
    processing_seconds: float = 0.0
    frame_count: int = 0
    token_usage: dict[str, Any] = Field(default_factory=dict)


class ProcessingError(BaseModel):
    video: str
    error: str


class ProcessingStats(BaseModel):
    total: int
    succeeded: int
    failed: int
    processing_seconds: float


class BatchResponse(BaseModel):
    results: list[VideoCaptionResult]
    errors: list[ProcessingError] = Field(default_factory=list)
    output_file: str
    stats: ProcessingStats


class UrlRequest(BaseModel):
    url: HttpUrl
