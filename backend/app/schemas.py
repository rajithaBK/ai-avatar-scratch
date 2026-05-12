"""Pydantic schemas for the public API."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


JobStatus = Literal[
    "queued",
    "generating_audio",
    "generating_video",
    "completed",
    "failed",
]


# Limit imposed at the API boundary. Kokoro can synthesize long passages but
# we keep an upper bound to make abuse / accidental huge inputs explicit.
MAX_TEXT_LENGTH = 2000


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class CreateJobRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize into the avatar video")

    @field_validator("text")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("text must be a string")
        stripped = v.strip()
        if not stripped:
            raise ValueError("text must not be empty")
        if len(stripped) > MAX_TEXT_LENGTH:
            raise ValueError(
                f"text is too long ({len(stripped)} chars); max allowed is {MAX_TEXT_LENGTH}"
            )
        return stripped


class CreateJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    mode: Literal["real", "mock"]


class JobStateResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    video_url: Optional[str] = None
    mode: Literal["real", "mock"]
    # Full backend / subprocess detail when status == failed (not truncated).
    error: Optional[str] = None


__all__ = [
    "HealthResponse",
    "CreateJobRequest",
    "CreateJobResponse",
    "JobStateResponse",
    "JobStatus",
    "MAX_TEXT_LENGTH",
]
