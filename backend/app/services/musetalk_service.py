"""MuseTalk lip-sync inference wrapper.

We invoke the official ``scripts.inference`` module via ``python -m`` from the
MuseTalk repo's working directory. The MuseTalk script reads its task list
from a YAML file, so we generate a per-job YAML pointing at the avatar video
and the Kokoro WAV.

Reference: https://github.com/TMElyralab/MuseTalk (Quickstart -> Inference,
Windows command).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from ..config import Settings
from .validation_service import (
    MissingAssetError,
    validate_avatar_input,
    validate_musetalk_setup,
)

log = logging.getLogger(__name__)


class MuseTalkError(RuntimeError):
    """Raised when MuseTalk setup or inference fails."""


def _build_inference_yaml(avatar_path: Path, audio_path: Path, result_name: str) -> str:
    """Render the MuseTalk inference YAML payload as a string.

    The MuseTalk inference script indexes tasks by id (e.g. ``task_0:``).
    We use a single task per job and render the YAML manually so we don't
    take a hard runtime dependency on PyYAML for this path. Forward-slashes
    are used in paths so the YAML is portable across Windows/Linux without
    YAML escape edge cases.
    """

    video_path_yaml = str(avatar_path).replace("\\", "/")
    audio_path_yaml = str(audio_path).replace("\\", "/")
    result_name_yaml = result_name.replace("\\", "/")
    return (
        "task_0:\n"
        f'  video_path: "{video_path_yaml}"\n'
        f'  audio_path: "{audio_path_yaml}"\n'
        f'  result_name: "{result_name_yaml}"\n'
    )


def _find_ffmpeg_dir() -> Optional[Path]:
    """Locate a directory that contains ffmpeg(.exe).

    MuseTalk's --ffmpeg_path expects a directory; we search PATH for ffmpeg
    and return its containing directory. Returns None if not found.
    """

    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    found = shutil.which(exe)
    if not found:
        return None
    return Path(found).resolve().parent


def required_model_files(settings: Settings, *, version: str = "v15") -> List[Path]:
    """Return the model files build_command() will reference for ``version``.

    Used by validation so we can fail fast with a precise error rather than
    waiting for the MuseTalk subprocess to crash with a cryptic message.
    """

    base = settings.musetalk_checkpoint_dir
    if version == "v15":
        return [
            base / "musetalkV15" / "unet.pth",
            base / "musetalkV15" / "musetalk.json",
            base / "whisper",
        ]
    return [
        base / "musetalk" / "pytorch_model.bin",
        base / "musetalk" / "musetalk.json",
        base / "whisper",
    ]


def _python_for_musetalk(settings: Settings) -> str:
    """Return the python executable to use for the MuseTalk subprocess.

    Order of preference:
    1. ``MUSETALK_PYTHON`` env var (resolved into ``settings.musetalk_python``).
    2. Auto-detected ``third_party/MuseTalk/.venv/...python``.
    3. ``sys.executable`` (the backend's interpreter) — only correct when the
       backend was set up with all of MuseTalk's heavy deps (mmcv etc.).
    """

    if settings.musetalk_python is not None:
        return str(settings.musetalk_python)
    return sys.executable


def build_command(
    settings: Settings,
    inference_config_path: Path,
    result_dir: Path,
    output_vid_name: str,
    *,
    version: str = "v15",
    use_float16: bool = True,
) -> List[str]:
    """Construct the exact MuseTalk inference CLI command we will run."""

    if version == "v15":
        unet_model_path = settings.musetalk_checkpoint_dir / "musetalkV15" / "unet.pth"
        unet_config = settings.musetalk_checkpoint_dir / "musetalkV15" / "musetalk.json"
    else:
        unet_model_path = settings.musetalk_checkpoint_dir / "musetalk" / "pytorch_model.bin"
        unet_config = settings.musetalk_checkpoint_dir / "musetalk" / "musetalk.json"

    cmd = [
        _python_for_musetalk(settings),
        "-m",
        "scripts.inference",
        "--inference_config",
        str(inference_config_path),
        "--result_dir",
        str(result_dir),
        "--unet_model_path",
        str(unet_model_path),
        "--unet_config",
        str(unet_config),
        "--whisper_dir",
        str(settings.musetalk_checkpoint_dir / "whisper"),
        "--version",
        version,
        "--output_vid_name",
        output_vid_name,
    ]

    ffmpeg_dir = _find_ffmpeg_dir()
    if ffmpeg_dir is not None:
        cmd += ["--ffmpeg_path", str(ffmpeg_dir)]

    if use_float16:
        cmd.append("--use_float16")

    cmd += ["--batch_size", str(settings.musetalk_batch_size)]

    return cmd


def run_inference(
    settings: Settings,
    *,
    job_id: str,
    audio_path: Path,
    avatar_path: Optional[Path] = None,
    version: str = "v15",
    use_float16: bool = True,
) -> Path:
    """Run MuseTalk inference and return the path to the generated MP4.

    Raises ``MuseTalkError`` with an actionable message on any failure.
    """

    avatar = avatar_path or settings.avatar_input
    validate_avatar_input(avatar)

    if not audio_path.exists():
        raise MuseTalkError(f"Kokoro WAV not found at {audio_path}; cannot run MuseTalk.")

    problems = validate_musetalk_setup(settings)
    # Also verify that the specific model files we are about to point the CLI
    # at exist. Without this check a stale checkpoint dir slips past preflight
    # and only fails much later inside the subprocess.
    for required in required_model_files(settings, version=version):
        if not required.exists():
            problems.append(f"Required MuseTalk model path missing: {required}")
    if problems:
        msg = "MuseTalk setup is incomplete:\n  - " + "\n  - ".join(problems)
        msg += (
            "\nFollow the MuseTalk install steps in README.md and place the "
            "third_party/MuseTalk repo and its model checkpoints accordingly."
        )
        raise MuseTalkError(msg)

    if shutil.which("ffmpeg" if os.name != "nt" else "ffmpeg.exe") is None:
        raise MuseTalkError(
            "ffmpeg is not on PATH. MuseTalk shells out to ffmpeg. Install it "
            "(Windows: BtbN/FFmpeg-Builds, Linux: `sudo apt-get install ffmpeg`) "
            "and ensure `ffmpeg -version` works in your shell."
        )

    musetalk_dir = settings.musetalk_dir
    output_vid_name = f"{job_id}.mp4"
    final_output = settings.output_dir / output_vid_name

    with tempfile.TemporaryDirectory(prefix=f"musetalk_job_{job_id}_") as tmpdir:
        tmp_path = Path(tmpdir)
        inference_config = tmp_path / "inference.yaml"
        # MuseTalk's result_dir gets a `<version>/` subdir from the script.
        result_dir = tmp_path / "results"
        result_dir.mkdir(parents=True, exist_ok=True)

        inference_config.write_text(
            _build_inference_yaml(avatar, audio_path, result_name=output_vid_name),
            encoding="utf-8",
        )

        cmd = build_command(
            settings,
            inference_config_path=inference_config,
            result_dir=result_dir,
            output_vid_name=output_vid_name,
            version=version,
            use_float16=use_float16,
        )
        cmd_str = " ".join(map(_shquote, cmd))
        log.info("Running MuseTalk: %s", cmd_str)

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(musetalk_dir),
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise MuseTalkError(
                f"Could not invoke Python at {sys.executable}: {exc}"
            ) from exc

        if proc.returncode != 0:
            raise MuseTalkError(
                "MuseTalk inference failed.\n"
                f"Command: {cmd_str}\n"
                f"Working dir: {musetalk_dir}\n"
                f"Exit code: {proc.returncode}\n"
                f"--- STDOUT ---\n{proc.stdout}\n"
                f"--- STDERR ---\n{proc.stderr}"
            )

        # MuseTalk writes the file to <result_dir>/<version>/<output_vid_name>.
        produced = result_dir / version / output_vid_name
        if not produced.exists():
            # Some versions write directly into result_dir; fall back to a search.
            candidates = list(result_dir.rglob(output_vid_name))
            if not candidates:
                raise MuseTalkError(
                    "MuseTalk reported success but no MP4 was found.\n"
                    f"Expected at {produced}.\n"
                    f"--- STDOUT ---\n{proc.stdout}\n"
                    f"--- STDERR ---\n{proc.stderr}"
                )
            produced = candidates[0]

        produced_size = produced.stat().st_size
        if produced_size < 4096:
            # Anything smaller than ~4 KB is almost certainly not a valid MP4
            # (the moov atom alone is larger). We fail loudly so the operator
            # does not see "completed" with an unplayable file.
            raise MuseTalkError(
                f"MuseTalk produced a suspiciously small MP4 ({produced_size} bytes) at {produced}. "
                "Treating as failure to avoid showing an unplayable file. Check the inference logs above."
            )

        final_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(produced, final_output)
        if not final_output.exists() or final_output.stat().st_size < 4096:
            raise MuseTalkError(
                f"Failed to copy MuseTalk output to {final_output} (size too small)."
            )
        log.info(
            "MuseTalk produced %s (%d bytes) -> copied to %s",
            produced,
            produced_size,
            final_output,
        )
        return final_output


def _shquote(part: str) -> str:
    """Lightweight shell quoting for log readability (not for execution)."""

    if any(ch in part for ch in (" ", "\\", "\"")):
        return '"' + part.replace('"', r"\"") + '"'
    return part


__all__ = ["run_inference", "build_command", "MuseTalkError"]
