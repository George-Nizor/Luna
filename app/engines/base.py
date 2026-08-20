"""Small engine interface shared by fake and Qwen implementations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class GenerationResult:
    sample_rate: int
    duration_seconds: float
    chunk_count: int


class VoiceEngine(Protocol):
    def load(self) -> None: ...

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
    ) -> GenerationResult: ...

    def close(self) -> None: ...
