from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("runtime_verifier", Path(__file__).parents[1] / "scripts/verify_public_runtime.py")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def runtime_fixture(tmp_path):
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "LICENSE.txt").write_text("Example licence")
    (root / "payload.dll").write_bytes(b"reviewed bytes")
    (root / "runtime-manifest.json").write_text(json.dumps({"packages": [{"name": "demo", "version": "1", "noticeFile": "LICENSE.txt"}]}))
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"packages": {"demo": "1"}}))
    rows = [hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name for p in root.iterdir()]
    (root / "runtime-files.sha256").write_text("\n".join(rows))
    return root, plan


def test_reviewed_runtime_rejects_modified_and_unrecorded_files(tmp_path):
    root, plan = runtime_fixture(tmp_path)
    _module.verify(root, plan)
    (root / "payload.dll").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        _module.verify(root, plan)
    (root / "payload.dll").write_bytes(b"reviewed bytes")
    (root / "unreviewed.dll").write_bytes(b"extra")
    with pytest.raises(ValueError, match="unrecorded"):
        _module.verify(root, plan)


def test_reviewed_runtime_requires_pins_and_licences(tmp_path):
    root, plan = runtime_fixture(tmp_path)
    plan.write_text(json.dumps({"packages": {"demo": "2"}}))
    with pytest.raises(ValueError, match="inventory differs"):
        _module.verify(root, plan)
    plan.write_text(json.dumps({"packages": {"demo": "1"}}))
    (root / "LICENSE.txt").unlink()
    with pytest.raises(ValueError, match="Missing licence"):
        _module.verify(root, plan)


def test_reviewed_runtime_rejects_inventory_path_escape(tmp_path):
    root, plan = runtime_fixture(tmp_path)
    (root / "runtime-files.sha256").write_text("0" * 64 + "  ../plan.json")
    with pytest.raises(ValueError, match="Invalid runtime inventory path"):
        _module.verify(root, plan)
