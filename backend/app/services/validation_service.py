"""Validation helpers used by both the API layer and pipeline services.

Centralising the validation gives us a single place to evolve the rules and
keeps the error messages actionable for the operator running the demo.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from ..config import Settings
from ..schemas import MAX_TEXT_LENGTH

log = logging.getLogger(__name__)


class ValidationError(ValueError):
    """Raised when input validation fails."""


class MissingAssetError(FileNotFoundError):
    """Raised when a required asset (e.g. avatar) is missing.

    We use a dedicated subclass so the API layer can map it to a 4xx response
    with an actionable message instead of a generic 500.
    """


def validate_text(text: str) -> str:
    if not isinstance(text, str):
        raise ValidationError("text must be a string")
    stripped = text.strip()
    if not stripped:
        raise ValidationError("text must not be empty")
    if len(stripped) > MAX_TEXT_LENGTH:
        raise ValidationError(
            f"text is too long ({len(stripped)} chars); max allowed is {MAX_TEXT_LENGTH}"
        )
    return stripped


def validate_avatar_input(path: Path) -> Path:
    if not path.exists():
        raise MissingAssetError(
            "Missing avatar input. Please place a professional face video at "
            f"{path}"
        )
    if not path.is_file():
        raise MissingAssetError(f"Avatar input is not a file: {path}")
    if path.suffix.lower() not in {".mp4", ".mov", ".png", ".jpg", ".jpeg"}:
        # MuseTalk supports both video clips and still images, so we accept
        # the common professional formats.
        raise ValidationError(
            f"Avatar input must be one of .mp4 / .mov / .png / .jpg, got {path.suffix}"
        )
    return path


def validate_musetalk_setup(settings: Settings) -> Sequence[str]:
    """Return a list of human-readable problems with the MuseTalk install.

    Empty list means "looks good" (best-effort; we do not import MuseTalk).
    """

    problems = []
    if not settings.musetalk_dir.exists():
        problems.append(f"MuseTalk directory not found at {settings.musetalk_dir}")
    if not settings.musetalk_inference_script.exists():
        problems.append(
            f"MuseTalk inference script not found at {settings.musetalk_inference_script}"
        )
    if not settings.musetalk_checkpoint_dir.exists():
        problems.append(
            f"MuseTalk checkpoint directory not found at {settings.musetalk_checkpoint_dir}"
        )
    else:
        ck = settings.musetalk_checkpoint_dir
        # VAE path used by MuseTalk `load_all_model` is always models/sd-vae (see musetalk/utils/utils.py).
        for rel in (
            "sd-vae/config.json",
            "sd-vae/diffusion_pytorch_model.bin",
            "whisper/config.json",
            "face-parse-bisent/79999_iter.pth",
            "face-parse-bisent/resnet18-5c106cde.pth",
        ):
            p = ck / rel
            if not p.exists():
                problems.append(f"Missing MuseTalk weight file (re-run weight download): {p}")
    return problems


__all__ = [
    "ValidationError",
    "MissingAssetError",
    "validate_text",
    "validate_avatar_input",
    "validate_musetalk_setup",
]
