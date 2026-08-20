from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_release_splitter_produces_reassemblable_verified_chunks(tmp_path: Path) -> None:
    if os.name != "nt":
        pytest.skip("The release splitter targets Windows PowerShell paths.")
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return

    root = Path(__file__).resolve().parents[1]
    release_root = root / "release"
    fixture_root = release_root / "pytest-fixture"
    fixture_root.mkdir(parents=True, exist_ok=True)
    payload = fixture_root / "luna-test.nsis.7z"
    installer = fixture_root / "Luna-Installer-test.exe"
    output = release_root / "pytest-output"
    data = (b"Luna release fixture\n" * 140000)
    payload.write_bytes(data)
    installer.write_bytes(b"installer fixture")
    try:
        subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(root / "scripts" / "split_release_assets.ps1"),
                "-InputPath",
                str(payload),
                "-InstallerPath",
                str(installer),
                "-OutputDirectory",
                str(output),
                "-ChunkSizeBytes",
                "1048576",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        manifest = json.loads((output / "instrumenta-release.json").read_text(encoding="utf-8"))
        chunks = manifest["payload"]["chunks"]
        rebuilt = b"".join((output / chunk["asset"]).read_bytes() for chunk in chunks)
        assert rebuilt == data
        assert manifest["payload"]["sha256"] == _sha256(data)
        assert all((output / chunk["asset"]).stat().st_size < 2 * 1024**3 for chunk in chunks)
        assert all(_sha256((output / chunk["asset"]).read_bytes()) == chunk["sha256"] for chunk in chunks)
    finally:
        shutil.rmtree(fixture_root, ignore_errors=True)
        shutil.rmtree(output, ignore_errors=True)
