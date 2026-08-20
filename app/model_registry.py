"""Fixed, browser-inaccessible model registry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FixedModel:
    key: str
    label: str
    engine: str
    page_url: str
    archive_url: str
    download_name: str
    extract_directory: str
    sha256: str | None = None


DAVID_ATTENBOROUGH = FixedModel(
    key="david",
    label="David Attenborough — XTTS",
    engine="xtts",
    page_url="https://huggingface.co/drewThomasson/xtts_David_Attenborough_fine_tune",
    archive_url="https://huggingface.co/drewThomasson/xtts_David_Attenborough_fine_tune/resolve/main/Finished_model_files.zip?download=true",
    download_name="david_attenborough_xtts.zip",
    extract_directory="xtts/david_attenborough",
    sha256="1cee904839ee964d52accb6ac4639c639fda3c5db10c386742e877f6259baabe",
)

EGIRL_RVC = FixedModel(
    key="egirl",
    label="E-Girl — RVC over selectable Qwen source",
    engine="rvc",
    page_url="https://voice-models.com/model/1uZvOaYhqJv",
    archive_url="https://huggingface.co/pendmg/Models/resolve/main/egirl.zip?download=true",
    download_name="egirl_rvc.zip",
    extract_directory="rvc/egirl",
)

QWEN_FAST = FixedModel(
    key="qwen-fast",
    label="Qwen Fast",
    engine="qwen",
    page_url="https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    archive_url="",
    download_name="",
    extract_directory="",
)

QWEN_BEST = FixedModel(
    key="qwen-best",
    label="Qwen Best",
    engine="qwen",
    page_url="https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    archive_url="",
    download_name="",
    extract_directory="",
)

MODEL_REGISTRY = {item.key: item for item in (DAVID_ATTENBOROUGH, EGIRL_RVC, QWEN_FAST, QWEN_BEST)}
