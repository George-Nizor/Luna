"""RVC V2 adapter layered over a selectable Qwen source waveform."""

from __future__ import annotations

import copy
import dataclasses
import gc
import os
import site
import sys
import tempfile
from dataclasses import _MISSING_TYPE
from pathlib import Path

import numpy as np
import soundfile as sf

from .base import GenerationResult
from .qwen_clone import QwenCloneEngine


def _patch_rvc_runtime_compat() -> None:
    """Keep the legacy fairseq runtime usable on the bundled Python version."""

    # The approved local HuBERT checkpoint is a trusted legacy Fairseq pickle.
    # PyTorch 2.6+ defaults torch.load to weights_only=True, which rejects the
    # Fairseq Dictionary object used by this checkpoint.
    os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")

    original_get_field = getattr(dataclasses._get_field, "_rvc_original", None)
    if original_get_field is None:
        original_get_field = dataclasses._get_field

        def compatible_get_field(cls, name, typ, kw_only):
            try:
                return original_get_field(cls, name, typ, kw_only)
            except ValueError as exc:
                if "mutable default" not in str(exc):
                    raise
                default = getattr(cls, name)
                setattr(cls, name, dataclasses.field(default_factory=lambda value=default: copy.copy(value)))
                return original_get_field(cls, name, typ, kw_only)

        compatible_get_field._rvc_original = original_get_field
        dataclasses._get_field = compatible_get_field

    from hydra.core.config_store import ConfigStore

    original_store = getattr(ConfigStore.store, "_rvc_original", None)
    if original_store is None:
        original_store = ConfigStore.store

        def compatible_store(self, name, node, group=None, package="_group_", provider=None):
            if isinstance(node, _MISSING_TYPE):
                return None
            return original_store(self, name, node, group, package, provider)

        compatible_store._rvc_original = original_store
        ConfigStore.store = compatible_store


