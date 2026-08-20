"""Qwen3-TTS voice-cloning adapter.

This module is imported by ``worker_process`` only.  Keeping the imports lazy
ensures the lightweight FastAPI process never creates a CUDA context.
"""

from __future__ import annotations

import gc
from pathlib import Path

import numpy as np
import soundfile as sf

from .base import GenerationResult


class CudaUnavailableError(RuntimeError):
    pass


class QwenCloneEngine:
    def __init__(
        self,
        *,
        model_id: str,
        allow_cpu: bool,
        max_new_tokens: int,
        offline_mode: bool = False,
        x_vector_only_mode: bool = False,
        model_source: Path | None = None,
    ):
        self.model_id = model_id
        self.model_source = model_source
        self.allow_cpu = allow_cpu
        self.max_new_tokens = max_new_tokens
        self.offline_mode = offline_mode
        self.x_vector_only_mode = x_vector_only_mode
        self.model = None
        self.torch = None
        self.cuda_active = False
        self.voice_prompt_cache: dict[str, object] = {}

    def load(self) -> None:
        import torch

        self.torch = torch
        cuda_available = bool(torch.cuda.is_available())
        if not cuda_available and not self.allow_cpu:
            raise CudaUnavailableError("CUDA is unavailable. Install CUDA-enabled PyTorch or set ALLOW_CPU=true.")
        device = "cuda:0" if cuda_available else "cpu"
        self.cuda_active = cuda_available
        dtype = torch.float32
        if cuda_available:
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

        from qwen_tts import Qwen3TTSModel

        if self.model_source is not None:
            if not self.model_source.is_dir():
                raise RuntimeError(f"The bundled Qwen model directory is missing: {self.model_source}")
            model_source = str(self.model_source)
        else:
            from huggingface_hub import snapshot_download

            model_source = snapshot_download(self.model_id, local_files_only=self.offline_mode)

        kwargs: dict[str, object] = {"device_map": device, "dtype": dtype}
        try:
            import flash_attn  # noqa: F401
        except ImportError:
            pass
        else:
            kwargs["attn_implementation"] = "flash_attention_2"
        try:
            self.model = Qwen3TTSModel.from_pretrained(model_source, **kwargs)
        except TypeError:
            kwargs.pop("attn_implementation", None)
            self.model = Qwen3TTSModel.from_pretrained(model_source, **kwargs)

    @staticmethod
    def _waveform_and_rate(result: object, fallback_rate: int = 24000) -> tuple[np.ndarray, int]:
        sample_rate = fallback_rate
        waveform = result
        if isinstance(result, tuple) and len(result) == 2:
            waveform, sample_rate = result
        if isinstance(waveform, (list, tuple)) and waveform:
            waveform = waveform[0]
        array = np.asarray(waveform, dtype=np.float32)
        if array.ndim > 1:
            array = array.reshape(-1)
        if array.ndim != 1 or array.size == 0:
            raise RuntimeError("Qwen returned an empty waveform")
        if not np.isfinite(array).all():
            raise RuntimeError("Qwen returned invalid audio values")
        return np.clip(array, -1.0, 1.0), int(sample_rate)

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
        if self.model is None:
            raise RuntimeError("Qwen model is not loaded")
        if reference_audio_path is None:
            raise RuntimeError("Qwen voice cloning requires a reference audio profile")
        prepared_prompt = self.voice_prompt_cache.get(profile_id)
        if prepared_prompt is None:
            prepared_prompt = self.model.create_voice_clone_prompt(
                ref_audio=str(reference_audio_path),
                ref_text=None if self.x_vector_only_mode else reference_transcript,
                x_vector_only_mode=self.x_vector_only_mode,
            )
            self.voice_prompt_cache[profile_id] = prepared_prompt

        pieces: list[np.ndarray] = []
        sample_rate: int | None = None
        for index, chunk in enumerate(text_chunks):
            generated = self.model.generate_voice_clone(
                text=chunk,
                language=language,
                voice_clone_prompt=prepared_prompt,
                max_new_tokens=self.max_new_tokens,
            )
            waveform, returned_rate = self._waveform_and_rate(generated)
            if sample_rate is None:
                sample_rate = returned_rate
            elif returned_rate != sample_rate:
                raise RuntimeError("Qwen returned mismatched sample rates")
            pieces.append(waveform)
            if index < len(text_chunks) - 1:
                pieces.append(np.zeros(int(sample_rate * silence_ms / 1000), dtype=np.float32))
        if not pieces or sample_rate is None:
            raise RuntimeError("Qwen returned no audio")
        audio = np.concatenate(pieces).astype(np.float32)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), audio, sample_rate, subtype="PCM_16", format="WAV")
        return GenerationResult(sample_rate, len(audio) / sample_rate, len(text_chunks))

    def close(self) -> None:
        self.voice_prompt_cache.clear()
        self.model = None
        if self.torch is not None and self.cuda_active:
            self.torch.cuda.empty_cache()
        self.torch = None
        gc.collect()
