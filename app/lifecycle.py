"""Application lifecycle monitoring and runtime metadata."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Settings


def utc_now() -> datetime:
    return datetime.now(UTC)


def write_runtime_file(settings: Settings, token: str) -> Path:
    settings.runtime_directory.mkdir(parents=True, exist_ok=True)
    runtime_path = settings.runtime_directory / "app.json"
    payload = {
        "app": "luna",
        "pid": os.getpid(),
        "port": settings.port,
        "token": token,
        "started_at": utc_now().isoformat(),
    }
    temporary = runtime_path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    temporary.replace(runtime_path)
    return runtime_path


def remove_runtime_file(settings: Settings) -> None:
    try:
        (settings.runtime_directory / "app.json").unlink()
    except FileNotFoundError:
        pass


async def monitor_application(app: Any) -> None:
    while True:
        await asyncio.sleep(1)
        if app.state.shutdown_requested:
            server = getattr(app.state, "server", None)
            if server is not None:
                server.should_exit = True
            continue
        settings: Settings = app.state.settings
        if settings.app_idle_shutdown_seconds <= 0:
            continue
        manager = app.state.worker_manager
        if manager.generation_active:
            continue
        last_activity = max(app.state.last_heartbeat, app.state.last_api_activity)
        if (utc_now() - last_activity).total_seconds() >= settings.app_idle_shutdown_seconds:
            app.state.shutdown_requested = True
            server = getattr(app.state, "server", None)
            if server is not None:
                server.should_exit = True
