#!/usr/bin/env python3
"""
Download MuseTalk + auxiliary checkpoints into MUSETALK_DIR/models (Colab-friendly).

Environment:
  MUSETALK_MODELS  Absolute path to the MuseTalk `models` directory (required).
  HF_TOKEN         Optional Hugging Face token for higher rate limits / gated models.

Designed to run with the same interpreter as MuseTalk (e.g. Colab /content/py310).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time


def _root() -> str:
    try:
        return os.environ["MUSETALK_MODELS"]
    except KeyError:
        print("Set MUSETALK_MODELS to the MuseTalk models directory.", file=sys.stderr)
        sys.exit(2)


def _mkdirs(root: str) -> None:
    for d in (
        "musetalk",
        "musetalkV15",
        "syncnet",
        "dwpose",
        "face-parse-bisent",
        "sd-vae",
        "whisper",
    ):
        os.makedirs(os.path.join(root, d), exist_ok=True)


def _hf_get(label: str, repo_id: str, filename: str, local_dir: str, retries: int = 4) -> None:
    from huggingface_hub import hf_hub_download

    token = os.environ.get("HF_TOKEN")
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            print(f"[{label}] ({attempt}/{retries}) {repo_id} :: {filename}", flush=True)
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=local_dir,
                token=token,
            )
            return
        except Exception as exc:  # noqa: BLE001 — hub HTTP, I/O, timeouts
            last = exc
            print(f"[{label}] error: {exc!r}", flush=True)
            time.sleep(min(45, 5 * attempt))
    print(f"[{label}] giving up after {retries} attempts: {last!r}", file=sys.stderr)
    raise SystemExit(1) from last


def _gdown_face_parse(root: str) -> None:
    import gdown

    out = os.path.join(root, "face-parse-bisent", "79999_iter.pth")
    url = "https://drive.google.com/uc?id=154JgKpzCPW82qINcVieuPH3fZ2e0P812"
    print("[face-parse] gdown", url, flush=True)
    gdown.download(url, out, quiet=False, fuzzy=True)
    if not os.path.isfile(out) or os.path.getsize(out) < 1_000_000:
        raise RuntimeError(f"gdown face-parse output missing or too small: {out}")


def _curl_resnet(root: str) -> None:
    dest = os.path.join(root, "face-parse-bisent", "resnet18-5c106cde.pth")
    print("[face-parse] curl resnet18", flush=True)
    subprocess.check_call(
        [
            "curl",
            "-fsSL",
            "https://download.pytorch.org/models/resnet18-5c106cde.pth",
            "-o",
            dest,
        ]
    )


def main() -> None:
    root = _root()
    os.environ.pop("HF_ENDPOINT", None)
    # Speed + reliability for multi-GB LFS files when hf_transfer is installed.
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")

    _mkdirs(root)

    for repo, fn in (
        ("TMElyralab/MuseTalk", "musetalk/musetalk.json"),
        ("TMElyralab/MuseTalk", "musetalk/pytorch_model.bin"),
        ("TMElyralab/MuseTalk", "musetalkV15/musetalk.json"),
        ("TMElyralab/MuseTalk", "musetalkV15/unet.pth"),
    ):
        _hf_get("musetalk", repo, fn, root)

    for fn in ("config.json", "diffusion_pytorch_model.bin"):
        _hf_get("sd-vae", "stabilityai/sd-vae-ft-mse", fn, os.path.join(root, "sd-vae"))

    for fn in ("config.json", "pytorch_model.bin", "preprocessor_config.json"):
        _hf_get("whisper", "openai/whisper-tiny", fn, os.path.join(root, "whisper"))

    _hf_get("dwpose", "yzd-v/DWPose", "dw-ll_ucoco_384.pth", os.path.join(root, "dwpose"))

    # ~1.4 GB — often the slowest step.
    _hf_get(
        "syncnet",
        "ByteDance/LatentSync",
        "latentsync_syncnet.pt",
        os.path.join(root, "syncnet"),
        retries=6,
    )

    _gdown_face_parse(root)
    _curl_resnet(root)

    unet = os.path.join(root, "musetalkV15", "unet.pth")
    st = os.path.getsize(unet)
    if st < 1_000_000:
        raise SystemExit(f"unet.pth missing or too small ({st} bytes): {unet}")
    print("OK: unet.pth", st, "bytes at", unet, flush=True)


if __name__ == "__main__":
    main()
