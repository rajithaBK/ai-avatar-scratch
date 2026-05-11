"""Diagnostic that prints what is and isn't ready for the demo.

Usage:
    python scripts/check_environment.py

Exits 0 if mock mode is feasible, 1 otherwise. Real mode readiness is
reported separately.
"""
from __future__ import annotations

import importlib
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def _check(name: str, ok: bool, detail: str = "", *, fatal: bool = False) -> bool:
    status = "OK " if ok else ("ERR" if fatal else "WARN")
    print(f"[{status}] {name}: {detail}")
    return ok


def check_python() -> bool:
    ok = sys.version_info >= (3, 10) and sys.version_info < (3, 13)
    return _check(
        "Python version",
        ok,
        f"{sys.version.split()[0]} (Kokoro requires >=3.10,<3.13)",
        fatal=not ok,
    )


def check_node() -> bool:
    if shutil.which("node") is None:
        return _check("Node.js", False, "not on PATH", fatal=True)
    out = subprocess.run(["node", "--version"], capture_output=True, text=True)
    return _check("Node.js", True, out.stdout.strip())


def check_npm() -> bool:
    if shutil.which("npm") is None:
        return _check("npm", False, "not on PATH", fatal=True)
    out = subprocess.run(["npm", "--version"], capture_output=True, text=True, shell=(os.name == "nt"))
    return _check("npm", True, out.stdout.strip() or "(installed)")


def check_ffmpeg() -> bool:
    found = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if found:
        return _check("ffmpeg", True, found)
    # imageio-ffmpeg falls back to a bundled binary for mock mode.
    try:
        import imageio_ffmpeg  # type: ignore

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        return _check(
            "ffmpeg",
            True,
            f"bundled with imageio-ffmpeg at {bundled} (real MuseTalk still wants system ffmpeg)",
        )
    except Exception:
        return _check(
            "ffmpeg",
            False,
            "not on PATH and imageio-ffmpeg is not importable. "
            "Install via `pip install imageio-ffmpeg` or system ffmpeg.",
        )


def check_cuda() -> bool:
    try:
        import torch  # type: ignore
    except ImportError:
        return _check("CUDA", False, "torch is not importable yet")
    if torch.cuda.is_available():
        try:
            name = torch.cuda.get_device_name(0)
        except Exception:
            name = "(device 0)"
        return _check("CUDA", True, f"available; device 0 = {name}")
    return _check(
        "CUDA",
        False,
        "torch reports CUDA unavailable. MuseTalk will fall back to CPU which is impractically slow.",
    )


def check_assets() -> bool:
    expected = [
        REPO_ROOT / "assets" / "audio",
        REPO_ROOT / "assets" / "outputs",
        REPO_ROOT / "assets" / "avatars",
        REPO_ROOT / "assets" / "mock",
    ]
    all_ok = True
    for p in expected:
        ok = p.exists()
        all_ok &= ok
        _check(f"asset dir {p.relative_to(REPO_ROOT)}", ok, "" if ok else "missing")

    avatar = REPO_ROOT / "assets" / "avatars" / "default.mp4"
    _check(
        f"avatar file {avatar.relative_to(REPO_ROOT)}",
        avatar.exists(),
        f"size={avatar.stat().st_size}" if avatar.exists() else (
            "missing — required for real MuseTalk mode. See assets/avatars/README.md"
        ),
    )
    return all_ok


def check_musetalk() -> bool:
    base = REPO_ROOT / "third_party" / "MuseTalk"
    script = base / "scripts" / "inference.py"
    models = base / "models"
    ok_dir = base.exists()
    _check("MuseTalk repo", ok_dir, str(base))
    _check("MuseTalk inference script", script.exists(), str(script))
    _check("MuseTalk checkpoint dir", models.exists(), str(models))
    return ok_dir and script.exists() and models.exists()


def check_kokoro_import() -> bool:
    try:
        importlib.import_module("kokoro")
        return _check("Kokoro import", True, "from `kokoro` package")
    except ImportError as exc:
        return _check(
            "Kokoro import",
            False,
            f"failed: {exc}. Install with `pip install -r backend/requirements.txt`.",
        )


def check_port(label: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
    except OSError:
        return _check(f"port {port} ({label})", False, "already in use")
    finally:
        s.close()
    return _check(f"port {port} ({label})", True, "free")


def main() -> int:
    print(f"Repo root: {REPO_ROOT}")
    _print_section("Languages")
    py = check_python()
    node = check_node()
    npm = check_npm()

    _print_section("Tools")
    ffmpeg = check_ffmpeg()
    check_cuda()

    _print_section("Assets")
    check_assets()

    _print_section("MuseTalk (third party)")
    musetalk = check_musetalk()

    _print_section("Kokoro")
    kokoro = check_kokoro_import()

    _print_section("Ports")
    backend_port = int(os.getenv("BACKEND_PORT", "8000"))
    frontend_port = int(os.getenv("FRONTEND_PORT", "3000"))
    check_port("backend", backend_port)
    check_port("frontend", frontend_port)

    _print_section("Summary")
    mock_ok = py and node and npm and ffmpeg and kokoro
    real_ok = mock_ok and musetalk
    print(f"  Mock mode feasible : {'YES' if mock_ok else 'NO'}")
    print(f"  Real mode feasible : {'YES' if real_ok else 'NO (see warnings above)'}")
    return 0 if mock_ok else 1


if __name__ == "__main__":
    sys.exit(main())
