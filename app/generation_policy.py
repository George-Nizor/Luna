"""Shared request limits and engine capabilities, without loading ML libraries."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import Settings

# Leave headroom below XTTS's language-specific tokenizer character limits.
XTTS_CHUNK_LIMITS = {
    "Auto": 200, "English": 200, "Chinese": 70, "Japanese": 60, "Korean": 75,
    "German": 200, "French": 200, "Russian": 145, "Portuguese": 200,
    "Spanish": 200, "Italian": 200,
}

QWEN_SPEAKERS = {
    "ryan": ("Ryan", "English", "Expressive male narrator"),
    "aiden": ("Aiden", "English", "Clear American male voice"),
    "vivian": ("Vivian", "Chinese", "Bright female voice"),
    "serena": ("Serena", "Chinese", "Warm, gentle female voice"),
    "uncle_fu": ("Uncle Fu", "Chinese", "Mellow, seasoned male voice"),
    "dylan": ("Dylan", "Chinese", "Young male voice, Beijing accent"),
    "eric": ("Eric", "Chinese", "Lively male voice, Sichuan accent"),
    "ono_anna": ("Ono Anna", "Japanese", "Playful female voice"),
    "sohee": ("Sohee", "Korean", "Warm female voice"),
}


@dataclass(frozen=True)
class GenerationPolicy:
    max_text_characters: int
    chunk_target_characters: int
    chunk_max_characters: int
    quality_choices: tuple[str, ...]
    supports_instruction: bool
    supports_sampling: bool

    def as_dict(self) -> dict:
        return asdict(self)


def generation_policy(settings: Settings, voice: str, quality: str, language: str) -> GenerationPolicy:
    is_xtts = voice == "david"
    # Reserve half the 12.5 Hz audio token budget and assume slow speech
    # (two written characters/sec) when bounding Qwen chunks.
    qwen_budget = max(1, int(settings.max_new_tokens / 12.5))
    maximum = min(
        settings.text_chunk_max_characters,
        XTTS_CHUNK_LIMITS.get(language, 150) if is_xtts else min(140 if quality == "fast" else 100, qwen_budget),
    )
    return GenerationPolicy(
        max_text_characters=settings.max_text_characters,
        chunk_target_characters=min(settings.text_chunk_target_characters, maximum),
        chunk_max_characters=maximum,
        quality_choices=("best",) if is_xtts else ("fast", "best"),
        supports_instruction=voice.startswith("qwen:") and quality == "best",
        supports_sampling=not is_xtts,
    )
