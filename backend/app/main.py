"""FastAPI entry point for the ai-avatar-desk-demo backend.

Endpoints:
    GET  /api/health
    POST /api/jobs
    GET  /api/jobs/{job_id}
    GET  /outputs/<job_id>.mp4   (static)
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config as _config
from .config import Settings, reload_settings
from .job_store import JOB_STORE, Job
from .schemas import (
    CreateJobRequest,
    CreateJobResponse,
    HealthResponse,
    JobStateResponse,
)
from .services import kokoro_service, musetalk_service, validation_service, video_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("avatar.api")


def _settings() -> Settings:
    """Always read the latest settings (test code can call ``reload_settings``)."""

    return _config.SETTINGS


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = _settings()
    log.info("App mode: %s", s.app_mode)
    log.info("Audio dir: %s", s.audio_dir)
    log.info("Output dir: %s", s.output_dir)
    log.info("Avatar input: %s (exists=%s)", s.avatar_input, s.avatar_input.exists())
    if s.is_mock_mode:
        try:
            video_service.ensure_mock_video(s.mock_video_path)
        except video_service.VideoError as exc:
            log.error("Failed to prepare mock video: %s", exc)
    yield


def create_app() -> FastAPI:
    s = _settings()

    app = FastAPI(
        title="AI Avatar Desk Demo Backend",
        version="0.1.0",
        description="Text -> Kokoro WAV -> MuseTalk MP4 -> browser playback.",
        lifespan=lifespan,
    )

    # CORS: in production we expect the Webex Desk web app to live on the
    # backend host or on a known LAN address. We intentionally allow any
    # origin here to make local kiosk deployment painless. Tighten for
    # internet-facing deployments.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    s.output_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs", StaticFiles(directory=str(s.output_dir)), name="outputs")

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/api/info")
    async def info() -> dict:
        s2 = _settings()
        problems = validation_service.validate_musetalk_setup(s2)
        return {
            "app_mode": s2.app_mode,
            "kokoro_available": kokoro_service.is_available(),
            "musetalk_problems": list(problems),
            "avatar_input": str(s2.avatar_input),
            "avatar_input_exists": s2.avatar_input.exists(),
            "output_dir": str(s2.output_dir),
        }

    @app.post("/api/jobs", response_model=CreateJobResponse)
    async def create_job(req: CreateJobRequest, background_tasks: BackgroundTasks) -> CreateJobResponse:
        s2 = _settings()
        job = JOB_STORE.create(text=req.text, mode="mock" if s2.is_mock_mode else "real")
        log.info("Created job %s (mode=%s, text_len=%d)", job.job_id, job.mode, len(req.text))
        background_tasks.add_task(_run_pipeline, job.job_id)
        return CreateJobResponse(
            job_id=job.job_id,
            status="queued",
            mode="mock" if job.mode == "mock" else "real",
        )

    @app.get("/api/jobs/{job_id}", response_model=JobStateResponse)
    async def get_job(job_id: str) -> JobStateResponse:
        job = JOB_STORE.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
        return JobStateResponse(
            job_id=job.job_id,
            status=job.status,
            message=job.message,
            video_url=job.video_url,
            mode="mock" if job.mode == "mock" else "real",
        )

    @app.exception_handler(validation_service.ValidationError)
    async def _on_validation(_, exc: validation_service.ValidationError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(validation_service.MissingAssetError)
    async def _on_missing(_, exc: validation_service.MissingAssetError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # Optional: serve the built React frontend from the same origin.
    # Useful when the backend is behind a single tunnel (Colab, ngrok,
    # cloudflared, AWS) so the Webex Desk only needs ONE URL. Mounted
    # last so the explicit /api and /outputs routes always win.
    frontend_dist_env = os.getenv("FRONTEND_DIST_DIR", "").strip()
    if frontend_dist_env:
        candidate = Path(frontend_dist_env)
        if not candidate.is_absolute():
            candidate = (_config.BACKEND_DIR / candidate).resolve()
    else:
        candidate = _config.REPO_ROOT / "frontend" / "dist"
    if candidate.exists() and (candidate / "index.html").exists():
        log.info("Serving frontend SPA from %s at /", candidate)
        app.mount("/", StaticFiles(directory=str(candidate), html=True), name="frontend")
    else:
        log.info("No frontend build at %s; SPA will not be served from backend.", candidate)

    return app


def _run_pipeline(job_id: str) -> None:
    """Execute the avatar pipeline for ``job_id``.

    This runs in a FastAPI BackgroundTask thread (so blocking subprocess work
    is fine here).
    """

    s = _settings()
    job = JOB_STORE.get(job_id)
    if job is None:
        log.error("Background task fired for unknown job_id=%s", job_id)
        return

    try:
        if s.is_mock_mode:
            _run_mock_pipeline(s, job)
        else:
            _run_real_pipeline(s, job)
    except validation_service.MissingAssetError as exc:
        log.warning("Job %s missing asset: %s", job.job_id, exc)
        job.update(status="failed", message=str(exc), error=str(exc))
    except validation_service.ValidationError as exc:
        log.warning("Job %s validation failed: %s", job.job_id, exc)
        job.update(status="failed", message=str(exc), error=str(exc))
    except kokoro_service.KokoroError as exc:
        log.error("Job %s kokoro error: %s", job.job_id, exc)
        job.update(status="failed", message=f"Kokoro TTS failed: {exc}", error=str(exc))
    except musetalk_service.MuseTalkError as exc:
        log.error("Job %s musetalk error: %s", job.job_id, exc)
        # Include the first ~280 chars of the error so the UI can show
        # something actionable without dumping the whole subprocess log.
        summary = str(exc).strip()
        if len(summary) > 280:
            summary = summary[:277] + "..."
        job.update(
            status="failed",
            message=f"MuseTalk failed: {summary}",
            error=str(exc),
        )
    except video_service.VideoError as exc:
        log.error("Job %s video error: %s", job.job_id, exc)
        job.update(status="failed", message=str(exc), error=str(exc))
    except Exception as exc:  # noqa: BLE001 - catch-all guard for the worker thread
        log.exception("Job %s crashed", job.job_id)
        job.update(status="failed", message=f"Unexpected error: {exc}", error=repr(exc))


def _run_mock_pipeline(s: Settings, job: Job) -> None:
    """Mock pipeline.

    Generates the real Kokoro WAV (so the operator can verify the TTS half of
    the pipeline) and renders a per-job mock MP4 with that audio muxed in.
    The video portion is a clearly-labelled "MOCK MODE" clip so it can never
    be confused with a real MuseTalk render.
    """

    job.update(status="generating_audio", message="(mock mode) generating audio with Kokoro if available")
    audio_path = s.audio_dir / f"{job.job_id}.wav"
    audio_ok = False
    try:
        if kokoro_service.is_available():
            kokoro_service.synthesize_to_wav(
                job.text,
                audio_path,
                voice=s.kokoro_voice,
                lang_code=s.kokoro_lang_code,
            )
            job.update(audio_path=str(audio_path))
            audio_ok = audio_path.exists() and audio_path.stat().st_size > 1024
        else:
            log.info("Kokoro not available; skipping WAV in mock mode.")
    except kokoro_service.KokoroError as exc:
        # Mock mode is meant to keep working even if Kokoro is broken; record it.
        log.warning("Kokoro failed in mock mode (continuing with silent mock MP4): %s", exc)
    except Exception as exc:  # noqa: BLE001 - never block mock UI on TTS issues
        log.warning("Unexpected Kokoro failure in mock mode (continuing): %s", exc)

    job.update(
        status="generating_video",
        message=(
            "(mock mode) rendering MP4 with real Kokoro audio"
            if audio_ok
            else "(mock mode) rendering silent mock MP4"
        ),
    )
    output_path = s.output_dir / f"{job.job_id}.mp4"
    video_service.render_mock_video_with_audio(
        output_path,
        audio_path=audio_path if audio_ok else None,
    )

    if not output_path.exists() or output_path.stat().st_size < 1024:
        raise video_service.VideoError(
            f"Mock MP4 was not written correctly to {output_path}"
        )

    job.update(
        status="completed",
        message=(
            "mock mode: real Kokoro speech, mock video frames (NOT real MuseTalk)"
            if audio_ok
            else "mock mode: silent mock video (Kokoro unavailable)"
        ),
        video_url=f"/outputs/{job.job_id}.mp4",
        output_path=str(output_path),
    )


def _run_real_pipeline(s: Settings, job: Job) -> None:
    """Real pipeline: Kokoro WAV -> MuseTalk MP4."""

    validation_service.validate_avatar_input(s.avatar_input)

    job.update(status="generating_audio", message="generating speech with Kokoro")
    audio_path = s.audio_dir / f"{job.job_id}.wav"
    kokoro_service.synthesize_to_wav(
        job.text,
        audio_path,
        voice=s.kokoro_voice,
        lang_code=s.kokoro_lang_code,
    )
    job.update(audio_path=str(audio_path))

    job.update(status="generating_video", message="running MuseTalk lip-sync")
    output_path = musetalk_service.run_inference(
        s,
        job_id=job.job_id,
        audio_path=audio_path,
        avatar_path=s.avatar_input,
    )

    if not output_path.exists() or output_path.stat().st_size < 4096:
        raise musetalk_service.MuseTalkError(
            f"MuseTalk completed but the final MP4 at {output_path} is missing or too small."
        )

    job.update(
        status="completed",
        message="completed",
        video_url=f"/outputs/{job.job_id}.mp4",
        output_path=str(output_path),
    )


# Module-level app for `uvicorn app.main:app`.
app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    s = _settings()
    uvicorn.run(
        "app.main:app",
        host=s.backend_host,
        port=s.backend_port,
        reload=False,
    )
