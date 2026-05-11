# third_party/

This directory hosts external repos that we **do not** vendor as code. The
backend expects MuseTalk to live here:

```
third_party/
└── MuseTalk/
    ├── scripts/
    │   └── inference.py
    ├── musetalk/                # the Python package the script imports
    └── models/
        ├── musetalk/
        │   ├── musetalk.json
        │   └── pytorch_model.bin
        ├── musetalkV15/
        │   ├── musetalk.json
        │   └── unet.pth
        ├── sd-vae/
        │   ├── config.json
        │   └── diffusion_pytorch_model.bin
        ├── whisper/
        │   ├── config.json
        │   ├── pytorch_model.bin
        │   └── preprocessor_config.json
        ├── dwpose/
        │   └── dw-ll_ucoco_384.pth
        └── face-parse-bisent/
            ├── 79999_iter.pth
            └── resnet18-5c106cde.pth
```

## Quick install (Windows)

```powershell
cd third_party
git clone https://github.com/TMElyralab/MuseTalk.git
cd MuseTalk
# Use the same Python version as the backend (3.12 is fine; the upstream
# README recommends 3.10, but the inference script works with 3.12 as long
# as you can install mmcv/mmdet/mmpose for that version).
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -U openmim
mim install mmengine
mim install "mmcv==2.0.1"
mim install "mmdet==3.1.0"
mim install "mmpose==1.1.0"
.\download_weights.bat
```

The avatar pipeline shells out to MuseTalk via `python -m scripts.inference`.
The exact command we run is logged at INFO level when you submit a job.

## Why we don't vendor it

- MuseTalk has its own license and active development cadence.
- The model weights are large (>1 GB) and shouldn't live in this repo.
- Pinning a specific commit here would silently break when MuseTalk updates
  its inference script signature; we'd rather see a loud error in the logs.

## CPU-only laptops

MuseTalk is a CUDA-first project. On CPU it technically runs but is far too
slow for an interactive Webex Desk demo. Use mock mode (`APP_MODE=mock`) on
machines without a CUDA GPU; route real-mode jobs to a workstation with at
least an NVIDIA RTX 3050 / 4 GB VRAM (the upstream README's minimum spec).
