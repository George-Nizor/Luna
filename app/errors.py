"""Structured application errors."""

from __future__ import annotations

import uuid


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, request_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.request_id = request_id or str(uuid.uuid4())


class GenerationBusyError(Exception):
    """Raised when the single generation slot is already occupied."""


class WorkerDiedError(Exception):
    """Raised when the inference process exits without a response."""


class GenerationTimeoutError(Exception):
    """Raised when the configured generation timeout is exceeded."""
