# Troubleshooting

## Kokoro install or download issues

Symptom: `KokoroError: Failed to initialise Kokoro pipeline ...`

Common causes:

1. **Wrong Python version.** Kokoro 0.9.x requires Python `>=3.10,<3.13`.
   Python 3.13 and 3.14 do not have wheels for several of Kokoro's
   transitive deps. Use Python 3.12.
2. **espeak-ng is not installed (Windows).**
   - Download the latest `*.msi` from https://github.com/espeak-ng/espeak-ng/releases
   - Run the installer (default location is fine).
   - Restart your terminal so `espeak-ng` is on `PATH`.
3. **Hugging Face download stalled.** If you see warnings about `xet_get`
   or progress freezes at `0%`:
   - `pip uninstall hf-xet`
   - Re-run; the standard HTTP downloader is reliable.
4. **TLS / corporate proxy blocking huggingface.co.** Symptoms:
   `[SSL: CERTIFICATE_VERIFY_FAILED]`. Fix:
   - Install `pip-system-certs` (already in `requirements.txt` on Windows)
     so Python uses the OS trust store.
   - Or set `REQUESTS_CA_BUNDLE` to your corporate CA bundle and
     `CURL_CA_BUNDLE` to the same value.

To smoke-test Kokoro outside the API:

```powershell
cd backend
.\.venv\Scripts\python.exe -c "from kokoro import KPipeline; KPipeline(lang_code='a')"
```

## MuseTalk missing model files

Symptom: `MuseTalk setup is incomplete: ...`

The backend logs *exactly* which path is missing. Cross-check against the
layout in `third_party/README.md`. Common mistakes:

- Cloned MuseTalk to `MuseTalk/` instead of `third_party/MuseTalk/`.
- Forgot to run `download_weights.bat` so `models/musetalkV15/unet.pth`
  is missing.
- Used the v1 path layout (`models/musetalk/pytorch_model.bin`) but kept
  `--version v15` (the default). Either match the version flag to the
  files you have or download the v1.5 weights.

## CUDA / GPU issues

Symptom: `torch.cuda.is_available()` returns False, jobs are extremely slow
or run out of memory.

- Make sure you installed PyTorch from the CUDA index, not the CPU index:
  `pip install torch --index-url https://download.pytorch.org/whl/cu121`.
- For laptops without an NVIDIA GPU there is no real fix — use mock mode
  (`APP_MODE=mock`) for UI demos and run real generation on a workstation.
- `nvidia-smi` should list at least one GPU. If not, the driver is the
  problem; reinstall the latest NVIDIA driver for your card.

## ffmpeg issues

Symptom (mock mode): `Failed to open MP4 writer ...`

Mock mode uses `imageio-ffmpeg`'s bundled binary; if that import fails,
reinstall:

```
pip install --force-reinstall imageio-ffmpeg
```

Symptom (real mode): MuseTalk logs `ffmpeg: command not found`.

MuseTalk shells out to ffmpeg from `os.system(...)` so it must be on
`PATH`. Install:

- Windows: download a static build from
  <https://github.com/BtbN/FFmpeg-Builds/releases> and add the `bin/`
  directory to your user `PATH`. Confirm with `ffmpeg -version`.
- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt-get install ffmpeg`

You can also pass `--ffmpeg_path` explicitly to the MuseTalk script if you
prefer not to mutate `PATH`. The backend already does this when ffmpeg
is found via `shutil.which`.

## Avatar input missing

Symptom: `Missing avatar input. Please place a professional face video at ...`

This is exactly what the README says: drop a 5–10s MP4 at
`assets/avatars/default.mp4`. See `assets/avatars/README.md` for tips.

## Output MP4 not found

Symptom: `MuseTalk reported success but no MP4 was found.`

1. Re-run with `APP_MODE=real` and watch the backend log — the full
   subprocess stdout / stderr is captured.
2. Some MuseTalk versions write to `results/<version>/<basename>.mp4`,
   others to `results/<version>/<output_vid_name>`. Our service searches
   the result directory recursively as a fallback. If you still see
   "no MP4 was found", inspect the temp dir name printed in the log.

## CORS issues

Symptom: browser console shows
`Access to fetch at 'http://...:8000' from origin 'http://...:3000' has been blocked by CORS policy`.

The dev server proxies `/api/*` and `/outputs/*` to the backend, so when
running locally you should not see this. If you deploy the frontend
separately, set the backend's CORS allowlist explicitly. Today
`backend/app/main.py` allows `*`, which is fine for a kiosk demo on a
trusted LAN; tighten it for any internet-facing deployment.

## Frontend cannot reach backend

- Confirm the backend is running: `curl http://127.0.0.1:8000/api/health`
  should return `{"status":"ok"}`.
- Check the terminal log for the exact host:port uvicorn bound to.
- The "Backend unreachable" pill in the UI updates every 10s; refresh
  after fixing the backend.

## Video does not play on Webex Desk

- Make sure the URL is HTTPS if your Desk's policy requires it
  (mixed-content rules block HTTP video on some firmware levels).
- Check the MP4 codec: it must be H.264 (`yuv420p`) + AAC. The MuseTalk
  inference script already picks `libx264` + `yuv420p`. If you tweak the
  ffmpeg pipeline yourself, keep that codec.
- The video element auto-plays muted; this is intentional because Webex
  Desk (like all browsers) blocks unmuted autoplay. The user can press
  the unmute / play button on the standard HTML5 controls.

## Mock mode vs real mode confusion

If you ever see a generated MP4 with the words "MOCK MODE" overlaid, the
backend is running in `APP_MODE=mock` and the file is **not** a real
MuseTalk render. Restart the backend with `APP_MODE=real` and ensure all
the real-mode assets are in place; the API response also includes a
`"mode"` field on every job (`"real"` or `"mock"`).

## WebRTC stream fails or never connects

The UI can play the finished MP4 two ways: classic ``<video src="/outputs/...">``
or **WebRTC** (``Start WebRTC``), which streams the same on-disk file through
aiortc after the job reaches ``completed``.

1. **ICE / NAT / HTTPS tunnels**  
   WebRTC needs working ICE (UDP and sometimes TCP). Browser and server must
   be able to exchange RTP. If you only expose the app through an HTTP(S)
   reverse proxy (for example a Cloudflare quick tunnel), **UDP host
   candidates on a private Colab IP are often unreachable** from a user's
   laptop. Configure a **TURN** relay via the ``WEBRTC_ICE_SERVERS`` environment
   variable (JSON array in the same shape as
   ``RTCPeerConnection``'s ``iceServers``). Example:

   ```bash
   export WEBRTC_ICE_SERVERS='[{"urls":"turn:turn.example.com:3478","username":"user","credential":"pass"}]'
   ```

2. **Dev server WebSocket proxy**  
   When using Vite on port 3000 with the default proxy, ``/api`` upgrades must
   reach uvicorn. The repo enables ``ws: true`` on the ``/api`` proxy so
   ``/api/webrtc/{job_id}`` signaling works.

3. **Job not completed**  
   The WebSocket rejects jobs that are still ``queued`` / ``generating_*``.
   Wait until the MP4 job shows **Completed**, then press **Start WebRTC**.

4. **ffmpeg / PyAV**  
   aiortc decodes the MP4 with PyAV/ffmpeg. The real MuseTalk path already
   requires ffmpeg on the server PATH; keep that requirement in mind if you
   strip dependencies. On **Windows**, PyAV may need **Microsoft C++ Build
   Tools** to compile from source; use **Python 3.10–3.12** where prebuilt
   wheels exist, or install the build toolchain.
