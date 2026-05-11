"""Video helpers used in mock mode and for ensuring a default avatar exists.

Mock mode must produce a real, playable MP4 so the frontend playback path can
be tested end-to-end without MuseTalk. We use ``imageio-ffmpeg`` (which ships
its own static ffmpeg binary) so the pipeline does not require the user to
install ffmpeg on the host system for the mock path.

When a Kokoro WAV is available we mux it into the mock MP4 so the operator
actually hears the synthesized speech and can verify the TTS half of the
pipeline end to end. The video portion is still a clearly-labelled MOCK
clip so it can never be confused with a real MuseTalk render.
"""
from __future__ import annotations

import logging
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class VideoError(RuntimeError):
    """Raised when the mock video pipeline fails."""


def _imageio_ffmpeg_exe() -> Optional[str]:
    """Return a path to a usable ffmpeg binary, or None if not available."""

    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # pragma: no cover - depends on host install
        return shutil.which("ffmpeg")


def ensure_mock_video(mock_path: Path, *, duration_s: float = 4.0, fps: int = 25) -> Path:
    """Make sure ``mock_path`` exists. If not, generate a deterministic clip.

    The generated clip is a 1080p still frame with the words "MOCK MODE" so
    nobody can confuse it with a real avatar render.
    """

    mock_path = Path(mock_path)
    mock_path.parent.mkdir(parents=True, exist_ok=True)

    if mock_path.exists() and mock_path.stat().st_size > 0:
        log.debug("Mock video already exists at %s", mock_path)
        return mock_path

    return _generate_mock_video(mock_path, duration_s=duration_s, fps=fps)


def _wav_duration_seconds(wav_path: Path) -> Optional[float]:
    """Return the duration of ``wav_path`` in seconds, or None if unreadable."""

    try:
        import soundfile as sf  # type: ignore
    except ImportError:  # pragma: no cover - soundfile is a hard dep
        return None
    try:
        info = sf.info(str(wav_path))
        return float(info.frames) / float(info.samplerate)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Could not read duration of %s: %s", wav_path, exc)
        return None


