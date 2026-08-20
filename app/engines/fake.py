"""Deterministic sine-wave engine used by tests and local smoke checks."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import soundfile as sf

from .base import GenerationResult


class FakeVoiceEngine:
    def __init__(self, *, delay_seconds: float = 0.0, fail: bool = False):
        self.delay_seconds = delay_seconds
        self.fail = fail
        self.loaded = False
        self.voice_prompt_cache: dict[str, object] = {}

    def load(self) -> None:
        if self.fail:
            raise RuntimeError("deliberate fake model load failure")
        self.loaded = True

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
        if not self.loaded:
            raise RuntimeError("fake engine is not loaded")
        if self.fail:
            raise RuntimeError("deliberate fake generation failure")
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        self.voice_prompt_cache.setdefault(profile_id, object())
        sample_rate = 22050
        pieces: list[np.ndarray] = []
        for index, chunk in enumerate(text_chunks):
            duration = max(0.18, min(2.0, 0.012 * len(chunk)))
            timeline = np.arange(int(sample_rate * duration), dtype=np.float32) / sample_rate
            frequency = 190.0 + index * 15.0
            pieces.append((0.16 * np.sin(2 * np.pi * frequency * timeline)).astype(np.float32))
            if index < len(text_chunks) - 1:
                pieces.append(np.zeros(int(sample_rate * silence_ms / 1000), dtype=np.float32))
        audio = np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), audio, sample_rate, subtype="PCM_16", format="WAV")
        return GenerationResult(sample_rate, len(audio) / sample_rate, len(text_chunks))

    def close(self) -> None:
        self.voice_prompt_cache.clear()
        self.loaded = False
