from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("preserve_legacy", Path(__file__).resolve().parents[1] / "packaging/preserve_legacy.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_preserves_old_assets_and_retries_without_overwriting(tmp_path):
    resources = tmp_path / "resources"
    models = resources / "model-data/models/xtts"
    base = resources / "python/Lib/site-packages/rvc_python/base_model"
    models.mkdir(parents=True)
    base.mkdir(parents=True)
    (models / "checkpoint.pth").write_bytes(b"voice weights")
    (base / "hubert_base.pt").write_bytes(b"base weights")
    destination = tmp_path / "userdata/legacy"
    result = module.preserve(resources, destination)
    assert result["copied_files"] == result["verified_files"] == 2
    assert (destination / "models/xtts/checkpoint.pth").read_bytes() == b"voice weights"
    assert (destination / "rvc-runtime/base_model/hubert_base.pt").read_bytes() == b"base weights"
    assert (models / "checkpoint.pth").exists()
    assert module.preserve(resources, destination)["copied_files"] == 0
    (destination / "models/xtts/checkpoint.pth").write_bytes(b"user replacement")
    with pytest.raises(ValueError, match="existing preserved model differs"):
        module.preserve(resources, destination)
    assert (models / "checkpoint.pth").read_bytes() == b"voice weights"
    assert (destination / "models/xtts/checkpoint.pth").read_bytes() == b"user replacement"


def test_clean_install_does_not_create_a_legacy_bundle(tmp_path):
    resources = tmp_path / "resources"
    resources.mkdir()
    destination = tmp_path / "legacy"
    assert module.preserve(resources, destination)["verified_files"] == 0
    assert not destination.exists()
