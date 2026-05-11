"""In-memory job store with thread-safe state transitions.

This is intentionally simple: jobs live for the lifetime of the process. For
production we would back this with a real queue + database, but for the
Webex Desk demo a single-process in-memory store is the right scope.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from .schemas import JobStatus


@dataclass
class Job:
    job_id: str
    text: str
    status: JobStatus = "queued"
    message: str = "queued"
    video_url: Optional[str] = None
    mode: str = "real"
    audio_path: Optional[str] = None
    output_path: Optional[str] = None
    error: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(
        self,
        *,
        status: Optional[JobStatus] = None,
        message: Optional[str] = None,
        video_url: Optional[str] = None,
        audio_path: Optional[str] = None,
        output_path: Optional[str] = None,
        error: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> None:
        with self._lock:
            if status is not None:
                self.status = status
            if message is not None:
                self.message = message
            if video_url is not None:
                self.video_url = video_url
            if audio_path is not None:
                self.audio_path = audio_path
            if output_path is not None:
                self.output_path = output_path
            if error is not None:
                self.error = error
            if mode is not None:
                self.mode = mode


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, text: str, mode: str = "real") -> Job:
        job_id = str(uuid.uuid4())
        job = Job(job_id=job_id, text=text, mode=mode)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> Dict[str, Job]:
        with self._lock:
            return dict(self._jobs)


# Singleton used by the FastAPI app.
JOB_STORE = JobStore()


__all__ = ["Job", "JobStore", "JOB_STORE"]
