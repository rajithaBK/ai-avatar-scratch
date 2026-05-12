"""Tests for the MuseTalk command/preflight wiring.

We can't actually run MuseTalk without GPU/CUDA, model weights, and ffmpeg,
so these tests focus on the parts we *can* exercise deterministically:

* the YAML payload we feed to scripts.inference is well-formed
* build_command() generates the same flags the upstream README documents
* preflight catches missing model files (not just missing top-level dirs)
* the configured MUSETALK_PYTHON env var is actually honoured
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.config import reload_settings
from app.services import musetalk_service
from app.services.musetalk_service import (
    MuseTalkError,
    _build_inference_yaml,
    build_command,
    required_model_files,
)


def test_build_inference_yaml_has_expected_fields(tmp_path: Path):
    avatar = tmp_path / "avatar.mp4"
    audio = tmp_path / "speech.wav"
    avatar.write_bytes(b"x")
    audio.write_bytes(b"x")

    text = _build_inference_yaml(avatar, audio, result_name="job123.mp4")
    assert "task_0:" in text
    assert "video_path:" in text
    assert "audio_path:" in text
    assert "result_name:" in text
    # Forward slashes only, so the same YAML works on both Windows and Linux.
    assert "\\" not in text, text


def test_build_command_uses_v15_paths_and_required_flags(temp_assets, tmp_path: Path):
    settings = reload_settings()
    cfg = tmp_path / "task.yaml"
    out = tmp_path / "out"
    cmd = build_command(settings, cfg, out, "job123.mp4", version="v15")
    # ``-m scripts.inference`` is what the upstream README docs show on Windows.
    assert "-m" in cmd and "scripts.inference" in cmd
    assert "--inference_config" in cmd and str(cfg) in cmd
    assert "--unet_model_path" in cmd
    assert "--unet_config" in cmd
    assert "--whisper_dir" in cmd
    assert "--version" in cmd and "v15" in cmd
    assert "--output_vid_name" in cmd and "job123.mp4" in cmd
    # The v1.5 weights live in models/musetalkV15/.
    joined = " ".join(cmd)
    assert "musetalkV15" in joined and "unet.pth" in joined
    assert "--batch_size" in cmd


def test_build_command_v1_paths(temp_assets, tmp_path: Path):
    settings = reload_settings()
    cfg = tmp_path / "task.yaml"
    out = tmp_path / "out"
    cmd = build_command(settings, cfg, out, "job.mp4", version="v1")
    joined = " ".join(cmd)
    # MuseTalk v1 uses pytorch_model.bin under models/musetalk/.
    assert "pytorch_model.bin" in joined


def test_build_command_honours_musetalk_python_env(monkeypatch, temp_assets, tmp_path: Path):
    fake_python = tmp_path / "fake_python.exe"
    fake_python.write_bytes(b"")
    monkeypatch.setenv("MUSETALK_PYTHON", str(fake_python))
    settings = reload_settings()
    cmd = build_command(settings, tmp_path / "x.yaml", tmp_path / "out", "j.mp4")
    assert cmd[0] == str(fake_python), cmd
    assert cmd[0] != sys.executable


def test_required_model_files_v15(temp_assets):
    settings = reload_settings()
    files = required_model_files(settings, version="v15")
    paths = [p.name for p in files]
    assert "unet.pth" in paths
    assert "musetalk.json" in paths
    # whisper is a directory, not a file.
    assert any("whisper" in str(p) for p in files)


def test_run_inference_fails_when_model_files_missing(temp_assets, tmp_path: Path):
    """Preflight must catch missing checkpoint files, not just dirs."""

    settings = reload_settings()
    # Create the top-level dirs so the *coarse* check passes ...
    settings.musetalk_dir.mkdir(parents=True, exist_ok=True)
    settings.musetalk_inference_script.parent.mkdir(parents=True, exist_ok=True)
    settings.musetalk_inference_script.write_text("# fake")
    settings.musetalk_checkpoint_dir.mkdir(parents=True, exist_ok=True)

    audio = tmp_path / "fake.wav"
    audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")

    # ... but the specific model files do NOT exist, so we must still fail.
    with pytest.raises(MuseTalkError) as ei:
        musetalk_service.run_inference(
            settings,
            job_id="test",
            audio_path=audio,
            avatar_path=settings.avatar_input,
        )
    msg = str(ei.value)
    # The error must name at least one of the required model paths.
    assert "unet.pth" in msg or "musetalk.json" in msg or "whisper" in msg, msg
