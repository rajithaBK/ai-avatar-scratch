"""Job lifecycle tests."""
from __future__ import annotations

import time
from pathlib import Path

import pytest


def _wait_for_terminal(client, job_id: str, *, timeout: float = 60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.2)
    raise AssertionError(f"Job {job_id} did not reach a terminal state within {timeout}s")


def test_create_and_poll_mock_job(mock_mode, client):
    """Mock mode must complete and produce a real .mp4 in assets/outputs."""

    resp = client.post("/api/jobs", json={"text": "Hello, this is a mock test."})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    # Mode must be echoed back from the create response so the UI never
    # flashes "REAL" on a mock-mode job.
    assert body["mode"] == "mock", body
    job_id = body["job_id"]
    assert isinstance(job_id, str) and len(job_id) >= 8

    final = _wait_for_terminal(client, job_id, timeout=60.0)
    assert final["status"] == "completed", final
    assert final["video_url"] == f"/outputs/{job_id}.mp4"
    assert "mock" in final["message"].lower()
    assert final["mode"] == "mock"

    # File must actually exist on disk and be a non-empty file.
    output_path = mock_mode / "outputs" / f"{job_id}.mp4"
    assert output_path.exists(), f"Output file missing at {output_path}"
    assert output_path.stat().st_size > 1024, "Output MP4 is suspiciously small"

    # And must be reachable through the static mount.
    resp = client.get(f"/outputs/{job_id}.mp4")
    assert resp.status_code == 200, resp.text
    assert len(resp.content) > 1024


def test_unknown_job_returns_404(temp_assets, client):
    resp = client.get("/api/jobs/does-not-exist")
    assert resp.status_code == 404


def test_real_mode_fails_clearly_when_musetalk_missing(real_mode, client, monkeypatch):
    """In real mode, when MuseTalk dir is missing, we fail with an actionable message."""

    # Stub out Kokoro so we don't try to download model weights during the test.
    from app.services import kokoro_service as ks
    from app.services.kokoro_service import KokoroError

    def fake_synth(text, out_path, **_kwargs):
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a tiny but non-empty WAV-ish placeholder. The real failure we
        # are testing is in MuseTalk, not Kokoro.
        import struct

        with open(out_path, "wb") as f:
            f.write(b"RIFF" + struct.pack("<I", 36) + b"WAVEfmt " + b"\x10\x00\x00\x00")
            f.write(struct.pack("<HHIIHH", 1, 1, 24000, 24000 * 2, 2, 16))
            f.write(b"data" + struct.pack("<I", 0))
        return out_path

    monkeypatch.setattr(ks, "synthesize_to_wav", fake_synth)
    monkeypatch.setattr(ks, "is_available", lambda: True)

    resp = client.post("/api/jobs", json={"text": "Hello world"})
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]

    final = _wait_for_terminal(client, job_id, timeout=30.0)
    assert final["status"] == "failed", final
    assert "MuseTalk" in final["message"] or "musetalk" in final["message"].lower()
