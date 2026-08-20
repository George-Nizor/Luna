"""Private Uvicorn backend started and stopped by the Electron shell."""

from __future__ import annotations

import uvicorn

from .main import app


def main() -> None:
    settings = app.state.settings
    config = uvicorn.Config(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower())
    server = uvicorn.Server(config)
    app.state.server = server
    server.run()
