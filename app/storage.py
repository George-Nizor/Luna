"""JSON-backed profile and output storage."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .audio_utils import convert_reference_to_wav, validate_uploaded_size
from .config import Settings
from .schemas import OutputMetadata, ProfileMetadata
from .security import safe_child_path, sanitize_filename, validate_output_id, validate_profile_id


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat()


class Storage:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.ensure_directories()

    def cleanup_temp(self) -> None:
        for child in self.settings.temp_directory.iterdir():
            try:
                if child.is_file() or child.is_symlink():
                    child.unlink()
                elif child.is_dir():
                    shutil.rmtree(child)
            except OSError:
                continue

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("metadata must be an object")
        return data

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        temporary.replace(path)

    def profile_dir(self, profile_id: str, *, must_exist: bool = False) -> Path:
        validate_profile_id(profile_id)
        return safe_child_path(self.settings.profiles_directory, profile_id, must_exist=must_exist)

    def output_dir(self, output_id: str, *, must_exist: bool = False) -> Path:
        validate_output_id(output_id)
        return safe_child_path(self.settings.outputs_directory, output_id, must_exist=must_exist)

    def create_profile(
        self,
        *,
        name: str,
        language: str,
        reference_transcript: str,
        consent_confirmed: bool,
        uploaded_path: Path,
    ) -> ProfileMetadata:
        name = name.strip()
        transcript = reference_transcript.strip()
        if not 1 <= len(name) <= 80:
            raise ValueError("Profile name must be between 1 and 80 characters.")
        if not 1 <= len(transcript) <= 2000:
            raise ValueError("Reference transcript must be between 1 and 2,000 characters.")
        if not consent_confirmed:
            raise ValueError("Consent must be confirmed before saving a profile.")
        validate_uploaded_size(uploaded_path, self.settings)
        profile_id = str(uuid.uuid4())
        directory = self.profile_dir(profile_id)
        directory.mkdir(parents=False, exist_ok=False)
        reference_path = directory / "reference.wav"
        try:
            convert_reference_to_wav(uploaded_path, reference_path, self.settings)
            now = utc_now()
            metadata = ProfileMetadata(
                id=profile_id,
                name=name,
                language=language,
                reference_transcript=transcript,
                consent_confirmed=True,
                created_at=now,
                updated_at=now,
            )
            self._write_json(directory / "profile.json", metadata.model_dump(mode="json"))
            return metadata
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def get_profile(self, profile_id: str) -> ProfileMetadata:
        directory = self.profile_dir(profile_id, must_exist=True)
        try:
            return ProfileMetadata.model_validate(self._read_json(directory / "profile.json"))
        except FileNotFoundError as exc:
            raise FileNotFoundError("profile not found") from exc

    def reference_path(self, profile_id: str) -> Path:
        path = safe_child_path(self.profile_dir(profile_id, must_exist=True), "reference.wav", must_exist=True)
        if path.is_symlink():
            raise ValueError("reference audio symlinks are not allowed")
        return path

    def list_profiles(self) -> list[ProfileMetadata]:
        profiles: list[ProfileMetadata] = []
        for directory in self.settings.profiles_directory.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                profiles.append(self.get_profile(directory.name))
            except (ValueError, FileNotFoundError):
                continue
        return sorted(profiles, key=lambda item: item.updated_at, reverse=True)

    def delete_profile(self, profile_id: str) -> None:
        directory = self.profile_dir(profile_id, must_exist=True)
        if directory.is_symlink():
            raise ValueError("profile symlinks are not allowed")
        shutil.rmtree(directory)

    def begin_output(self, output_id: str) -> tuple[Path, Path]:
        directory = self.output_dir(output_id)
        directory.mkdir(parents=False, exist_ok=False)
        return directory, directory / "output.wav"

    def save_output_metadata(self, metadata: OutputMetadata) -> None:
        directory = self.output_dir(metadata.id, must_exist=True)
        self._write_json(directory / "metadata.json", metadata.model_dump(mode="json"))
        self._enforce_output_retention()

    def _enforce_output_retention(self) -> None:
        entries: list[tuple[datetime, Path]] = []
        for directory in self.settings.outputs_directory.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                metadata = OutputMetadata.model_validate(self._read_json(directory / "metadata.json"))
                entries.append((metadata.created_at, directory))
            except (OSError, ValueError):
                continue
        entries.sort(key=lambda item: item[0], reverse=True)
        for _, directory in entries[self.settings.output_history_limit :]:
            shutil.rmtree(directory, ignore_errors=True)

    def list_outputs(self) -> list[OutputMetadata]:
        outputs: list[OutputMetadata] = []
        for directory in self.settings.outputs_directory.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                outputs.append(OutputMetadata.model_validate(self._read_json(directory / "metadata.json")))
            except (OSError, ValueError):
                continue
        return sorted(outputs, key=lambda item: item.created_at, reverse=True)

    def get_output(self, output_id: str) -> OutputMetadata:
        directory = self.output_dir(output_id, must_exist=True)
        try:
            return OutputMetadata.model_validate(self._read_json(directory / "metadata.json"))
        except FileNotFoundError as exc:
            raise FileNotFoundError("output not found") from exc

    def output_audio_path(self, output_id: str) -> Path:
        return safe_child_path(self.output_dir(output_id, must_exist=True), "output.wav", must_exist=True)

    def delete_output(self, output_id: str) -> None:
        directory = self.output_dir(output_id, must_exist=True)
        if directory.is_symlink():
            raise ValueError("output symlinks are not allowed")
        shutil.rmtree(directory)

    def download_name(self, metadata: OutputMetadata) -> str:
        stamp = metadata.created_at.astimezone(UTC).strftime("%Y%m%d-%H%M%S")
        return f"{sanitize_filename(metadata.profile_name)}_{stamp}.wav"
