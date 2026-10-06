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


def test_release_build_ships_no_python_runtime() -> None:
    root = Path(__file__).resolve().parents[1]
    build_script = (root / "scripts" / "build_installer.ps1").read_text(encoding="utf-8")
    builder_config = (root / "electron-builder.config.cjs").read_text(encoding="utf-8")
    release_docs = " ".join((root / "docs" / "releasing.md").read_text(encoding="utf-8").split())

    # The installed-payload repack and the reviewed-runtime gate existed only to redistribute Python.
    for retired in ("InstalledPayloadRoot", "LUNA_INSTALLED_PAYLOAD_ROOT", "VOICE_STUDIO_PYTHON_BASE", "IncludeModels"):
        assert retired not in build_script and retired not in builder_config
    assert not (root / "scripts" / "prepare_public_runtime.py").exists()
    assert "UvArchiveSha256" in build_script
    assert "first start" in release_docs


def _powershell() -> str:
    if os.name != "nt":
        pytest.skip("The release splitter targets Windows PowerShell paths.")
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell is not available.")
    return powershell


def _split(powershell: str, root: Path, payload: Path, installer: Path, output: Path, chunk: int) -> dict:
    subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(root / "scripts" / "split_release_assets.ps1"),
         "-InputPath", str(payload), "-InstallerPath", str(installer), "-OutputDirectory", str(output), "-ChunkSizeBytes", str(chunk)],
        check=True, capture_output=True, text=True,
    )
    return json.loads((output / "instrumenta-release.json").read_text(encoding="utf-8"))


def test_small_payload_is_one_asset_under_its_own_name() -> None:
    powershell = _powershell()
    root = Path(__file__).resolve().parents[1]
    fixture_root = root / "release" / "pytest-single"
    output = root / "release" / "pytest-single-output"
    fixture_root.mkdir(parents=True, exist_ok=True)
    payload = fixture_root / "luna-test-x64.nsis.7z"
    installer = fixture_root / "Luna-Installer-test.exe"
    payload.write_bytes(b"small payload" * 1000)
    installer.write_bytes(b"installer fixture")
    try:
        manifest = _split(powershell, root, payload, installer, output, 1048576)
        assert [chunk["asset"] for chunk in manifest["payload"]["chunks"]] == [payload.name]
        assert manifest["payload"]["assembledAsset"] == payload.name
        assert manifest["payload"]["sha256"] == manifest["payload"]["chunks"][0]["sha256"] == _sha256(payload.read_bytes())
        assert manifest["minimumInstrumentaVersion"] == "0.10.0"
    finally:
        shutil.rmtree(fixture_root, ignore_errors=True)
        shutil.rmtree(output, ignore_errors=True)


def test_release_splitter_produces_reassemblable_verified_chunks(tmp_path: Path) -> None:
    powershell = _powershell()

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
        manifest = _split(powershell, root, payload, installer, output, 1048576)
        chunks = manifest["payload"]["chunks"]
        assert [chunk["asset"] for chunk in chunks] == [f"{payload.name}.part{index:03d}" for index in range(1, 4)]
        rebuilt = b"".join((output / chunk["asset"]).read_bytes() for chunk in chunks)
        assert rebuilt == data
        assert manifest["payload"]["sha256"] == _sha256(data)
        assert all((output / chunk["asset"]).stat().st_size < 2 * 1024**3 for chunk in chunks)
        assert all(_sha256((output / chunk["asset"]).read_bytes()) == chunk["sha256"] for chunk in chunks)
    finally:
        shutil.rmtree(fixture_root, ignore_errors=True)
        shutil.rmtree(output, ignore_errors=True)
