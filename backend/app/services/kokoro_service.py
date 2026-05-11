"""Kokoro TTS service.

Wraps the official ``kokoro`` Python package and writes a single concatenated
WAV file at ``assets/audio/<job_id>.wav``.

The Kokoro pipeline yields one chunk of audio per sentence/segment; we
concatenate them so MuseTalk consumes a single contiguous audio file.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List, Optional

from .validation_service import ValidationError, validate_text

log = logging.getLogger(__name__)


class KokoroError(RuntimeError):
    """Raised for Kokoro-specific failures with an actionable message."""


def _import_kokoro():
    """Import Kokoro lazily so the API still starts when the package is missing."""

    try:
        from kokoro import KPipeline  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on host install
        raise KokoroError(
            "Kokoro is not installed. Install it with `pip install kokoro==0.9.4 soundfile` "
            "and ensure espeak-ng is on PATH (Windows installer or `apt-get install espeak-ng`). "
            "See docs/TROUBLESHOOTING.md for details."
        ) from exc
    return KPipeline


def _concatenate(chunks: Iterable):
    """Concatenate the per-chunk audio tensors/arrays into one numpy array."""

    import numpy as np  # local import keeps cold start fast

    arrays: List[np.ndarray] = []
    for chunk in chunks:
        if hasattr(chunk, "detach"):
            # torch.Tensor -> numpy
            chunk = chunk.detach().cpu().numpy()
        arrays.append(np.asarray(chunk, dtype="float32"))
    if not arrays:
        raise KokoroError("Kokoro returned no audio chunks for the given text.")
    return np.concatenate(arrays, axis=0)


def synthesize_to_wav(
    text: str,
    out_path: Path,
    *,
    voice: str = "af_heart",
    lang_code: str = "a",
    sample_rate: int = 24000,
) -> Path:
    """Generate a WAV file from ``text`` using Kokoro and return its path.

    Parameters
    ----------
    text:
        The text to synthesize. Must be non-empty.
    out_path:
        The full file path (including .wav extension) to write the audio to.
    voice:
        Kokoro voice name (e.g. ``af_heart``, ``am_michael``).
    lang_code:
        Kokoro language code (``a`` = American English, ``b`` = British English, etc.).
    sample_rate:
        Output sample rate. Kokoro 0.9.x runs at 24000 Hz natively.
    """

    validate_text(text)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    KPipeline = _import_kokoro()

    try:
        import soundfile as sf  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise KokoroError(
            "soundfile is not installed. Install it with `pip install soundfile`."
        ) from exc

    log.info("Initialising Kokoro pipeline (lang_code=%s, voice=%s)", lang_code, voice)
    try:
        pipeline = KPipeline(lang_code=lang_code)
    except Exception as exc:
        raise KokoroError(
            "Failed to initialise Kokoro pipeline. This usually means the model "
            "weights could not be downloaded from Hugging Face or espeak-ng is "
            "missing from PATH. Original error: " + str(exc)
        ) from exc

    log.info("Generating speech for %d characters", len(text))
    try:
        generator = pipeline(text, voice=voice)
        # Newer Kokoro releases yield a ``Result`` dataclass with ``.audio``.
        # Older releases yielded a 3-tuple ``(graphemes, phonemes, audio)``.
        # We handle both so this code keeps working through minor upgrades.
        audio_chunks = []
        for i, item in enumerate(generator):
            if hasattr(item, "audio"):
                audio = item.audio
            elif isinstance(item, tuple) and len(item) >= 3:
                audio = item[2]
            else:
                audio = item
            audio_chunks.append(audio)
            log.debug("Kokoro chunk %d type=%s", i, type(audio).__name__)
    except Exception as exc:
        raise KokoroError(
            "Kokoro inference failed: " + str(exc) + ". See docs/TROUBLESHOOTING.md."
        ) from exc

    audio_array = _concatenate(audio_chunks)

    try:
        sf.write(str(out_path), audio_array, sample_rate)
    except Exception as exc:
        raise KokoroError(f"Failed to write WAV to {out_path}: {exc}") from exc

    log.info("Wrote WAV: %s (%d samples @ %d Hz)", out_path, len(audio_array), sample_rate)
    return out_path


def is_available() -> bool:
    """Return True when Kokoro can be imported (does not load weights)."""

    try:
        _import_kokoro()
        return True
    except KokoroError:
        return False


__all__ = ["synthesize_to_wav", "is_available", "KokoroError"]
