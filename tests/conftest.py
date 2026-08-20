from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        engine="fake",
        allow_cpu=True,
        data_directory=tmp_path / "data",
        runtime_directory=tmp_path / "runtime",
        log_directory=tmp_path / "logs",
        hf_home=tmp_path / "data" / "model_cache",
        worker_idle_seconds=2,
        generation_timeout_seconds=10,
        app_idle_shutdown_seconds=0,
        text_chunk_target_characters=40,
        text_chunk_max_characters=60,
        max_reference_file_mb=5,
    )
    settings.ensure_directories()
    return settings


@pytest.fixture()
def app_client(test_settings):
    from fastapi.testclient import TestClient

    app = create_app(test_settings)
    with TestClient(app) as client:
        client.headers.update({"Host": f"{test_settings.host}:{test_settings.port}"})
        client.headers.update({"X-Local-Token": app.state.token})
        yield client, app
