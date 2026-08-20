"""Typed application configuration.

The web process imports this module, but it deliberately does not import any
machine-learning libraries.  The worker receives a serializable settings
dictionary and imports the selected inference engine only in the child.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    return int(value) if value not in (None, "") else default


def _float(value: str | None, default: float) -> float:
    return float(value) if value not in (None, "") else default


@dataclass(slots=True)
class Settings:
    app_name: str = "Luna"
    host: str = "127.0.0.1"
    port: int = 7865
    engine: str = "qwen"
    allow_cpu: bool = False
    qwen_fast_model: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
    qwen_best_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    qwen_fast_path: Path | None = None
    qwen_best_path: Path | None = None
    default_quality: str = "fast"
    worker_idle_seconds: int = 300
    generation_timeout_seconds: int = 900
    app_idle_shutdown_seconds: int = 1200
    browser_heartbeat_seconds: int = 20
    max_text_characters: int = 5000
    text_chunk_target_characters: int = 350
    text_chunk_max_characters: int = 500
    chunk_silence_milliseconds: int = 180
    max_reference_file_mb: int = 25
    min_reference_seconds: float = 1.0
    max_reference_seconds: float = 60.0
    output_history_limit: int = 30
    log_level: str = "INFO"
    data_directory: Path = Path("data")
    output_directory: Path | None = None
    fixed_models_directory: Path | None = None
    runtime_directory: Path = Path("runtime")
    log_directory: Path = Path("logs")
    hf_home: Path = Path("data/model_cache")
    offline_mode: bool = False
    max_new_tokens: int = 2048
    fake_delay_seconds: float = 0.0
    fake_fail: bool = False

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> Settings:
        root = (base_dir or Path.cwd()).resolve()
        values: dict[str, object] = {}
        env_map = {
            "APP_NAME": ("app_name", str, "Luna"),
            "HOST": ("host", str, "127.0.0.1"),
            "PORT": ("port", int, 7865),
            "ENGINE": ("engine", str, "qwen"),
            "ALLOW_CPU": ("allow_cpu", bool, False),
            "QWEN_FAST_MODEL": ("qwen_fast_model", str, "Qwen/Qwen3-TTS-12Hz-0.6B-Base"),
            "QWEN_BEST_MODEL": ("qwen_best_model", str, "Qwen/Qwen3-TTS-12Hz-1.7B-Base"),
            "DEFAULT_QUALITY": ("default_quality", str, "fast"),
            "WORKER_IDLE_SECONDS": ("worker_idle_seconds", int, 300),
            "GENERATION_TIMEOUT_SECONDS": ("generation_timeout_seconds", int, 900),
            "APP_IDLE_SHUTDOWN_SECONDS": ("app_idle_shutdown_seconds", int, 1200),
            "BROWSER_HEARTBEAT_SECONDS": ("browser_heartbeat_seconds", int, 20),
            "MAX_TEXT_CHARACTERS": ("max_text_characters", int, 5000),
            "TEXT_CHUNK_TARGET_CHARACTERS": ("text_chunk_target_characters", int, 350),
            "TEXT_CHUNK_MAX_CHARACTERS": ("text_chunk_max_characters", int, 500),
            "CHUNK_SILENCE_MILLISECONDS": ("chunk_silence_milliseconds", int, 180),
            "MAX_REFERENCE_FILE_MB": ("max_reference_file_mb", int, 25),
            "MIN_REFERENCE_SECONDS": ("min_reference_seconds", float, 1.0),
            "MAX_REFERENCE_SECONDS": ("max_reference_seconds", float, 60.0),
            "OUTPUT_HISTORY_LIMIT": ("output_history_limit", int, 30),
            "LOG_LEVEL": ("log_level", str, "INFO"),
            "OFFLINE_MODE": ("offline_mode", bool, False),
            "MAX_NEW_TOKENS": ("max_new_tokens", int, 2048),
            "FAKE_DELAY_SECONDS": ("fake_delay_seconds", float, 0.0),
            "FAKE_FAIL": ("fake_fail", bool, False),
        }
        for env_name, (field_name, converter, default) in env_map.items():
            raw = os.getenv(env_name)
            if converter is bool:
                values[field_name] = _bool(raw, default)  # type: ignore[arg-type]
            elif converter is int:
                values[field_name] = _int(raw, default)  # type: ignore[arg-type]
            elif converter is float:
                values[field_name] = _float(raw, default)  # type: ignore[arg-type]
            else:
                values[field_name] = raw if raw not in (None, "") else default

        for env_name, field_name, fallback in (
            ("DATA_DIRECTORY", "data_directory", "data"),
            ("OUTPUT_DIRECTORY", "output_directory", "data/outputs"),
            ("MODELS_DIRECTORY", "fixed_models_directory", "data/models"),
            ("QWEN_FAST_PATH", "qwen_fast_path", ""),
            ("QWEN_BEST_PATH", "qwen_best_path", ""),
            ("RUNTIME_DIRECTORY", "runtime_directory", "runtime"),
            ("LOG_DIRECTORY", "log_directory", "logs"),
            ("HF_HOME", "hf_home", "data/model_cache"),
        ):
            raw_path = os.getenv(env_name, fallback)
            if raw_path in (None, ""):
                values[field_name] = None
                continue
            path = Path(raw_path)
            values[field_name] = (path if path.is_absolute() else root / path).resolve()

        settings = cls(**values)
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.host not in ALLOWED_HOSTS:
            raise ValueError("HOST must be 127.0.0.1, localhost, or ::1")
        if self.engine not in {"qwen", "fake"}:
            raise ValueError("ENGINE must be qwen or fake")
        if self.default_quality not in {"fast", "best"}:
            raise ValueError("DEFAULT_QUALITY must be fast or best")
        if self.text_chunk_target_characters <= 0 or self.text_chunk_max_characters <= 0:
            raise ValueError("text chunk sizes must be positive")
        if self.text_chunk_target_characters > self.text_chunk_max_characters:
            raise ValueError("TEXT_CHUNK_TARGET_CHARACTERS cannot exceed TEXT_CHUNK_MAX_CHARACTERS")
        if self.max_new_tokens <= 0:
            raise ValueError("MAX_NEW_TOKENS must be positive")

    @property
    def profiles_directory(self) -> Path:
        return self.data_directory / "profiles"

    @property
    def outputs_directory(self) -> Path:
        return self.output_directory or self.data_directory / "outputs"

    @property
    def temp_directory(self) -> Path:
        return self.data_directory / "temp"

    @property
    def model_cache_directory(self) -> Path:
        return self.data_directory / "model_cache"

    @property
    def model_downloads_directory(self) -> Path:
        return self.model_cache_directory / "downloads"

    @property
    def models_directory(self) -> Path:
        return self.fixed_models_directory or self.data_directory / "models"

    def ensure_directories(self) -> None:
        for path in (
            self.data_directory,
            self.profiles_directory,
            self.outputs_directory,
            self.temp_directory,
            self.model_cache_directory,
            self.model_downloads_directory,
            self.models_directory,
            self.runtime_directory,
            self.log_directory,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def model_id(self, quality: str) -> str:
        if quality == "fast":
            return self.qwen_fast_model
        if quality == "best":
            return self.qwen_best_model
        raise ValueError("quality must be fast or best")

    def worker_dict(self) -> dict[str, object]:
        """Return only spawn-safe values for the worker."""
        values = asdict(self)
        for key, value in list(values.items()):
            if isinstance(value, Path):
                values[key] = str(value)
        return values

    @classmethod
    def from_worker_dict(cls, values: dict[str, object]) -> Settings:
        path_fields = {
            "data_directory",
            "output_directory",
            "fixed_models_directory",
            "qwen_fast_path",
            "qwen_best_path",
            "runtime_directory",
            "log_directory",
            "hf_home",
        }
        converted = dict(values)
        for key in path_fields:
            if key in converted and converted[key] is not None:
                converted[key] = Path(str(converted[key]))
        settings = cls(**converted)  # type: ignore[arg-type]
        settings.validate()
        return settings


def configure_offline_environment(settings: Settings) -> None:
    """Set local runtime paths and offline flags before model modules are imported."""
    os.environ["HF_HOME"] = str(settings.hf_home)
    # Coqui's trainer asks Windows for a shell-folder registry value during
    # construction. Keep its cache inside this project so the fixed XTTS
    # worker is independent of the user's shell setup.
    os.environ["TTS_HOME"] = str(settings.data_directory / "model_cache" / "tts")
    if settings.offline_mode:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
