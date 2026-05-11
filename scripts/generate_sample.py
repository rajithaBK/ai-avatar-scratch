"""Generate one sample avatar video end-to-end without the HTTP layer.

This is the fastest way to verify the whole pipeline outside of pytest:

    # Mock mode (always works once requirements are installed):
    APP_MODE=mock python scripts/generate_sample.py

    # Real mode (needs MuseTalk repo, weights, ffmpeg, GPU, avatar file):
    APP_MODE=real python scripts/generate_sample.py
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import reload_settings  # noqa: E402  (import after sys.path tweak)
from app.services import (  # noqa: E402
    kokoro_service,
    musetalk_service,
    validation_service,
    video_service,
)


SAMPLE_TEXT = (
    "Hello, welcome. I am your AI assistant. This is a test video generated locally."
)


def main() -> int:
    s = reload_settings()
    job_id = uuid.uuid4().hex[:12]
    audio_path = s.audio_dir / f"sample_{job_id}.wav"
    output_path = s.output_dir / f"sample_{job_id}.mp4"

    print(f"app_mode    : {s.app_mode}")
    print(f"job id      : {job_id}")
    print(f"audio_path  : {audio_path}")
    print(f"output_path : {output_path}")

    real_mode = not s.is_mock_mode

    # 1. Kokoro WAV
    print("\n[1/2] Kokoro WAV ...")
    if kokoro_service.is_available():
        try:
            kokoro_service.synthesize_to_wav(
                SAMPLE_TEXT,
                audio_path,
                voice=s.kokoro_voice,
                lang_code=s.kokoro_lang_code,
            )
            print(f"  WAV OK ({audio_path.stat().st_size} bytes)")
        except kokoro_service.KokoroError as exc:
            print(f"  Kokoro FAILED: {exc}")
            if real_mode:
                return 1
    else:
        print("  Kokoro not installed; skipping WAV.")
        if real_mode:
            print("  Real mode requires Kokoro. Install backend/requirements.txt.")
            return 1

    # 2. Video (real or mock)
    print("\n[2/2] Video ...")
    if real_mode:
        try:
            validation_service.validate_avatar_input(s.avatar_input)
        except validation_service.MissingAssetError as exc:
            print(f"  Avatar missing: {exc}")
            return 1
        try:
            output_path = musetalk_service.run_inference(
                s,
                job_id=f"sample_{job_id}",
                audio_path=audio_path,
                avatar_path=s.avatar_input,
            )
            print(f"  REAL MuseTalk MP4 OK -> {output_path}")
            print("\nRESULT: real")
        except musetalk_service.MuseTalkError as exc:
            print(f"  MuseTalk FAILED:\n{exc}")
            return 1
    else:
        mock = video_service.ensure_mock_video(s.mock_video_path)
        video_service.copy_mock_to_output(mock, output_path)
        print(f"  MOCK MP4 written -> {output_path}")
        print("\nRESULT: mock (this MP4 is NOT a real MuseTalk render)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
