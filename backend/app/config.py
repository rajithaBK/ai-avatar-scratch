"""Configuration loaded from environment / .env.

We avoid hard-coding absolute paths. All paths are resolved relative to the
repo root unless the env var is already absolute.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional  # noqa: F401  (used in dataclass annotations)

try:
    # Loading is best-effort; the project still works without python-dotenv.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - import-time fallback
    pass


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _resolve_path(value: str, default: Path) -> Path:
    """Resolve a possibly-relative path from .env against the backend dir.

    Mirrors the .env.example which uses ``../assets/...`` style values.
    """

    if not value:
        return default
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = (BACKEND_DIR / p).resolve()
    return p


@dataclass(frozen=True)
class Settings:
    app_mode: str
    backend_host: str
    backend_port: int
    frontend_port: int

    assets_dir: Path
    audio_dir: Path
    output_dir: Path
    avatar_input: Path

    kokoro_voice: str
    kokoro_lang_code: str

    musetalk_dir: Path
    musetalk_inference_script: Path
    musetalk_checkpoint_dir: Path
    musetalk_python: Optional[Path]
    musetalk_batch_size: int

    mock_video_path: Path

    #: Browser RTCPeerConnection ``iceServers`` entries (STUN/TURN). JSON array in env
    #: ``WEBRTC_ICE_SERVERS``; see docs/TROUBLESHOOTING.md for tunnel setups.
    webrtc_ice_servers: tuple[dict[str, Any], ...]

    @property
    def is_mock_mode(self) -> bool:
        return self.app_mode.lower() == "mock"


def _load_webrtc_ice_servers() -> tuple[dict[str, Any], ...]:
    """Parse ``WEBRTC_ICE_SERVERS`` JSON (RFC 5245 style objects) or use a STUN default."""

    raw = os.getenv("WEBRTC_ICE_SERVERS", "").strip()
    if not raw:
        return ({"urls": "stun:stun.l.google.com:19302"},)
    try:
        data = json.loads(raw)
        if isinstance(data, list) and data:
            return tuple(d for d in data if isinstance(d, dict))
    except json.JSONDecodeError:
        pass
    return ({"urls": "stun:stun.l.google.com:19302"},)


def load_settings() -> Settings:
    app_mode = os.getenv("APP_MODE", "real").strip()
    backend_host = os.getenv("BACKEND_HOST", "0.0.0.0").strip()
    backend_port = int(os.getenv("BACKEND_PORT", "8000"))
    frontend_port = int(os.getenv("FRONTEND_PORT", "3000"))

    assets_dir = _resolve_path(os.getenv("ASSETS_DIR", "../assets"), REPO_ROOT / "assets")
    audio_dir = _resolve_path(os.getenv("AUDIO_DIR", "../assets/audio"), assets_dir / "audio")
    output_dir = _resolve_path(os.getenv("OUTPUT_DIR", "../assets/outputs"), assets_dir / "outputs")
    avatar_input = _resolve_path(
        os.getenv("AVATAR_INPUT", "../assets/avatars/default.mp4"),
        assets_dir / "avatars" / "default.mp4",
    )

    kokoro_voice = os.getenv("KOKORO_VOICE", "af_heart").strip()
    kokoro_lang_code = os.getenv("KOKORO_LANG_CODE", "a").strip()

    musetalk_dir = _resolve_path(os.getenv("MUSETALK_DIR", "../third_party/MuseTalk"), REPO_ROOT / "third_party" / "MuseTalk")
    musetalk_inference_script = _resolve_path(
        os.getenv("MUSETALK_INFERENCE_SCRIPT", "../third_party/MuseTalk/scripts/inference.py"),
        musetalk_dir / "scripts" / "inference.py",
    )
    musetalk_checkpoint_dir = _resolve_path(
        os.getenv("MUSETALK_CHECKPOINT_DIR", "../third_party/MuseTalk/models"),
        musetalk_dir / "models",
    )
    musetalk_python_env = os.getenv("MUSETALK_PYTHON", "").strip()
    musetalk_python: Optional[Path] = None
    if musetalk_python_env:
        musetalk_python = _resolve_path(musetalk_python_env, REPO_ROOT / musetalk_python_env)
    else:
        # Auto-detect a venv that the user created inside the MuseTalk repo
        # following the upstream README. We *do not* fall back to the backend
        # interpreter implicitly here; if a venv exists and works we prefer
        # it, otherwise the service uses ``sys.executable`` so the operator
        # decides explicitly via the env var.
        candidate = musetalk_dir / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
            "python.exe" if os.name == "nt" else "python"
        )
        if candidate.exists():
            musetalk_python = candidate

    _bs = os.getenv("MUSETALK_BATCH_SIZE", "4").strip()
    try:
        musetalk_batch_size = max(1, min(32, int(_bs)))
    except ValueError:
        musetalk_batch_size = 4

    mock_video_path = _resolve_path(
        os.getenv("MOCK_VIDEO_PATH", "../assets/mock/mock_avatar.mp4"),
        assets_dir / "mock" / "mock_avatar.mp4",
    )

    webrtc_ice_servers = _load_webrtc_ice_servers()

    audio_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        app_mode=app_mode,
        backend_host=backend_host,
        backend_port=backend_port,
        frontend_port=frontend_port,
        assets_dir=assets_dir,
        audio_dir=audio_dir,
        output_dir=output_dir,
        avatar_input=avatar_input,
        kokoro_voice=kokoro_voice,
        kokoro_lang_code=kokoro_lang_code,
        musetalk_dir=musetalk_dir,
        musetalk_inference_script=musetalk_inference_script,
        musetalk_checkpoint_dir=musetalk_checkpoint_dir,
        musetalk_python=musetalk_python,
        musetalk_batch_size=musetalk_batch_size,
        mock_video_path=mock_video_path,
        webrtc_ice_servers=webrtc_ice_servers,
    )


# Singleton settings used by the app.
SETTINGS: Settings = load_settings()


def reload_settings() -> Settings:
    """Reload settings from the environment (useful in tests)."""

    global SETTINGS
    SETTINGS = load_settings()
    return SETTINGS


__all__ = ["Settings", "SETTINGS", "load_settings", "reload_settings", "REPO_ROOT", "BACKEND_DIR"]