def _make_frame_factory(width: int, height: int):
    """Build a function that returns the RGB frame for time ``t`` (seconds).

    The frame has a visibly animated gradient, an audio-style equalizer band,
    and a clear "MOCK MODE — not real MuseTalk" label so nobody mistakes it
    for a real render.
    """

    import numpy as np

    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore

        try:
            font_lg = ImageFont.truetype("seguiemj.ttf", 38)
        except Exception:
            try:
                font_lg = ImageFont.truetype("arial.ttf", 38)
            except Exception:
                font_lg = ImageFont.load_default()
        try:
            font_sm = ImageFont.truetype("arial.ttf", 18)
        except Exception:
            font_sm = ImageFont.load_default()

        def make_frame(t: float) -> "np.ndarray":
            # Animated dark blue/violet background.
            phase = t * 2 * math.pi / 4.0  # 4-second loop
            r = int(15 + 15 * (0.5 + 0.5 * math.sin(phase)))
            g = int(20 + 20 * (0.5 + 0.5 * math.sin(phase + 1.0)))
            b = int(60 + 40 * (0.5 + 0.5 * math.sin(phase + 2.0)))
            img = Image.new("RGB", (width, height), (r, g, b))
            draw = ImageDraw.Draw(img)

            # Header text.
            draw.text((40, 40), "MOCK MODE", fill=(255, 220, 110), font=font_lg)
            draw.text(
                (40, 90),
                "Real Kokoro speech, not real MuseTalk video",
                fill=(220, 220, 235),
                font=font_sm,
            )

            # Pseudo equalizer bars synced to time so the user can SEE the
            # video is actually playing.
            bar_w = 18
            gap = 8
            n_bars = 18
            base_x = 40
            base_y = height - 60
            for i in range(n_bars):
                # Each bar uses a different sin frequency so it looks lively.
                amp = 0.5 + 0.5 * math.sin(phase * (1 + i * 0.25) + i * 0.6)
                h = int(8 + amp * 80)
                x0 = base_x + i * (bar_w + gap)
                y0 = base_y - h
                draw.rectangle(
                    (x0, y0, x0 + bar_w, base_y),
                    fill=(110, 200, 255),
                )

            # Time readout so motion is obvious even without sound.
            draw.text(
                (width - 130, 40),
                f"t={t:5.2f}s",
                fill=(180, 200, 240),
                font=font_sm,
            )
            return np.asarray(img)

    except ImportError:  # Pillow missing - fall back to plain animated gradient.

        def make_frame(t: float) -> "np.ndarray":
            base = np.linspace(0, 255, width, dtype=np.uint8)
            row = np.tile(base, (height, 1))
            offset = int((t * 80) % 255)
            r = (row + offset) % 255
            g = np.full_like(row, 30)
            b = (row + (offset // 2)) % 255
            return np.stack([r, g, b], axis=-1).astype(np.uint8)

    return make_frame


def _write_silent_video(
    out_path: Path, *, duration_s: float, fps: int, width: int = 960, height: int = 540
) -> Path:
    """Render a silent MP4 of ``duration_s`` seconds to ``out_path``."""

    try:
        import imageio.v2 as imageio  # type: ignore
    except ImportError as exc:
        raise VideoError(
            "imageio is required to generate the mock MP4 (pip install imageio "
            "imageio-ffmpeg). " + str(exc)
        ) from exc

    ffmpeg_path = _imageio_ffmpeg_exe()
    if ffmpeg_path is not None:
        import os

        os.environ.setdefault("IMAGEIO_FFMPEG_EXE", ffmpeg_path)

    n_frames = max(1, int(round(duration_s * fps)))
    make_frame = _make_frame_factory(width, height)

    try:
        writer = imageio.get_writer(
            str(out_path),
            fps=fps,
            codec="libx264",
            pixelformat="yuv420p",
            macro_block_size=8,
            quality=7,
        )
    except Exception as exc:
        raise VideoError(
            "Failed to open MP4 writer (need imageio-ffmpeg with a working "
            f"ffmpeg binary). Underlying error: {exc}"
        ) from exc

    try:
        for i in range(n_frames):
            writer.append_data(make_frame(i / fps))
    finally:
        writer.close()

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise VideoError(f"Mock video was not written to {out_path}")
    return out_path


def _generate_mock_video(mock_path: Path, *, duration_s: float, fps: int) -> Path:
    """Create a small but valid silent MP4 (used as the canned fallback)."""

    return _write_silent_video(mock_path, duration_s=duration_s, fps=fps)


def render_mock_video_with_audio(
    output_path: Path,
    *,
    audio_path: Optional[Path] = None,
    fps: int = 25,
    fallback_duration_s: float = 4.0,
) -> Path:
    """Render a per-job mock MP4 that matches ``audio_path`` in length and muxes the WAV.

    If ``audio_path`` is None or unreadable, falls back to a 4 s silent clip.
    Returns the path that was written.
    """

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration_s: float
    if audio_path is not None and Path(audio_path).exists():
        d = _wav_duration_seconds(Path(audio_path))
        # Clamp to a sane range so a typo doesn't render a 30 minute clip.
        duration_s = max(1.0, min(d, 120.0)) if d else fallback_duration_s
    else:
        duration_s = fallback_duration_s

    ffmpeg = _imageio_ffmpeg_exe()
    have_audio = audio_path is not None and Path(audio_path).exists() and ffmpeg is not None

    if not have_audio:
        # No audio available -> just render the silent clip directly.
        return _write_silent_video(output_path, duration_s=duration_s, fps=fps)

    # 1) Render silent video to a temp file.
    with tempfile.TemporaryDirectory(prefix="mockvid_") as tmpdir:
        silent = Path(tmpdir) / "silent.mp4"
        _write_silent_video(silent, duration_s=duration_s, fps=fps)

        # 2) Mux the Kokoro WAV in via the bundled ffmpeg.
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(silent),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        log.info("Muxing Kokoro WAV into mock MP4: %s", " ".join(cmd))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise VideoError(f"Could not invoke ffmpeg at {ffmpeg}: {exc}") from exc

        if proc.returncode != 0 or not output_path.exists() or output_path.stat().st_size < 1024:
            # Fall back to the silent video so the UI still gets *something*.
            log.warning(
                "ffmpeg mux failed (rc=%s); falling back to silent mock video.\n"
                "stderr=%s",
                proc.returncode,
                proc.stderr,
            )
            shutil.copy2(silent, output_path)

    if not output_path.exists() or output_path.stat().st_size < 1024:
        raise VideoError(f"Mock video was not written to {output_path}")
    log.info(
        "Rendered mock MP4 at %s (duration=%.2fs, audio=%s)",
        output_path,
        duration_s,
        "yes" if have_audio else "no",
    )
    return output_path


def copy_mock_to_output(mock_path: Path, output_path: Path) -> Path:
    """Copy the mock MP4 to the per-job output path."""

    mock_path = Path(mock_path)
    output_path = Path(output_path)

    if not mock_path.exists():
        raise VideoError(
            f"Mock video missing at {mock_path}; run scripts/check_environment.py "
            "or backend startup to generate it."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mock_path, output_path)
    log.info("Copied mock video to %s", output_path)
    return output_path


__all__ = [
    "ensure_mock_video",
    "copy_mock_to_output",
    "render_mock_video_with_audio",
    "VideoError",
]
