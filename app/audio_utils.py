"""Soundfile/NumPy-only reference audio validation and conversion."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from .config import Settings


class InvalidAudioError(ValueError):
    """Raised when an uploaded reference cannot be used."""


def convert_reference_to_wav(source: Path, destination: Path, settings: Settings) -> tuple[int, float]:
    try:
        info = sf.info(str(source))
    except Exception as exc:
        raise InvalidAudioError("The reference audio could not be decoded.") from exc
    if info.channels <= 0 or info.frames <= 0 or info.samplerate <= 0:
        raise InvalidAudioError("The reference audio has no usable samples.")
    duration = info.frames / info.samplerate
    if duration < settings.min_reference_seconds:
        raise InvalidAudioError(f"Reference audio must be at least {settings.min_reference_seconds:g} seconds.")
    if duration > settings.max_reference_seconds:
        raise InvalidAudioError(f"Reference audio must be no longer than {settings.max_reference_seconds:g} seconds.")
    try:
        samples, sample_rate = sf.read(str(source), dtype="float32", always_2d=True)
    except Exception as exc:
        raise InvalidAudioError("The reference audio could not be read.") from exc
    if samples.size == 0:
        raise InvalidAudioError("The reference audio is empty.")
    mono = samples.mean(axis=1, dtype=np.float32)
    if not np.isfinite(mono).all():
        raise InvalidAudioError("The reference audio contains invalid numeric samples.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(destination), np.clip(mono, -1.0, 1.0), sample_rate, subtype="PCM_16", format="WAV")
    return int(sample_rate), float(len(mono) / sample_rate)


def validate_uploaded_size(path: Path, settings: Settings) -> None:
    size = path.stat().st_size
    if size <= 0:
        raise InvalidAudioError("The reference audio file is empty.")
    maximum = settings.max_reference_file_mb * 1024 * 1024
    if size > maximum:
        raise InvalidAudioError(f"The reference audio must be smaller than {settings.max_reference_file_mb} MB.")
