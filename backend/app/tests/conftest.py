"""Shared pytest fixtures.

Each test gets its own temporary assets/audio/output dirs, with the env vars
set to point at them, so we don't pollute the real assets/ directory.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def temp_assets(tmp_path: Path, monkeypatch) -> Path:
    """Set up a temp assets/ tree and point env vars at it.

    Returns the root assets directory.
    """

    assets = tmp_path / "assets"
    audio = assets / "audio"
    outputs = assets / "outputs"
    avatars = assets / "avatars"
    mock = assets / "mock"
    for d in (audio, outputs, avatars, mock):
        d.mkdir(parents=True, exist_ok=True)

    # Provide a tiny placeholder avatar file so validate_avatar_input passes.
    avatar = avatars / "default.mp4"
    if not avatar.exists():
        avatar.write_bytes(b"\x00\x00\x00\x20ftypisom")  # not a real mp4 but passes the file check

    monkeypatch.setenv("ASSETS_DIR", str(assets))
    monkeypatch.setenv("AUDIO_DIR", str(audio))
    monkeypatch.setenv("OUTPUT_DIR", str(outputs))
    monkeypatch.setenv("AVATAR_INPUT", str(avatar))
    monkeypatch.setenv("MOCK_VIDEO_PATH", str(mock / "mock_avatar.mp4"))
    monkeypatch.setenv("MUSETALK_DIR", str(tmp_path / "third_party" / "MuseTalk"))
    monkeypatch.setenv(
        "MUSETALK_INFERENCE_SCRIPT",
        str(tmp_path / "third_party" / "MuseTalk" / "scripts" / "inference.py"),
    )
    monkeypatch.setenv(
        "MUSETALK_CHECKPOINT_DIR",
        str(tmp_path / "third_party" / "MuseTalk" / "models"),
    )

    # Reload settings so the app picks up the patched env.
    from app.config import reload_settings

    reload_settings()
    return assets


@pytest.fixture
def mock_mode(monkeypatch, temp_assets: Path) -> Path:
    monkeypatch.setenv("APP_MODE", "mock")
    from app.config import reload_settings

    reload_settings()
    return temp_assets


@pytest.fixture
def real_mode(monkeypatch, temp_assets: Path) -> Path:
    monkeypatch.setenv("APP_MODE", "real")
    from app.config import reload_settings

    reload_settings()
    return temp_assets


@pytest.fixture
def client(monkeypatch):
    """A FastAPI TestClient bound to the app with current settings."""

    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    return TestClient(app)
