"""Health endpoint smoke test."""
from __future__ import annotations


def test_health_ok(temp_assets, client):
    resp = client.get("/api/health")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok"}


def test_info_endpoint_keys(temp_assets, client):
    resp = client.get("/api/info")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "app_mode" in body
    assert "kokoro_available" in body
    assert "musetalk_problems" in body
    assert "avatar_input" in body
