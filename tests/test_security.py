from pathlib import Path

import pytest

from app.config import Settings
from app.errors import ApiError
from app.security import require_local_request, safe_child_path, sanitize_filename, validate_host_header


def test_safe_paths_and_filename():
    root = Path("C:/tmp/profiles")
    assert safe_child_path(root, "voice") == root / "voice"
    with pytest.raises(ValueError):
        safe_child_path(root, "../outside")
    assert sanitize_filename("My voice / test?.wav") == "test_.wav"


def test_token_origin_and_host_validation():
    settings = Settings()
    validate_host_header("127.0.0.1:7865", settings)
    with pytest.raises(ApiError):
        validate_host_header("0.0.0.0:7865", settings)
    with pytest.raises(ApiError):
        require_local_request(
            host_header="127.0.0.1:7865",
            origin="https://evil.example",
            token="ok",
            session_token="ok",
            settings=settings,
            state_changing=True,
        )
