# Webex Desk deployment notes

The Webex Desk web engine renders the **frontend only**. All AI work
(Kokoro, MuseTalk, ffmpeg) happens on a separate laptop / server / workstation
that the Desk reaches over the network.

## Architecture

```
┌────────────────────────┐        ┌──────────────────────────────────────────┐
│ Cisco Webex Desk        │ HTTPS  │ AI backend host (laptop / GPU server)    │
│  (Web Engine kiosk)     │ ─────▶ │  uvicorn:8000                            │
│  - HTML5 video <video>  │        │   ├─ Kokoro TTS (CPU/GPU)                │
│  - Plain MP4 playback   │        │   ├─ MuseTalk inference (CUDA GPU)       │
│  - Touch-friendly UI    │ ◀───── │   └─ /outputs/<job_id>.mp4 (static)      │
└────────────────────────┘ MP4 GET └──────────────────────────────────────────┘
```

The Desk fetches both the SPA and the rendered MP4 from the backend host.
There is no live media (no WebRTC, no HLS) in this version.

## What runs where

| Component         | Runs on Desk? | Runs on backend? |
|-------------------|--------------|------------------|
| Static HTML/JS/CSS | ✅            | ✅ (served)       |
| Kokoro TTS        | ❌            | ✅                |
| MuseTalk          | ❌            | ✅                |
| ffmpeg            | ❌            | ✅                |
| MP4 playback      | ✅            | ❌                |

## Network requirements

1. The Desk and the backend must be on a network that allows the Desk to
   reach the backend's IP and port. Quickest options:
   - Same L2 / VLAN as the laptop.
   - A reverse proxy on the LAN that exposes `https://<host>:443` and
     proxies to the laptop's `:8000`.
2. Port 80 / 443 are easiest if your environment forces HTTPS-only on
   managed devices. Use `nginx`, `caddy`, or `traefik` with Let's Encrypt
   if you need a public DNS name.
3. If the Desk's WebExtensions/Web Apps policy demands HTTPS, you must
   put the backend behind a TLS-terminating proxy. Browser policies in
   recent Webex Desks reject mixed-content video sources.

## Frontend kiosk setup

1. Build the frontend (`cd frontend && npm run build`). The static files
   are emitted into `frontend/dist/`. Either:
   - Serve `dist/` from `nginx` / a CDN.
   - Or point the Desk at the running Vite dev server (less polished).
2. From the Webex Control Hub or `xConfiguration WebEngine` configure a
   custom Web App pointed at the deployed URL, e.g.
   `https://avatar-demo.example.com/`.
3. Confirm the UI loads, taps work, and the in-page video element shows
   the generated MP4 with on-screen controls.

## Why MP4 only (and not HLS / WebRTC)

The Webex Desk Web Engine reliably plays standard `<video>` MP4 with
`H.264 + AAC`. It does not have a fully tested HLS or WebRTC pipeline for
custom Web Apps. Sticking to plain `<video src=".../foo.mp4" controls>`
keeps the UX consistent with a polished SaaS avatar demo and avoids
codec / DRM surprises.

When you need live streaming the right path is to use Webex's own SDK,
not a custom Web App.

## Recommended layout

- 1920x1080, dark UI, large rounded corners, strong contrast.
- Touch targets ≥ 56px tall.
- One action per screen (type → generate → watch).
- No `target="_blank"` links and no popups (the Web Engine cannot manage
  external windows like a desktop browser).

## Performance tips

- Cache the avatar input file on the backend so MuseTalk's coord cache
  (`<basename>.pkl`) stays warm; you'll get measurable speed-ups after
  the first job.
- Pre-render a few "demo loop" responses at startup if you want zero-wait
  on a kiosk demo path.
- Set `Cache-Control: public, max-age=3600` on the `/outputs/*.mp4` route
  if you serve through a reverse proxy. (FastAPI's `StaticFiles` keeps
  weak ETags so 304s work out of the box.)

## Security checklist

- Backend: bind to a LAN-only IP if the Desk is on the same VLAN.
- Backend: enable HTTPS via a TLS-terminating proxy when crossing
  network boundaries.
- Frontend: never embed credentials; the demo today does not need any.
- Logs: do not log the user's typed text in cleartext if it is ever
  sensitive. The default INFO log level only logs the character count.
