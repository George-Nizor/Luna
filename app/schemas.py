"""API and storage schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

LANGUAGES = [
    "Auto",
    "English",
    "Chinese",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Russian",
    "Portuguese",
    "Spanish",
    "Italian",
]
Quality = Literal["fast", "best"]
VoiceChoice = str


class ProfileMetadata(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=80)
    language: str
    reference_audio: str = "reference.wav"
    reference_transcript: str = Field(min_length=1, max_length=2000)
    consent_confirmed: bool
    created_at: datetime
    updated_at: datetime


class OutputMetadata(BaseModel):
    id: str
    profile_id: str
    profile_name: str
    language: str
    quality: Quality
    model_id: str
    text_character_count: int
    chunk_count: int
    duration_seconds: float
    created_at: datetime
    filename: str = "output.wav"
    # Defaults preserve outputs created by older Luna versions.
    text: str | None = None
    voice: str | None = None
    instruction: str = ""
    seed: int | None = None
    sample_rate: int | None = None
    size_bytes: int = 0
    generation_seconds: float | None = None
    parameters: dict = Field(default_factory=dict)


class GenerationRequest(BaseModel):
    profile_id: str | None = None
    text: str
    language: str = "English"
    voice: VoiceChoice = "david"
    quality: Quality | None = None
    instruction: str = Field(default="", max_length=500)
    seed: int | None = Field(default=None, ge=0, le=4294967295)
    temperature: float | None = Field(default=None, ge=0.2, le=1.2)


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
