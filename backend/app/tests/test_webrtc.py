"""WebRTC config + signaling smoke tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.job_store import JOB_STORE, Job


def test_webrtc_ice_config_endpoint(mock_mode, client: TestClient) -> None:
    r = client.get("/api/webrtc/config")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("iceServers"), list)
    assert len(body["iceServers"]) >= 1


def test_webrtc_ws_unknown_job(client: TestClient) -> None:
    with client.websocket_connect("/api/webrtc/00000000-0000-0000-0000-000000000099") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "error"


def test_webrtc_ws_job_not_completed(mock_mode, client: TestClient) -> None:
    jid = "00000000-0000-0000-0000-000000000088"
    JOB_STORE._jobs[jid] = Job(job_id=jid, text="x", mode="mock", status="queued")  # type: ignore[attr-defined]
    with client.websocket_connect(f"/api/webrtc/{jid}") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "error"
    assert "not completed" in msg["message"].lower()


def test_webrtc_ws_missing_mp4(mock_mode, client: TestClient, tmp_path: Path) -> None:
    """Completed job but MP4 missing on disk → error before aiortc starts."""

    jid = "00000000-0000-0000-0000-000000000077"
    out = tmp_path / "missing.mp4"
    JOB_STORE._jobs[jid] = Job(  # type: ignore[attr-defined]
        job_id=jid,
        text="x",
        mode="mock",
        status="completed",
        output_path=str(out),
        video_url=f"/outputs/{jid}.mp4",
    )
    with client.websocket_connect(f"/api/webrtc/{jid}") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "error"
    assert "not available" in msg["message"].lower()
