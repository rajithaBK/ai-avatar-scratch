"""Kokoro TTS service tests.

The real test (synthesizing audio) is gated on Kokoro being importable. If it
is not, we *fail loudly with an actionable message* rather than silently
skipping, so the operator running the demo cannot accidentally believe the
real path is healthy when it isn't.

Run as ``pytest -m "not slow"`` to skip the real model load.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import kokoro_service
from app.services.kokoro_service import KokoroError


def test_is_available_returns_bool():
    assert isinstance(kokoro_service.is_available(), bool)


def test_kokoro_rejects_empty_text(tmp_path: Path):
    out = tmp_path / "empty.wav"
    with pytest.raises(Exception):
        kokoro_service.synthesize_to_wav("", out)


@pytest.mark.slow
@pytest.mark.real_kokoro
def test_kokoro_generates_real_wav(tmp_path: Path):
    """End-to-end: Kokoro produces a valid WAV file for a short phrase."""

    if not kokoro_service.is_available():
        pytest.fail(
            "Kokoro is not installed/importable. Install with "
            "`pip install kokoro==0.9.4 soundfile` and `pip install -r backend/requirements.txt`. "
            "On Windows install espeak-ng MSI and ensure it is on PATH."
        )

    out = tmp_path / "hello.wav"
    try:
        path = kokoro_service.synthesize_to_wav(
            "Hello, this is a test.",
            out,
            voice="af_heart",
            lang_code="a",
        )
    except KokoroError as exc:
        pytest.fail(
            "Kokoro inference failed with an actionable error:\n" + str(exc)
        )

    assert path.exists(), f"WAV not written: {path}"
    size = path.stat().st_size
    assert size > 1024, f"WAV is suspiciously small ({size} bytes)"

    # Validate it is a real WAV by reading it back.
    import soundfile as sf  # type: ignore

    data, sr = sf.read(str(path))
    assert sr in (22050, 24000, 44100, 48000), f"Unexpected sample rate {sr}"
    assert len(data) > sr * 0.2, "Audio is shorter than 200ms; Kokoro likely failed silently"
