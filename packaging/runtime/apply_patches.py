"""Luna's five reviewed source patches, applied to a freshly installed runtime environment.

Run by electron/runtime-setup.cjs with the new environment's own interpreter, after uv has installed
the locked wheels and before the environment is marked ready:

    python -I apply_patches.py <site-packages>

Each file must hash to the pristine upstream file of its pinned wheel before it is changed, and to
the reviewed result afterwards; anything else stops the setup. Running it again on a patched file is
a no-op. These are the changes the 0.4.1 runtime carried (its publication audit lists them):

- fairseq 0.12.2 and hydra-core 1.0.7 declare dataclass fields with instance defaults, which
  Python 3.11+ rejects. Each becomes field(default_factory=...).
- rvc-python 0.1.5 imports Praat (parselmouth) and PyAV at module level. Luna uses RMVPE pitch and
  hands RVC a WAV, so Praat is imported only by the "pm" pitch method and WAV input is read with
  SoundFile; neither optional package is installed.
- coqui-tts 0.27.5 refuses to import without torchcodec on PyTorch 2.9+. Luna's XTTS adapter
  supplies SoundFile audio IO, so the guard is removed.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


def _fields(code: str, names: list[str]) -> str:
    for name in names:
        pattern = re.compile(rf"^(\s+\w+: {name} = ){name}\(\)$", re.MULTILINE)
        code, count = pattern.subn(rf"\1field(default_factory={name})", code)
        if count != 1:
            raise ValueError(f"expected one {name}() default")
    return code


def fairseq_configs(code: str) -> str:
    return _fields(code, ["CommonConfig", "CommonEvalConfig", "DistributedTrainingConfig", "DatasetConfig",
                          "OptimizationConfig", "CheckpointConfig", "FairseqBMUFConfig", "GenerationConfig",
                          "EvalLMConfig", "InteractiveConfig", "EMAConfig"])


def hydra_conf(code: str) -> str:
    return _fields(code, ["OverrideDirname", "JobConfig", "RunDir", "SweepDir", "HelpConf", "HydraHelpConf",
                          "OverridesConf", "JobConf", "RuntimeConf"])


def rvc_pipeline(code: str) -> str:
    if "import parselmouth\n" not in code or 'if f0_method == "pm":' not in code:
        raise ValueError("the optional-import patch no longer matches")
    code = code.replace("import parselmouth\n", "", 1)
    return code.replace('if f0_method == "pm":', 'if f0_method == "pm":\n            import parselmouth  # Optional upstream Praat mode; not used by Luna.')


def rvc_audio(code: str) -> str:
    if "import av\n" not in code or "def load_audio(file, sr):" not in code:
        raise ValueError("the audio patch no longer matches")
    code = code.replace("import av\n", "import soundfile as sf\n", 1)
    code = code.replace("def wav2(i, o, format):", "def wav2(i, o, format):\n    import av  # Optional upstream export, not used by Luna.")
    code = code.replace("def audio2(i, o, format, sr):", "def audio2(i, o, format, sr):\n    import av  # Optional upstream export, not used by Luna.")
    return code[:code.index("def load_audio(file, sr):")] + """def load_audio(file, sr):
    # Luna supplies a generated PCM WAV. No external decoder is needed.
    audio, source_rate = sf.read(file, dtype="float32", always_2d=True)
    audio = np.mean(audio, axis=1)
    if source_rate != sr:
        audio = librosa.resample(audio, orig_sr=source_rate, target_sr=sr)
    return np.asarray(audio, dtype=np.float32)
"""


def coqui_init(code: str) -> str:
    guard = 'if is_torch_greater_or_equal("2.9"):\n    if not is_torchcodec_available():\n        raise ImportError(TORCHCODEC_IMPORT_ERROR)'
    if guard not in code:
        raise ValueError("the SoundFile patch no longer matches")
    return code.replace(guard, "# Luna supplies SoundFile audio IO in its XTTS adapter; torchcodec is optional here.")


# file, transform, line ending, SHA-256 of the pinned upstream file, SHA-256 of the reviewed result.
# The results are byte-identical to the files the reviewed 0.4.1 runtime shipped, line endings included.
PATCHES = [
    ("fairseq/dataclass/configs.py", fairseq_configs, "\n",
     "3bad79013565db4477ed859ce9778397588c9efaeb7eaaecee1911cc7409dde2",
     "9215fade9365eb5b86d669bd2dce0be950a00fd5d2870c6da1e7f38ab253e788"),
    ("hydra/conf/__init__.py", hydra_conf, "\n",
     "ebb83d718384db8e54bdae9b300e3c3fba6ee0b9462922939c5b7290b7af8907",
     "d78d053b135dd9d96cf7c9b6a13eeadfab034cc6acb492f8cff8b5fa34127b2e"),
    ("rvc_python/modules/vc/pipeline.py", rvc_pipeline, "\r\n",
     "9b3e1ad3b9aff7177a63aca8d36c90388c62a938dfd38d333b6e40ed7a140809",
     "5bafdb9b32195481fad354b4df0b943aa5ed3e0b939cc5478facfee16dbbcc4a"),
    ("rvc_python/lib/audio.py", rvc_audio, "\n",
     "aae47b7437057659940731239f9f2d291c12cc64b6cb03995f477aee45cefc9e",
     "ef8a85c7d2af2bd38580f89a8d8b93ee10862272407f04a89641ae5da84e1f35"),
    ("TTS/__init__.py", coqui_init, "\n",
     "746fe8084b3a6b0c50294d08172675abd98a09f60cb2bf3d4904d591f5ae7090",
     "a123a1b2786365094913333c0254460014c69f7e1829bc0341e77ff75cc3edf3"),
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patched_bytes(original: bytes, transform, newline: str) -> bytes:
    text = original.decode("utf-8").replace("\r\n", "\n")
    return transform(text).replace("\n", newline).encode("utf-8")


def apply(site_packages: Path) -> list[dict]:
    results = []
    for relative, transform, newline, upstream, reviewed in PATCHES:
        path = site_packages / relative
        current = path.read_bytes()
        if digest(current) == reviewed:
            results.append({"file": relative, "sha256": reviewed, "changed": False})
            continue
        if digest(current) != upstream:
            raise ValueError(f"{relative} is not the pinned upstream file")
        result = patched_bytes(current, transform, newline)
        if digest(result) != reviewed:
            raise ValueError(f"{relative} did not patch to the reviewed result")
        path.write_bytes(result)
        results.append({"file": relative, "sha256": digest(result), "changed": True})
    return results


if __name__ == "__main__":
    print(json.dumps(apply(Path(sys.argv[1])), indent=2))