class EgirlRvcEngine:
    def __init__(
        self,
        *,
        rvc_directory: Path,
        qwen_model_id: str,
        qwen_model_source: Path | None,
        allow_cpu: bool,
        max_new_tokens: int,
        offline_mode: bool = False,
    ):
        self.rvc_directory = rvc_directory
        self.qwen_model_id = qwen_model_id
        self.qwen_model_source = qwen_model_source
        self.allow_cpu = allow_cpu
        self.max_new_tokens = max_new_tokens
        self.offline_mode = offline_mode
        self.source_engine: QwenCloneEngine | None = None
        self.rvc = None
        self.cuda_active = False
        self.reference_path: Path | None = None

    def load(self) -> None:
        checkpoint = next(iter(self.rvc_directory.glob("**/*.pth")), None)
        index_file = next(iter(self.rvc_directory.glob("**/*.index")), None)
        if checkpoint is None:
            raise RuntimeError("The extracted E-Girl RVC model does not contain a .pth checkpoint.")
        base_candidates = [Path(root) / "rvc_python" / "base_model" for root in site.getsitepackages()]
        base_candidates.append(Path(sys.prefix) / "Lib" / "site-packages" / "rvc_python" / "base_model")
        base_directory = next((candidate for candidate in base_candidates if candidate.parent.is_dir()), base_candidates[0])
        missing_base_assets = [name for name in ("hubert_base.pt",) if not (base_directory / name).is_file()]
        if missing_base_assets:
            raise RuntimeError(
                "The E-Girl archive contains the checkpoint and index, but is missing local RVC base asset(s): "
                + ", ".join(missing_base_assets)
                + ". The app will not auto-download unregistered model URLs."
            )
        try:
            _patch_rvc_runtime_compat()
            import rvc_python.infer as rvc_module
            import torch
        except Exception as exc:
            detail = str(exc).splitlines()[-1].strip() or exc.__class__.__name__
            if "object_type=None" in detail:
                detail = "Fairseq/Hydra compatibility error"
            raise RuntimeError(
                "E-Girl RVC cannot start because the local rvc-python/Fairseq runtime is unavailable "
                f"({detail}). It also needs a local hubert_base.pt asset; the app will not auto-download "
                "unregistered RVC base models."
            ) from exc
        # rvc-python otherwise downloads HuBERT/RMVPE from its own URLs in its
        # constructor. The registry contract permits only the fixed model
        # URLs, so prevent that implicit network access.
        rvc_module.download_rvc_models = lambda _directory: None
        RVCInference = rvc_module.RVCInference
        self.cuda_active = bool(torch.cuda.is_available())
        if not self.cuda_active and not self.allow_cpu:
            raise RuntimeError("CUDA is unavailable for the E-Girl RVC model. Set ALLOW_CPU=true for CPU mode.")
        self.rvc = RVCInference(device="cuda:0" if self.cuda_active else "cpu")
        self.rvc.load_model(str(checkpoint), version="v2", index_path=str(index_file) if index_file else "")
        # The model page identifies this checkpoint as RMVPE and its best
        # female-source preview uses pitch 0. rvc-python otherwise defaults to
        # the older Harvest extractor, which materially changes this voice.
        self.rvc.set_params(
            f0method="rmvpe",
            f0up_key=0,
            index_rate=0.6,
            filter_radius=3,
            resample_sr=0,
            # Match the conservative rvc-python/w-okada-style defaults more
            # closely. The previous full RMS replacement and low protection
            # made consonants harsher and less like the published preview.
            rms_mix_rate=0.25,
            protect=0.5,
        )
        self.reference_path = next(iter(self.rvc_directory.glob("**/source_ref.wav")), None)
        if self.reference_path is None:
            self.reference_path = next(iter(self.rvc_directory.glob("**/*.wav")), None)
        if self.reference_path is None:
            raise RuntimeError("E-Girl RVC requires its bundled clean female source reference.")
        self.source_engine = QwenCloneEngine(
            model_id=self.qwen_model_id,
            allow_cpu=self.allow_cpu,
            max_new_tokens=self.max_new_tokens,
            offline_mode=self.offline_mode,
            # The supplied RVC archive has no transcript-bearing reference
            # audio. Use speaker-embedding-only cloning so an invented
            # transcript cannot send Qwen into an unbounded ICL generation.
            x_vector_only_mode=True,
            model_source=self.qwen_model_source,
        )
        self.source_engine.load()

    def generate(
        self,
        *,
        text_chunks: list[str],
        language: str,
        reference_audio_path: Path | None,
        reference_transcript: str,
        profile_id: str,
        output_path: Path,
        silence_ms: int,
    ) -> GenerationResult:
        if self.rvc is None or self.source_engine is None or self.reference_path is None:
            raise RuntimeError("E-Girl RVC model is not loaded")
        with tempfile.TemporaryDirectory(prefix="egirl-", dir=output_path.parent) as temporary:
            source_path = Path(temporary) / "qwen-source.wav"
            self.source_engine.generate(
                text_chunks=text_chunks,
                language=language,
                reference_audio_path=self.reference_path,
                reference_transcript=reference_transcript or "This is a local voice sample.",
                profile_id=profile_id,
                output_path=source_path,
                silence_ms=silence_ms,
            )
            try:
                self.rvc.infer_file(str(source_path), str(output_path))
            except TypeError:
                self.rvc.infer_file(str(source_path), output_path=str(output_path))
        audio, sample_rate = sf.read(str(output_path), dtype="float32")
        array = np.asarray(audio, dtype=np.float32).reshape(-1)
        if array.size == 0 or not np.isfinite(array).all():
            raise RuntimeError("RVC returned an invalid waveform")
        return GenerationResult(int(sample_rate), len(array) / sample_rate, len(text_chunks))

    def close(self) -> None:
        self.rvc = None
        if self.source_engine is not None:
            self.source_engine.close()
        self.source_engine = None
        self.reference_path = None
        gc.collect()
