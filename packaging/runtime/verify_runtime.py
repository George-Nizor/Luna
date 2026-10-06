"""Check a freshly installed runtime before Luna switches to it.

    python -I verify_runtime.py <runtime-lock.json> <backend root>

Prints one JSON object. Exit code 0 means the environment holds exactly the locked distributions
and every engine's modules import; whether PyTorch can reach an NVIDIA GPU is reported, not
required, so a machine without one still gets a working (if unable to generate) Luna and a clear
message instead of a crash.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import json
import re
import sys
import time
from pathlib import Path

MODULES = [
    "fastapi", "uvicorn", "multipart", "soundfile", "numpy", "psutil", "huggingface_hub",
    "torch", "torchaudio", "transformers", "accelerate", "librosa", "qwen_tts",
    "TTS.tts.models.xtts", "rvc_python.infer",
]


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def main() -> int:
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    report: dict = {"python": sys.version.split()[0], "problems": []}
    if report["python"] != plan["python"]:
        report["problems"].append(f"Python {report['python']} is not the locked {plan['python']}")
    installed = {normalized(d.metadata["Name"]): d.version for d in importlib.metadata.distributions()}
    for package in plan["packages"]:
        if installed.get(package["name"]) != package["version"]:
            report["problems"].append(f"{package['name']} {package['version']} is missing (found {installed.get(package['name'])})")
    extra = sorted(set(installed) - {p["name"] for p in plan["packages"]})
    if extra:
        report["problems"].append("unlocked distributions installed: " + ", ".join(extra))
    started = time.monotonic()
    # RVC imports the way Luna's E-Girl adapter does: after its Fairseq/Hydra compatibility shim.
    sys.path.insert(0, sys.argv[2])
    try:
        from app.engines.rvc_egirl import _patch_rvc_runtime_compat

        _patch_rvc_runtime_compat()
    except Exception as exc:  # noqa: BLE001
        report["problems"].append(f"Luna's RVC compatibility shim failed: {exc}"[:400])
    for module in MODULES:
        try:
            importlib.import_module(module)
        except Exception as exc:  # noqa: BLE001 - every failure is reported to the setup screen
            report["problems"].append(f"import {module} failed: {exc.__class__.__name__}: {exc}"[:400])
    report["importSeconds"] = round(time.monotonic() - started, 1)
    try:
        import torch

        report["torch"] = torch.__version__
        report["cudaBuild"] = torch.version.cuda
        report["cuda"] = bool(torch.cuda.is_available())
        if report["cuda"]:
            report["device"] = torch.cuda.get_device_name(0)
            report["deviceMemory"] = torch.cuda.get_device_properties(0).total_memory
    except Exception as exc:  # noqa: BLE001
        report["cuda"] = False
        report["cudaError"] = str(exc)[:400]
    print(json.dumps(report))
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
