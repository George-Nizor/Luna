"""Assemble a public Python runtime from reviewed distribution records only."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import re
import shutil
from pathlib import Path


def normalized(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def permitted(relative: Path) -> bool:
    value = relative.as_posix().lower()
    return not (
        any(part in {"__pycache__", "tests", "test"} for part in relative.parts) or relative.suffix.lower() in {".pyc", ".pyo"}
        or value.endswith("/direct_url.json") or value.startswith("rvc_python/base_model/")
        or value.startswith("rvc_python/weights/")
    )


def patch_rvc_audio(code: str) -> str:
    """Retain upstream optional exports while using the app's WAV decoder."""
    if "import av\n" not in code or "def load_audio(file, sr):" not in code:
        raise ValueError("The reviewed RVC audio patch no longer matches")
    code = code.replace("import av\n", "import soundfile as sf\n", 1)
    code = code.replace("def wav2(i, o, format):", "def wav2(i, o, format):\n    import av  # Optional upstream export, not used by Luna.")
    code = code.replace("def audio2(i, o, format, sr):", "def audio2(i, o, format, sr):\n    import av  # Optional upstream export, not used by Luna.")
    code = code[:code.index("def load_audio(file, sr):")] + """def load_audio(file, sr):
    # Luna supplies a generated PCM WAV. No external decoder is needed.
    audio, source_rate = sf.read(file, dtype="float32", always_2d=True)
    audio = np.mean(audio, axis=1)
    if source_rate != sr:
        audio = librosa.resample(audio, orig_sr=source_rate, target_sr=sr)
    return np.asarray(audio, dtype=np.float32)
"""
    return code


