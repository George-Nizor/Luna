"""The runtime Luna installs for itself: lock, download plan and reviewed source patches."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "packaging" / "runtime"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


patches = _load("apply_patches", RUNTIME / "apply_patches.py")
PLAN = json.loads((RUNTIME / "runtime-lock.json").read_text(encoding="utf-8"))


def test_download_plan_matches_the_lock() -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "runtime_lock.py"), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_plan_is_wheels_only_with_pinned_hashes_and_sizes() -> None:
    assert PLAN["python"].startswith("3.12.")
    names = {package["name"] for package in PLAN["packages"]}
    for package in PLAN["packages"]:
        assert package["file"].endswith(".whl")
        assert len(package["sha256"]) == 64 and package["size"] > 0
        assert ("url" in package) != ("bundled" in package)
        if "url" in package:
            assert package["url"].startswith(("https://files.pythonhosted.org/", "https://download.pytorch.org/", "https://download-r2.pytorch.org/"))
        else:
            wheel = RUNTIME / package["bundled"]
            assert hashlib.sha256(wheel.read_bytes()).hexdigest() == package["sha256"]
    torch = next(p for p in PLAN["packages"] if p["name"] == "torch")
    assert torch["version"].endswith("+cu128") and torch["file"].endswith("cp312-cp312-win_amd64.whl")
    # Declared upstream, never used by Luna.
    assert not names & {"gradio", "av", "praat-parselmouth", "tensorboard", "cython", "pandas", "aiohttp", "torchcodec", "pip"}
    assert {"qwen-tts", "coqui-tts", "rvc-python", "fairseq", "fastapi", "uvicorn"} <= names
    assert PLAN["downloadBytes"] == sum(p["size"] for p in PLAN["packages"] if "url" in p)


def test_lock_names_the_reviewed_runtime_project() -> None:
    project = tomllib.loads((RUNTIME / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["requires-python"] == "==3.12.*"
    assert project["tool"]["uv"]["package"] is False
    lock = tomllib.loads((RUNTIME / "uv.lock").read_text(encoding="utf-8"))
    assert {p["name"] for p in lock["package"]} - {"luna-runtime"} == {p["name"] for p in PLAN["packages"]}


def test_patches_refuse_files_that_are_not_the_pinned_upstream(tmp_path: Path) -> None:
    for relative, *_ in patches.PATCHES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("not the upstream file\n")
    with pytest.raises(ValueError, match="not the pinned upstream file"):
        patches.apply(tmp_path)


def test_patch_transforms_are_the_reviewed_changes() -> None:
    fairseq = "@dataclass\nclass FairseqConfig(FairseqDataclass):\n" + "".join(
        f"    x{i}: {name} = {name}()\n" for i, name in enumerate(
            ["CommonConfig", "CommonEvalConfig", "DistributedTrainingConfig", "DatasetConfig", "OptimizationConfig",
             "CheckpointConfig", "FairseqBMUFConfig", "GenerationConfig", "EvalLMConfig", "InteractiveConfig", "EMAConfig"]))
    assert "= CommonConfig()" not in patches.fairseq_configs(fairseq)
    assert "field(default_factory=EMAConfig)" in patches.fairseq_configs(fairseq)
    pipeline = 'import parselmouth\nimport pyworld\n        if f0_method == "pm":\n'
    assert patches.rvc_pipeline(pipeline).startswith("import pyworld")
    audio = "import av\ndef wav2(i, o, format):\n    pass\ndef audio2(i, o, format, sr):\n    pass\ndef load_audio(file, sr):\n    old\n"
    patched = patches.rvc_audio(audio)
    assert patched.startswith("import soundfile as sf") and "sf.read(file" in patched and "    old" not in patched
    guard = 'if is_torch_greater_or_equal("2.9"):\n    if not is_torchcodec_available():\n        raise ImportError(TORCHCODEC_IMPORT_ERROR)'
    assert "raise ImportError" not in patches.coqui_init(f"x\n{guard}\n")
    # Every patch is pinned to both ends and the lock hash covers the patch script.
    assert all(len(upstream) == len(reviewed) == 64 for *_, upstream, reviewed in patches.PATCHES)
