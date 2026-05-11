# Google Colab quickstart (real-mode demo, free GPU)

Use this when you need to **prove the project works** before you have a
permanent GPU box (e.g. before getting AWS access). Colab gives you a free
T4 GPU + Python 3.10 + CUDA 11.8, which is exactly what MuseTalk wants.

> **This is a proof-of-concept, not a production deployment.** Free Colab
> kicks idle sessions off after ~90 min, the public tunnel URL changes
> every session, and the GPU is best-effort. Use it to validate the
> pipeline and screenshot/record the demo, then move to AWS or another
> permanent host for real use.

## What you need

1. A Google account (free Colab tier is fine).
2. A 5–10 second face video (MP4) to use as the avatar — see
   `assets/avatars/README.md` for tips.
3. The `ai-avatar-desk-demo` repo, ideally pushed to GitHub so the
   notebook can `git clone` it. (Zip upload and Drive copy also work; see
   cell 3 of the notebook.)

## Steps

1. Open <https://colab.research.google.com>.
2. **File → Upload notebook** → pick
   `scripts/colab/avatar_demo.ipynb` from this repo.
3. **Runtime → Change runtime type → Hardware accelerator: GPU (T4)
   → Save**.
4. (Recommended) Mount Google Drive in cell 2 so MuseTalk's ~2 GB of
   weights are cached between sessions.
5. Edit cell 3 with the URL of your fork:
   ```python
   GIT_URL = 'https://github.com/<your-user>/ai-avatar-desk-demo.git'
   ```
   If you haven't pushed it, the same cell shows commented-out
   alternatives for zip upload and Drive copy.
6. Run cells 1 → 8 in order. The slow one is cell 5 (~15 min the first
   time; ~10 s on subsequent sessions if Drive caching is on).
7. Cell 6 prompts you to upload your avatar MP4 from your laptop.
8. Cell 8 prints a public URL like
   `https://random-words-here.trycloudflare.com`. Open that in a browser
   on **any** device — your laptop, your phone, your Webex Desk.

You're now running the same UI you've been testing locally, but the
backend is on a Colab T4 GPU and producing **real MuseTalk lip-sync MP4s**
instead of mock placeholders.

## Architecture

```
┌────────────────────────┐                 ┌──────────────────────────────┐
│ Your laptop / Desk     │      HTTPS      │ Google Colab runtime         │
│  Webex Desk Web App    │ ──────────────▶ │  Python 3.10 + CUDA 11.8     │
│  React SPA             │                 │  uvicorn :8000               │
│   (served from Colab)  │                 │   ├─ FastAPI                 │
└────────────────────────┘                 │   ├─ Kokoro TTS (CPU)        │
                                            │   └─ MuseTalk (T4 GPU)       │
              ▲                            │                              │
              │       *.trycloudflare.com  │  cloudflared quick-tunnel    │
              └────────────────────────────┤  (anonymous, no auth)        │
                                            └──────────────────────────────┘
```

One URL serves three things:

| Path             | Served by                                                  |
|------------------|------------------------------------------------------------|
| `/`              | React SPA (built into `frontend/dist`, mounted by FastAPI) |
| `/api/*`         | FastAPI routes (jobs, health, info)                        |
| `/outputs/*.mp4` | Static MP4s rendered by MuseTalk                           |

That's why the SPA does not need `VITE_BACKEND_URL` set on Colab —
everything is same-origin through the tunnel.

## Caveats and mitigations

| Caveat | Mitigation |
|---|---|
| Free Colab idle-disconnects after ~90 min | Re-run cell 8 to relaunch + get a new tunnel URL. Cells 4–7 stay in the runtime if it didn't fully restart. |
| Tunnel URL changes every session | Use Colab Pro + a named Cloudflare tunnel (sign-in required) for a stable URL. Or move to AWS for production. |
| GPU not always available on free tier | Colab Pro ($10/mo) gives priority allocation. Or wait a few minutes and retry. |
| 2 GB weight download per session | Mount Drive in cell 2 to cache them. Reduces session 2+ to ~3 min total. |
| MuseTalk first-job latency | The script extracts and pickles landmarks from your avatar on the first job. Job 2 onwards is 2–3× faster. Don't judge speed by your first job. |
| You forget your avatar is a placeholder | Make sure you upload a real face MP4 in cell 6. The placeholder option is purely so the pipeline can run end-to-end at all without an upload. |

## How this maps to the AWS production path

Cell 8 already writes a `.env` with `MUSETALK_PYTHON` pointing at the
Colab system Python. The same `.env` (with paths adjusted) drops onto
the EC2 box untouched — see `docs/AWS_DEPLOYMENT.md`. The single line
that's "Colab-specific" is the `cloudflared` tunnel; on AWS the same role
is played by Caddy + Let's Encrypt.

So the sequence is:

1. Use Colab to prove the pipeline (~25 min first time).
2. Use the recorded demo / screenshot to get AWS access approved.
3. Run `scripts/aws_bootstrap.sh` on a `g4dn.xlarge` for the permanent
   home of the demo.

## Troubleshooting

**"No GPU detected"** — Runtime → Change runtime type → GPU → Save → Connect.

**"`mim install` is taking forever"** — That's normal. mmcv compiles or
downloads ~150 MB; ~5 min on the first run.

**"Cell 5 fails with: `OSError: [Errno 28] No space left on device`"** —
You disabled Drive caching but Colab gave you a small disk. Open Runtime
→ Disconnect and delete runtime, then start over with the Drive option
enabled (cell 2).

**"Cell 8 hangs on `Cloudflare tunnel did not come up`"** — The first
attempt sometimes takes 60+ s in some Colab regions. Re-run cell 8.

**"Backend log says `MuseTalk failed`"** — Run `!tail -200 /tmp/uvicorn.log`
to see the captured stdout/stderr from the MuseTalk subprocess. The most
common cause is the avatar input being missing or corrupt; re-upload via
cell 6 and re-run cell 8.

**"It works in Colab but not on the Webex Desk"** — The Desk's Web Engine
has stricter cert handling. The `*.trycloudflare.com` cert is publicly
trusted, but some corporate firewalls block `*.trycloudflare.com` URLs as
"unknown". If your Desk is on a corporate network with strict outbound
filtering, you may need a named tunnel on a custom corporate domain
(Cloudflare account required). Easier just to move to AWS at that point.
