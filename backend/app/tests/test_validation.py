"""Input validation tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.validation_service import (
    MissingAssetError,
    ValidationError,
    validate_avatar_input,
    validate_text,
)


def test_empty_text_rejected():
    with pytest.raises(ValidationError):
        validate_text("")
    with pytest.raises(ValidationError):
        validate_text("    \n\t  ")


def test_long_text_rejected():
    too_long = "a" * 5000
    with pytest.raises(ValidationError):
        validate_text(too_long)


def test_normal_text_accepted():
    out = validate_text("  Hello world  ")
    assert out == "Hello world"


def test_missing_avatar_path_gives_clear_error(tmp_path: Path):
    missing = tmp_path / "does_not_exist.mp4"
    with pytest.raises(MissingAssetError) as ei:
        validate_avatar_input(missing)
    msg = str(ei.value)
    assert "Missing avatar input" in msg
    assert str(missing) in msg


def test_avatar_wrong_extension_rejected(tmp_path: Path):
    bad = tmp_path / "weird.gif"
    bad.write_bytes(b"x")
    with pytest.raises(ValidationError):
        validate_avatar_input(bad)


def test_api_rejects_empty_text(temp_assets, client):
    resp = client.post("/api/jobs", json={"text": ""})
    assert resp.status_code == 422 or resp.status_code == 400, resp.text
