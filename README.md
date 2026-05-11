# ai-avatar-desk-demo

A self-hosted, open-source **text → speech → lip-synced avatar video** demo
designed to run as a kiosk-style web app on a Cisco Webex Desk device. The
heavy lifting (Kokoro TTS + MuseTalk lip-sync) happens on a backend laptop
or GPU workstation — the Desk just plays the resulting MP4 in plain HTML5
video.

```
text  ─▶  Kokoro TTS  ─▶  WAV  ─▶  MuseTalk  ─▶  MP4  ─▶  Webex Desk <video>
```

No HeyGen, D-ID, ElevenLabs, OpenAI, or any other paid API. Everything runs
locally.

## Project layout

```
ai-avatar-desk-demo/
├── backend/                 # FastAPI app, Kokoro + MuseTalk wrappers, tests
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── schemas.py
│   │   ├── job_store.py
│   │   ├── services/
│   │   │   ├── kokoro_service.py
│   │   │   ├── musetalk_service.py
│   │   │   ├── video_service.py
│   │   │   └── validation_service.py
│   │   └── tests/
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/                # React + Vite kiosk UI, Playwright tests
│   ├── src/
│   ├── tests/
│   ├── package.json
│   └── playwright.config.ts
├── assets/
│   ├── avatars/             # default.mp4 lives here (see assets/avatars/README.md)
│   ├── audio/               # generated Kokoro WAVs
│   ├── outputs/             # generated MP4s served at /outputs/<job>.mp4
│   └── mock/                # auto-generated mock MP4 for mock mode
├── third_party/
│   └── MuseTalk/            # cloned manually (see third_party/README.md)
├── scripts/                 # helper scripts (Bash + PowerShell)
├── docs/
│   ├── WEBEX_DESK_DEPLOYMENT.md
│   └── TROUBLESHOOTING.md
└── .env.example
```

## Architecture

```
┌─ Browser / Webex Desk ────────────────┐    ┌─ Backend host (laptop/GPU) ─┐
│  React SPA                            │    │  FastAPI (uvicorn:8000)     │
│   - text input                        │    │   - POST /api/jobs          │
│   - status polling every 1.5s         │ ◀▶ │   - GET  /api/jobs/{id}     │
│   - <video src="/outputs/<id>.mp4">   │    │   - GET  /api/health        │
└───────────────────────────────────────┘    │   - /outputs/<id>.mp4 (MP4) │
                                             │  Kokoro 0.9.x  (Python)     │
                                             │  MuseTalk      (subprocess) │
                                             │  imageio-ffmpeg (mock)      │
                                             └─────────────────────────────┘
```

The job lifecycle is queued → generating_audio → generating_video → completed
(or failed with a clear, actionable message). The backend processes jobs in
FastAPI BackgroundTasks; the frontend just polls `GET /api/jobs/{id}`.

## API

| Method | Path                  | Notes                                                 |
|--------|----------------------|-------------------------------------------------------|
| GET    | `/api/health`         | `{ "status": "ok" }`                                  |
| GET    | `/api/info`           | Diagnostic: kokoro/musetalk/avatar status             |
| POST   | `/api/jobs`           | Body: `{ "text": "..." }` → `{ job_id, status }`      |
| GET    | `/api/jobs/{job_id}`  | Job state w/ `status`, `message`, `video_url`, `mode` |
| GET    | `/outputs/{job}.mp4`  | The rendered MP4 (static)                             |

## Prerequisites

- Python **3.10–3.12** (Kokoro 0.9.x does not support 3.13+ yet)
- Node 18+ and npm 9+
- ffmpeg on `PATH` for **real** mode. Mock mode ships with a bundled ffmpeg
  via `imageio-ffmpeg`, so basic testing works on any laptop.
- For real MuseTalk: an NVIDIA GPU with at least 4 GB VRAM and CUDA 11.x/12.x
  drivers. CPU-only works but is impractical (minutes per second of video).

## Setup

### 1. Backend

```powershell
# Windows / PowerShell
.\scripts\setup_backend.ps1
```

```bash
# Linux / macOS
bash scripts/setup_backend.sh
```

This creates `backend/.venv`, installs `requirements.txt` (FastAPI, Kokoro,
torch, soundfile, imageio-ffmpeg, …) and prints next steps.

### 2. Frontend

```powershell
.\scripts\setup_frontend.ps1
```

```bash
bash scripts/setup_frontend.sh
```

Installs npm dependencies for the Vite + React app.

### 3. ffmpeg (real mode only)

- Windows: download a static build from
  <https://github.com/BtbN/FFmpeg-Builds/releases>, extract somewhere like
  `C:\tools\ffmpeg\`, and add `C:\tools\ffmpeg\bin` to your user PATH.
- macOS: `brew install ffmpeg`
- Linux: `sudo apt-get install -y ffmpeg`

### 4. Avatar input

Place a 5–10 second face video at `assets/avatars/default.mp4`. See
`assets/avatars/README.md` for the recommended specs. Without this file
real-mode jobs fail with a clear error; mock mode keeps working.

### 5. MuseTalk (real mode only)

```powershell
cd third_party
git clone https://github.com/TMElyralab/MuseTalk.git
cd MuseTalk
.\download_weights.bat       # ~2 GB; needs internet access to Hugging Face
```

Full install (mmcv, mmdet, mmpose, etc.) is documented at
<https://github.com/TMElyralab/MuseTalk> and re-summarised in
`third_party/README.md`.

## Configuration

Copy `.env.example` to `.env` and tweak as needed:

```dotenv
APP_MODE=real            # or "mock" — see below
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_PORT=3000

