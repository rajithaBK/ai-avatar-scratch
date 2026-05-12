"""WebSocket signaling for WebRTC playback of a completed job MP4.

The Kokoro + MuseTalk pipeline still writes an MP4 to disk first. This module
uses aiortc to *stream* that file to the browser over WebRTC (separate video
track), which is useful for kiosk-style playback without downloading the whole
file first.

``aiortc`` is imported lazily inside the socket handler so ``import app.main``
still works in lightweight environments that have not installed the WebRTC
stack yet (``pip install -r requirements.txt`` pulls it in for real runs).

For HTTPS reverse proxies and many NAT setups, configure TURN via
``WEBRTC_ICE_SERVERS`` (see docs/TROUBLESHOOTING.md).
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import WebSocket, WebSocketDisconnect

from . import config as _config
from .job_store import JOB_STORE

log = logging.getLogger(__name__)


def _settings():
    return _config.SETTINGS


def _rtc_configuration_from_env() -> Any:
    from aiortc import RTCConfiguration, RTCIceServer

    servers: list[Any] = []
    for entry in _settings().webrtc_ice_servers:
        urls = entry.get("urls")
        if isinstance(urls, str):
            url_list = [urls]
        elif isinstance(urls, list):
            url_list = [str(u) for u in urls]
        else:
            continue
        kwargs: dict[str, Any] = {"urls": url_list}
        if entry.get("username") is not None:
            kwargs["username"] = str(entry["username"])
        if entry.get("credential") is not None:
            kwargs["credential"] = str(entry["credential"])
        servers.append(RTCIceServer(**kwargs))
    if not servers:
        servers.append(RTCIceServer(urls=["stun:stun.l.google.com:19302"]))
    return RTCConfiguration(iceServers=servers)


def _candidate_from_message(msg: dict[str, Any]) -> Optional[Any]:
    from aiortc.rtcicetransport import RTCIceCandidate
    from aiortc.sdp import candidate_from_sdp

    raw = msg.get("candidate")
    if raw is None or raw == "":
        return None
    line = str(raw)
    if line.startswith("candidate:"):
        line = line[len("candidate:") :].lstrip()
    cand: RTCIceCandidate = candidate_from_sdp(line)
    sdp_mid = msg.get("sdpMid")
    if sdp_mid is not None:
        cand.sdpMid = str(sdp_mid)
    sdp_mline_index = msg.get("sdpMLineIndex")
    try:
        cand.sdpMLineIndex = int(sdp_mline_index) if sdp_mline_index is not None else 0
    except (TypeError, ValueError):
        cand.sdpMLineIndex = 0
    return cand


async def _wire_server_ice(pc: Any, websocket: WebSocket) -> None:
    from aiortc.sdp import candidate_to_sdp

    @pc.on("icecandidate")
    async def on_ice(candidate: Optional[Any]) -> None:  # type: ignore[misc]
        if candidate is None:
            try:
                await websocket.send_json({"type": "ice", "candidate": None})
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            sdp_frag = candidate_to_sdp(candidate)
            if not sdp_frag.startswith("candidate:"):
                sdp_frag = "candidate:" + sdp_frag
            await websocket.send_json(
                {
                    "type": "ice",
                    "candidate": sdp_frag,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex,
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("Failed to relay server ICE candidate: %s", exc)


async def handle_webrtc_socket(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()

    job = JOB_STORE.get(job_id)
    if job is None:
        await websocket.send_json({"type": "error", "message": f"Unknown job_id: {job_id}"})
        return

    if job.status != "completed":
        await websocket.send_json(
            {
                "type": "error",
                "message": f"Job {job_id} is not completed yet (status={job.status}).",
            }
        )
        return

    s = _settings()
    mp4 = Path(job.output_path) if job.output_path else (s.output_dir / f"{job_id}.mp4")
    if not mp4.is_file() or mp4.stat().st_size < 512:
        await websocket.send_json(
            {"type": "error", "message": f"MP4 not available at {mp4} (missing or too small)."}
        )
        return

    # Heavy WebRTC stack (PyAV, etc.) — only import once we know the session is meaningful.
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.contrib.media import MediaPlayer

    pc: Optional[Any] = None
    player: Optional[Any] = None
    pending_remote_ice: list[Optional[Any]] = []

    try:
        pc = RTCPeerConnection(configuration=_rtc_configuration_from_env())
        await _wire_server_ice(pc, websocket)

        player = MediaPlayer(str(mp4))
        if player.video is None:
            await websocket.send_json({"type": "error", "message": "Could not open a video track from the MP4."})
            return
        pc.addTrack(player.video)
        if player.audio is not None:
            pc.addTrack(player.audio)

        async def flush_pending_ice() -> None:
            for cand in pending_remote_ice:
                await pc.addIceCandidate(cand)
            pending_remote_ice.clear()

        while True:
            try:
                msg = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Expected JSON messages over this socket."})
                continue

            mtype = msg.get("type")
            if mtype == "offer":
                sdp = msg.get("sdp")
                if not sdp:
                    await websocket.send_json({"type": "error", "message": "Missing sdp on offer."})
                    continue
                await pc.setRemoteDescription(RTCSessionDescription(sdp=str(sdp), type="offer"))
                await flush_pending_ice()
                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)
                await websocket.send_json(
                    {
                        "type": "answer",
                        "sdp": pc.localDescription.sdp,
                        "sdpType": pc.localDescription.type,
                    }
                )
            elif mtype == "ice":
                cand = _candidate_from_message(msg)
                if pc.remoteDescription is None:
                    pending_remote_ice.append(cand)
                else:
                    await pc.addIceCandidate(cand)
            elif mtype == "bye":
                break
            else:
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {mtype!r}"})
    except asyncio.CancelledError:  # pragma: no cover
        raise
    except ModuleNotFoundError as exc:
        log.error("WebRTC requested but aiortc is not installed: %s", exc)
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "WebRTC dependencies missing on the server. Install requirements.txt (aiortc).",
                }
            )
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        log.exception("WebRTC session failed for job_id=%s", job_id)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        if pc is not None:
            await pc.close()
        try:
            await websocket.close()
        except Exception:
            pass
