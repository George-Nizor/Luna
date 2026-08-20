"""Local-only request and filesystem security helpers."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .config import ALLOWED_HOSTS, Settings
from .errors import ApiError


def new_session_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


def is_uuid4(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return parsed.version == 4 and str(parsed) == value.lower()


def safe_child_path(root: Path, child: str | Path, *, must_exist: bool = False) -> Path:
    """Resolve a child and ensure it remains within root, rejecting symlinks."""
    root_resolved = root.resolve()
    candidate = (root_resolved / Path(child)).resolve(strict=False)
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise ValueError("path escapes its storage directory")
    if must_exist and not candidate.exists():
        raise FileNotFoundError(candidate)
    current = candidate
    while current != root_resolved:
        if current.is_symlink():
            raise ValueError("symlinks are not allowed in storage paths")
        current = current.parent
    return candidate


def validate_profile_id(profile_id: str) -> str:
    if not is_uuid4(profile_id):
        raise ValueError("invalid profile id")
    return profile_id


def validate_output_id(output_id: str) -> str:
    if not is_uuid4(output_id):
        raise ValueError("invalid output id")
    return output_id


def sanitize_filename(value: str, fallback: str = "voice") -> str:
    base = Path(value).name
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-")
    return base[:80] or fallback


def validate_uploaded_filename(filename: str | None) -> str:
    if not filename:
        raise ValueError("reference audio filename is required")
    if filename != Path(filename).name or "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("invalid reference audio filename")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".wav", ".flac"}:
        raise ValueError("reference audio must be a .wav or .flac file")
    return suffix


def _allowed_origins(settings: Settings) -> set[str]:
    return {
        f"http://[{host}]:{settings.port}" if ":" in host else f"http://{host}:{settings.port}"
        for host in ALLOWED_HOSTS
    }


def validate_host_header(host_header: str | None, settings: Settings) -> None:
    if not host_header:
        raise ApiError("INVALID_ORIGIN", "A localhost Host header is required.", 400)
    parsed = urlsplit(f"//{host_header}")
    host = parsed.hostname
    try:
        port = parsed.port or 80
    except ValueError as exc:
        raise ApiError("INVALID_ORIGIN", "Requests must target the local application.", 400) from exc
    if host not in ALLOWED_HOSTS or port != settings.port:
        raise ApiError("INVALID_ORIGIN", "Requests must target the local application.", 400)


def require_local_request(
    *,
    host_header: str | None,
    origin: str | None,
    token: str | None,
    session_token: str,
    settings: Settings,
    state_changing: bool,
) -> None:
    validate_host_header(host_header, settings)
    if token != session_token:
        raise ApiError("INVALID_TOKEN", "The local session token is missing or invalid.", 403)
    if state_changing and origin is not None and origin not in _allowed_origins(settings):
        raise ApiError("INVALID_ORIGIN", "The request origin is not allowed.", 403)