def prepare(source: Path, destination: Path, plan: Path, overlays: Path | None = None, supplemental_notices: Path | None = None) -> dict:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if destination.exists() or destination == source or source in destination.parents:
        raise ValueError("Choose a new destination outside the source runtime")
    config = json.loads(plan.read_text(encoding="utf-8"))
    site = source / "Lib/site-packages"
    roots = ([overlays.resolve(strict=True)] if overlays else []) + [site]
    candidates = list(importlib.metadata.distributions(path=[str(root) for root in roots]))
    chosen = []
    for name, version in config["packages"].items():
        match = next((d for d in candidates if normalized(d.metadata["Name"]) == normalized(name) and d.version == version), None)
        if match is None:
            raise ValueError(f"Reviewed distribution missing: {name}=={version}")
        chosen.append(match)
    destination.mkdir(parents=True)
    # CPython's own standard library and DLLs; never copy the old site-packages wholesale.
    for item in source.iterdir():
        if item.name.lower() in {"scripts", "include", "libs"}:
            continue
        if item.is_symlink():
            raise ValueError("Runtime roots cannot be symlinks")
        output = destination / item.name
        if item.is_dir():
            shutil.copytree(item, output, ignore=shutil.ignore_patterns("site-packages", "__pycache__", "*.pyc", "*.pyo"))
        else:
            shutil.copy2(item, output)
    target_site = destination / "Lib/site-packages"
    notices = destination / "THIRD_PARTY_LICENSES"
    notices.mkdir()
    packages = []
    deviations = []
    for distribution in chosen:
        name = distribution.metadata["Name"]
        version = distribution.version
        root = Path(distribution.locate_file("")).resolve()
        files = []
        texts = []
        for record in distribution.files or []:
            item = Path(distribution.locate_file(record)).resolve()
            if root not in item.parents:
                # Console launchers are deliberately not installed in the app runtime.
                if "Scripts" in Path(str(record)).parts or "bin" in Path(str(record)).parts:
                    continue
                raise ValueError(f"Distribution path escapes site-packages: {name}: {record}")
            relative = item.relative_to(root)
            if not permitted(relative):
                continue
            if not item.is_file():
                raise ValueError(f"Distribution file is missing: {name}: {relative}")
            if Path(distribution.locate_file(record)).is_symlink():
                raise ValueError(f"Distribution file is a symlink: {name}: {relative}")
            output = target_site / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists() and sha256(output) != sha256(item):
                raise ValueError(f"Distributions disagree about {relative}")
            shutil.copy2(item, output)
            digest = sha256(output)
            if record.hash and record.hash.mode == "sha256":
                expected = base64.urlsafe_b64encode(bytes.fromhex(digest)).decode().rstrip("=")
                if expected != record.hash.value:
                    if config.get("allowedModifiedFiles", {}).get(relative.as_posix()) != digest:
                        raise ValueError(f"Unreviewed modified runtime file: {name}: {relative}")
                    deviations.append({"package": name, "file": relative.as_posix(), "sha256": digest})
            files.append(relative.as_posix())
            if any(token in relative.name.lower() for token in ("license", "copying", "notice")):
                try:
                    texts.append((relative.as_posix(), item.read_text(encoding="utf-8")))
                except UnicodeError:
                    pass
        if texts:
            (notices / f"{normalized(name)}.txt").write_text("\n\n".join(f"=== {p} ===\n{text}" for p, text in texts), encoding="utf-8")
        packages.append({"name": name, "version": version,
            "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or "See package notices",
            "projectUrls": distribution.metadata.get_all("Project-URL") or [distribution.metadata.get("Home-page")],
            "fileCount": len(files), "noticeFile": f"THIRD_PARTY_LICENSES/{normalized(name)}.txt" if texts else None})
    if supplemental_notices:
        for item in supplemental_notices.iterdir():
            if item.is_file() and not item.is_symlink():
                shutil.copy2(item, notices / item.name)
        for package in packages:
            name = normalized(package["name"])
            if (notices / f"{name}.txt").is_file():
                package["noticeFile"] = f"THIRD_PARTY_LICENSES/{name}.txt"
    # Praat is an optional upstream pitch extractor. Luna uses RMVPE, so defer its import.
    pipeline = target_site / "rvc_python/modules/vc/pipeline.py"
    code = pipeline.read_text(encoding="utf-8")
    if "import parselmouth\n" not in code or 'if f0_method == "pm":' not in code:
        raise ValueError("The reviewed RVC optional-import patch no longer matches")
    code = code.replace("import parselmouth\n", "", 1)
    code = code.replace('if f0_method == "pm":', 'if f0_method == "pm":\n            import parselmouth  # Optional upstream Praat mode; not used by Luna.')
    pipeline.write_text(code, encoding="utf-8")
    audio = target_site / "rvc_python/lib/audio.py"
    audio_code = patch_rvc_audio(audio.read_text(encoding="utf-8"))
    audio.write_text(audio_code, encoding="utf-8")
    coqui = target_site / "TTS/__init__.py"
    coqui_code = coqui.read_text(encoding="utf-8")
    guard = 'if is_torch_greater_or_equal("2.9"):\n    if not is_torchcodec_available():\n        raise ImportError(TORCHCODEC_IMPORT_ERROR)'
    if guard not in coqui_code:
        raise ValueError("The reviewed Coqui SoundFile patch no longer matches")
    coqui.write_text(coqui_code.replace(guard, "# Luna supplies SoundFile audio IO in its XTTS adapter; torchcodec is optional here."), encoding="utf-8")
    result = {"schemaVersion": 1, "pythonVersion": config["pythonVersion"], "packages": packages,
        "excludedPackages": config["excludedPackages"], "recordDifferences": deviations,
        "sourcePatches": [{"file": "Lib/site-packages/rvc_python/modules/vc/pipeline.py", "change": "Import optional Praat only when its pm pitch method is requested.", "sha256": sha256(pipeline)}, {"file": "Lib/site-packages/rvc_python/lib/audio.py", "change": "Read Luna WAV inputs through SoundFile; defer optional PyAV exports.", "sha256": sha256(audio)}, {"file": "Lib/site-packages/TTS/__init__.py", "change": "Permit XTTS with Luna SoundFile audio IO without optional torchcodec.", "sha256": sha256(coqui)}]}
    (destination / "runtime-manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with (destination / "runtime-files.sha256").open("w", encoding="utf-8") as handle:
        for item in sorted(destination.rglob("*")):
            if item.is_file() and item.name != "runtime-files.sha256":
                handle.write(f"{sha256(item)}  {item.relative_to(destination).as_posix()}\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--plan", type=Path, default=Path(__file__).resolve().parents[1] / "packaging/runtime-packages.json")
    parser.add_argument("--overlays", type=Path)
    parser.add_argument("--supplemental-notices", type=Path)
    options = parser.parse_args()
    result = prepare(options.source, options.destination, options.plan, options.overlays, options.supplemental_notices)
    print(json.dumps({"packages": len(result["packages"]), "recordDifferences": len(result["recordDifferences"]), "missingNotices": [d["name"] for d in result["packages"] if not d["noticeFile"]]}, indent=2))
