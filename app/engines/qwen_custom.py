"""Official Qwen predefined speakers; Fast and High use separate weights."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from .base import GenerationResult
from .qwen_clone import QwenCloneEngine, ensure_audio_budget, sampling_parameters


class QwenCustomVoiceEngine(QwenCloneEngine):
    def generate(
        self, *, text_chunks: list[str], language: str, reference_audio_path: Path | None,
        reference_transcript: str, profile_id: str, output_path: Path, silence_ms: int,
        instruction: str = "",
    ) -> GenerationResult:
        if self.model is None:
            raise RuntimeError("Qwen voice model is not loaded")
        speaker = profile_id.removeprefix("qwen:")
        pieces = []
        sample_rate = None
        for index, chunk in enumerate(text_chunks):
            generated = self.model.generate_custom_voice(
                text=chunk, speaker=speaker, language=language, instruct=instruction or None,
                non_streaming_mode=True, max_new_tokens=self.max_new_tokens,
                **sampling_parameters(self.temperature),
            )
            waveform, returned_rate = self._waveform_and_rate(generated)
            ensure_audio_budget(waveform, returned_rate, self.max_new_tokens)
            if sample_rate is not None and returned_rate != sample_rate:
                raise RuntimeError("Qwen returned mismatched sample rates")
            sample_rate = returned_rate
            pieces.append(waveform)
            if index < len(text_chunks) - 1:
                pieces.append(np.zeros(int(sample_rate * silence_ms / 1000), dtype=np.float32))
        if not pieces or sample_rate is None:
            raise RuntimeError("Qwen returned no audio")
        audio = np.concatenate(pieces)
        sf.write(str(output_path), audio, sample_rate, subtype="PCM_16", format="WAV")
        return GenerationResult(sample_rate, len(audio) / sample_rate, len(text_chunks))
