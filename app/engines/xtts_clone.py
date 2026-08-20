"""Lazy XTTS adapter for the fixed David Attenborough fine-tune."""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .base import GenerationResult


class XttsAttenboroughEngine:
    def __init__(self, model_directory: Path, *, allow_cpu: bool, silence_ms: int):
        self.model_directory = model_directory
        self.allow_cpu = allow_cpu
        self.silence_ms = silence_ms
        self.model = None
        self.conditioning_latents: tuple[Any, Any] | None = None
        self.output_sample_rate = 24000
        self.cuda_active = False
        self.reference_path: Path | None = None
        self.inference_settings: dict[str, float | int] = {}

    def load(self) -> None:
        config_path = next(iter(self.model_directory.glob("**/config*.json")), None)
        checkpoint = next(iter(self.model_directory.glob("**/*.pth")), None)
        # The supplied fine-tune uses Coqui's historical ``vocab.json_`` name
        # (note the trailing underscore), so do not require a ``.json`` suffix.
        vocabulary = next(iter(self.model_directory.glob("**/vocab*")), None)
        reference = next(iter(self.model_directory.glob("**/ref.wav")), None)
        if config_path is None or checkpoint is None or vocabulary is None or reference is None:
            raise RuntimeError("The extracted David XTTS model files are incomplete.")
        try:
            import torch
            import torchaudio
            from TTS.config import load_config
            from TTS.tts.models import xtts as xtts_module
            from TTS.tts.models.xtts import Xtts
        except ImportError as exc:
            raise RuntimeError("XTTS requires the optional Coqui TTS runtime (coqui-tts) to be installed.") from exc
        self.cuda_active = bool(torch.cuda.is_available())
        if not self.cuda_active and not self.allow_cpu:
            raise RuntimeError("CUDA is unavailable for the XTTS model. Set ALLOW_CPU=true for CPU mode.")

        # Coqui 0.27's high-level TTS wrapper still routes local XTTS
        # checkpoints through the old ``checkpoint_dir`` argument. Load the
        # model class directly so the supplied fine-tune works with current
        # Coqui releases and never reaches the model downloader.
        def local_load_audio(path: str | Path, sample_rate: int):
            audio, source_rate = sf.read(str(path), dtype="float32", always_2d=True)
            waveform = torch.from_numpy(np.asarray(audio, dtype=np.float32).T.copy())
            if waveform.shape[0] != 1:
                waveform = waveform.mean(dim=0, keepdim=True)
            if source_rate != sample_rate:
                waveform = torchaudio.functional.resample(waveform, source_rate, sample_rate)
            waveform.clamp_(-1, 1)
            return waveform

        xtts_module.load_audio = local_load_audio
        config = load_config(str(config_path))
        self.model = Xtts.init_from_config(config)
        self.model.load_checkpoint(
            config,
            checkpoint_path=str(checkpoint),
            vocab_path=str(vocabulary),
            eval=True,
        )
        if self.cuda_active:
            self.model.cuda()
        self.output_sample_rate = int(config.audio.output_sample_rate)
        self.reference_path = reference
        self.conditioning_latents = self.model.get_conditioning_latents(
            str(reference),
            max_ref_length=int(config.max_ref_len),
            gpt_cond_len=int(config.gpt_cond_len),
            gpt_cond_chunk_len=int(config.gpt_cond_chunk_len),
            sound_norm_refs=bool(config.sound_norm_refs),
        )
        self.inference_settings = {
            "temperature": float(config.temperature),
            "length_penalty": float(config.length_penalty),
            # This fine-tune records the older training-time value 5. Current
            # XTTS v2 can fail to emit EOS with that value and decode to its
            # multi-minute hard limit. Retain the current runtime's safe floor
            # while honoring every other repository inference preset.
            "repetition_penalty": max(10.0, float(config.repetition_penalty)),
            "top_k": int(config.top_k),
            "top_p": float(config.top_p),
        }

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
        if self.model is None or self.reference_path is None or self.conditioning_latents is None:
            raise RuntimeError("XTTS model is not loaded")
        pieces: list[np.ndarray] = []
        sample_rate: int | None = None
        for index, text in enumerate(text_chunks):
            language_code = {
                "Auto": "en",
                "English": "en",
                "Chinese": "zh-cn",
                "Japanese": "ja",
                "Korean": "ko",
                "German": "de",
                "French": "fr",
                "Russian": "ru",
                "Portuguese": "pt",
                "Spanish": "es",
                "Italian": "it",
            }.get(language, language.lower())
            conditioning, speaker_embedding = self.conditioning_latents
            result = self.model.inference(
                text,
                language_code,
                conditioning,
                speaker_embedding,
                enable_text_splitting=False,
                **self.inference_settings,
            )
            array = np.asarray(result["wav"], dtype=np.float32).reshape(-1)
            if array.size == 0 or not np.isfinite(array).all():
                raise RuntimeError("XTTS returned an invalid waveform")
            if sample_rate is None:
                sample_rate = self.output_sample_rate
            elif sample_rate != self.output_sample_rate:
                raise RuntimeError("XTTS returned mismatched sample rates")
            pieces.append(np.clip(array, -1.0, 1.0))
            if index < len(text_chunks) - 1:
                pieces.append(np.zeros(int(sample_rate * silence_ms / 1000), dtype=np.float32))
        if sample_rate is None or not pieces:
            raise RuntimeError("XTTS returned no audio")
        audio = np.concatenate(pieces)
        sf.write(str(output_path), audio, sample_rate, subtype="PCM_16", format="WAV")
        return GenerationResult(sample_rate, len(audio) / sample_rate, len(text_chunks))

    def close(self) -> None:
        self.model = None
        self.conditioning_latents = None
        self.reference_path = None
        self.inference_settings = {}
        gc.collect()