ASSETS_DIR=../assets
AUDIO_DIR=../assets/audio
OUTPUT_DIR=../assets/outputs
AVATAR_INPUT=../assets/avatars/default.mp4

KOKORO_VOICE=af_heart
KOKORO_LANG_CODE=a

MUSETALK_DIR=../third_party/MuseTalk
MUSETALK_INFERENCE_SCRIPT=../third_party/MuseTalk/scripts/inference.py
MUSETALK_CHECKPOINT_DIR=../third_party/MuseTalk/models

MOCK_VIDEO_PATH=../assets/mock/mock_avatar.mp4
```

Two modes are supported:

| Mode  | Kokoro WAV         | MP4 source                              | Use it for |
|-------|--------------------|-----------------------------------------|------------|
| real  | yes (Kokoro)       | MuseTalk lip-sync of `AVATAR_INPUT`     | Production demo |
| mock  | yes (best effort)  | Pre-generated mock clip with "MOCK MODE" overlay | UI / backend / Playwright tests when MuseTalk isn't available |

The `mode` field is included in every job state response so the UI can
visibly badge mock-mode results.

## Running

### Mock mode (fastest)

```powershell
$env:APP_MODE = "mock"
.\scripts\run_backend.ps1     # Terminal 1
.\scripts\run_frontend.ps1    # Terminal 2
```

Open `http://localhost:3000` (or whatever port Vite picked).

### Real mode

```powershell
$env:APP_MODE = "real"
.\scripts\run_backend.ps1
.\scripts\run_frontend.ps1
```

You can also run the entire backend with `python -m uvicorn app.main:app
--host 0.0.0.0 --port 8000` from inside the activated `backend/.venv`.

## Tests

### Backend pytest

```powershell
.\scripts\run_tests.ps1            # 13 fast tests
.\scripts\run_tests.ps1 -Slow      # also runs the real Kokoro WAV test
```

```bash
bash scripts/run_tests.sh           # 13 fast tests
bash scripts/run_tests.sh --slow    # plus real Kokoro
```

The slow Kokoro test downloads ~327 MB of model weights to your HF cache
on first run (`~/.cache/huggingface`). Subsequent runs use the cache and
take ~12 s on CPU.

### Playwright e2e

The Playwright spec drives the SPA against a running backend (mock mode
is fine — the test only checks that "Generate Avatar Video" produces a
playable MP4 with a `<video>` element):

```powershell
cd frontend
npx playwright install chromium
npx playwright test
```

### One-shot end-to-end

```powershell
.\scripts\run_e2e_check.ps1
```

```bash
bash scripts/run_e2e_check.sh
```

## Generate a sample MP4 from the command line

```powershell
$env:APP_MODE = "mock"
.\backend\.venv\Scripts\python.exe scripts/generate_sample.py
```

This writes `assets/audio/sample_<id>.wav` and
`assets/outputs/sample_<id>.mp4` and prints whether MuseTalk or the mock
clip produced the video.

## Webex Desk deployment

See `docs/WEBEX_DESK_DEPLOYMENT.md` for the full rationale and a network
diagram. The short version:

1. Deploy this frontend (`npm run build`) behind HTTPS.
2. Add a Web App / kiosk URL on the Desk pointing at the deployed
   frontend.
3. Keep the Python backend (Kokoro + MuseTalk) on a separate machine that
   the Desk can reach over the network.

## Running real-mode (need a GPU)

Real MuseTalk inference (an actual lip-synced face video instead of the mock
placeholder) needs a CUDA GPU. Two paths are scripted in this repo:

| Use case | Doc | What you get |
|---|---|---|
| Quick proof — show stakeholders the real pipeline works | `docs/COLAB_QUICKSTART.md` + `scripts/colab/avatar_demo.ipynb` | Free Colab T4 GPU, public `*.trycloudflare.com` URL, ~25 min first-run setup |
| Permanent demo / production | `docs/AWS_DEPLOYMENT.md` + `scripts/aws_bootstrap.sh` | Single `g4dn.xlarge` EC2 (~$0.55/hr on-demand), Caddy + Let's Encrypt HTTPS, systemd unit, ~30 min first-run setup |

The notebook and the bash bootstrap both produce the same final state — a
FastAPI backend serving the SPA + API + MP4s from a single origin, real
Kokoro speech, real MuseTalk lip-sync. Use Colab to validate the demo,
then move to AWS for a stable URL.

## Troubleshooting

See `docs/TROUBLESHOOTING.md` for SSL/HF Hub stalls, MuseTalk path issues,
CUDA gotchas, ffmpeg, and so on.
