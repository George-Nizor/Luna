"""Curated, pinned Qwen packs and explicit, resumable local acquisition."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
from pathlib import Path
from urllib.request import Request, urlopen

from .config import Settings
from .generation_policy import QWEN_SPEAKERS, generation_policy
from .security import safe_child_path

_manifest = json.loads(Path(__file__).with_name("voice_packs.json").read_text(encoding="utf-8-sig"))
PACKS = {pack["id"]: pack for pack in _manifest["packs"]}


def verify_file(path: Path, entry: dict) -> bool:
    if not path.is_file() or path.stat().st_size != entry["size"]:
        return False
    sha256 = entry.get("sha256")
    digest = hashlib.sha256() if sha256 else hashlib.sha1()
    if not sha256:
        digest.update(f"blob {entry['size']}\0".encode())
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == (sha256 or entry["git_blob_sha1"])


def _complete_model(path: Path | None) -> bool:
    return bool(path and (path / "config.json").is_file() and
                (path / "model.safetensors").is_file() and
                (path / "speech_tokenizer" / "model.safetensors").is_file())


def pack_source(settings: Settings, pack_id: str) -> Path | None:
    pack = PACKS[pack_id]
    directory = safe_child_path(settings.model_packs_directory, pack_id)
    try:
        marker = json.loads((directory / "installed.json").read_text(encoding="utf-8"))
        if marker.get("revision") == pack["revision"] and all(
            safe_child_path(directory, entry["path"]).is_file()
            and safe_child_path(directory, entry["path"]).stat().st_size == entry["size"]
            for entry in pack["files"]
        ):
            return directory
    except (OSError, ValueError):
        pass
    if pack["kind"] == "clone":
        candidate = settings.qwen_fast_path if pack["quality"] == "fast" else settings.qwen_best_path
        if _complete_model(candidate):
            return candidate
    # Development caches are local only; generation never initiates downloads.
    cache = settings.hf_home / "hub" / ("models--" + pack["repository"].replace("/", "--"))
    candidate = cache / "snapshots" / pack["revision"]
    if _complete_model(candidate):
        return candidate
    try:
        revision = (cache / "refs" / "main").read_text().strip()
        if re.fullmatch(r"[0-9a-f]{40}", revision):
            candidate = cache / "snapshots" / revision
            if _complete_model(candidate):
                return candidate
    except OSError:
        pass
    return None


class ModelCatalog:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._job: dict | None = None

    def enabled_voices(self) -> list[str]:
        try:
            stored = json.loads((self.settings.data_directory / "voice-selection.json").read_text(encoding="utf-8"))
            return [voice for voice in stored["voices"] if voice in self.voice_ids]
        except (OSError, ValueError, KeyError, TypeError):
            defaults = [f"qwen:{speaker}" for speaker in QWEN_SPEAKERS]
            if list((self.settings.models_directory / "xtts" / "david_attenborough").glob("**/ref.wav")):
                defaults.insert(0, "david")
            if list((self.settings.models_directory / "rvc" / "egirl").glob("**/source_ref.wav")):
                defaults.insert(1, "egirl")
            return defaults

    @property
    def voice_ids(self) -> tuple[str, ...]:
        return ("david", "egirl", *(f"qwen:{speaker}" for speaker in QWEN_SPEAKERS))

    def save_selection(self, voices: list[str]) -> None:
        if not voices or any(voice not in self.voice_ids for voice in voices):
            raise ValueError("Choose at least one voice from the catalog.")
        path = self.settings.data_directory / "voice-selection.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"voices": list(dict.fromkeys(voices))}), encoding="utf-8")
        temporary.replace(path)

    def snapshot(self) -> dict:
        with self._lock:
            job = dict(self._job) if self._job else None
        packs = [{
            **{key: value for key, value in pack.items() if key != "files"},
            "installed": pack_source(self.settings, pack["id"]) is not None,
            "managed": (self.settings.model_packs_directory / pack["id"] / "installed.json").is_file(),
            "source_url": f"https://huggingface.co/{pack['repository']}/tree/{pack['revision']}",
        } for pack in PACKS.values()]
        enabled = self.enabled_voices()
        xtts = self.settings.models_directory / "xtts" / "david_attenborough"
        rvc = self.settings.models_directory / "rvc" / "egirl"
        david_available = bool(list(xtts.glob("**/*.pth")) and list(xtts.glob("**/ref.wav")))
        egirl_available = bool(list(rvc.glob("**/*.pth")) and list(rvc.glob("**/source_ref.wav")))
        voices = [
            {"id": "david", "label": "David Attenborough", "description": "Existing XTTS fine-tune; one original checkpoint",
             "native_language": "English", "qualities": ["best"] if david_available else [],
             "required_packs": {}, "quality_label": "Original", "legacy": True},
            {"id": "egirl", "label": "E-Girl", "description": "Existing RVC voice over Qwen; conversion quality varies",
             "native_language": "English", "qualities": list(dict.fromkeys(p["quality"] for p in packs if p["installed"] and p["kind"] in {"clone", "voices"})) if egirl_available else [],
             "required_packs": {"fast": "qwen-clone-fast", "best": "qwen-clone-high"}, "legacy": True},
        ]
        voices.extend({
            "id": f"qwen:{speaker}", "label": label, "description": description,
            "native_language": language,
            "qualities": [p["quality"] for p in packs if p["kind"] == "voices" and p["installed"]],
            "required_packs": {"fast": "qwen-voices-fast", "best": "qwen-voices-high"},
            "legacy": False,
        } for speaker, (label, language, description) in QWEN_SPEAKERS.items())
        if self.settings.engine == "fake":
            for voice in voices:
                voice["qualities"] = ["best"] if voice["id"] == "david" else ["fast", "best"]
        for voice in voices:
            voice["enabled"] = voice["id"] in enabled
        return {"packs": packs, "voices": voices, "download": job,
                "free_bytes": shutil.disk_usage(self.settings.model_packs_directory).free,
                "model_directory": str(self.settings.model_packs_directory),
                "history_limit": self.settings.output_history_limit,
                "default_quality": self.settings.default_quality}

    def policy(self, voice: str, quality: str, language: str) -> dict:
        return generation_policy(self.settings, voice, quality, language).as_dict()

    def start_download(self, pack_id: str) -> dict:
        if pack_id not in PACKS:
            raise ValueError("Unknown voice pack.")
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("A voice pack download is already running.")
            if pack_source(self.settings, pack_id):
                return {"pack_id": pack_id, "status": "installed"}
            staging = safe_child_path(self.settings.model_packs_directory, f".{pack_id}.partial")
            already_downloaded = sum(p.stat().st_size for p in staging.rglob("*") if p.is_file()) if staging.exists() else 0
            required = max(0, PACKS[pack_id]["size_bytes"] - already_downloaded) + 256 * 1024 * 1024
            if shutil.disk_usage(self.settings.model_packs_directory).free < required:
                raise ValueError("There is not enough free space for this voice pack.")
            self._cancel.clear()
            self._job = {"pack_id": pack_id, "status": "downloading", "downloaded_bytes": 0,
                         "total_bytes": PACKS[pack_id]["size_bytes"], "filename": "", "error": None}
            self._thread = threading.Thread(target=self._download, args=(pack_id,), daemon=True, name="luna-pack-download")
            self._thread.start()
            return dict(self._job)

    def _update(self, **values) -> None:
        with self._lock:
            if self._job:
                self._job.update(values)

    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            raise InterruptedError("Download paused. Choose Download again to resume.")

    def _download(self, pack_id: str) -> None:
        pack = PACKS[pack_id]
        staging = safe_child_path(self.settings.model_packs_directory, f".{pack_id}.partial")
        try:
            staging.mkdir(exist_ok=True)
            finished_bytes = 0
            for entry in pack["files"]:
                self._check_cancel()
                target = safe_child_path(staging, entry["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                self._update(filename=entry["path"], status="verifying")
                if verify_file(target, entry):
                    finished_bytes += entry["size"]
                    self._update(downloaded_bytes=finished_bytes)
                    continue
                partial = safe_child_path(staging, entry["path"] + ".part")
                offset = partial.stat().st_size if partial.exists() else 0
                if offset >= entry["size"]:
                    partial.unlink()
                    offset = 0
                headers = {"User-Agent": "Luna-Voice-Catalog/0.3", "Accept-Encoding": "identity"}
                if offset:
                    headers["Range"] = f"bytes={offset}-"
                url = f"https://huggingface.co/{pack['repository']}/resolve/{pack['revision']}/{entry['path']}"
                self._update(status="downloading", downloaded_bytes=finished_bytes + offset)
                with urlopen(Request(url, headers=headers), timeout=30) as response:
                    if offset and response.status != 206:
                        offset = 0
                    if response.status == 206 and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                        raise ValueError("The model server returned an invalid resume range.")
                    with partial.open("ab" if offset else "wb") as handle:
                        while True:
                            self._check_cancel()
                            block = response.read(1024 * 1024)
                            if not block:
                                break
                            offset += len(block)
                            if offset > entry["size"]:
                                raise ValueError("The model download exceeds its expected size.")
                            handle.write(block)
                            self._update(downloaded_bytes=finished_bytes + offset)
                if offset < entry["size"]:
                    raise ConnectionError("Download interrupted; the partial file is saved. Choose Resume to continue.")
                self._update(status="verifying")
                self._check_cancel()
                if not verify_file(partial, entry):
                    partial.unlink(missing_ok=True)
                    raise ValueError(f"Checksum verification failed for {entry['path']}. Retry the download.")
                partial.replace(target)
                finished_bytes += entry["size"]
            self._check_cancel()
            (staging / "installed.json").write_text(json.dumps({"revision": pack["revision"]}), encoding="utf-8")
            destination = safe_child_path(self.settings.model_packs_directory, pack_id)
            if destination.exists():
                shutil.rmtree(destination)
            staging.replace(destination)
            self._update(status="installed", downloaded_bytes=pack["size_bytes"], filename="")
        except InterruptedError as exc:
            self._update(status="paused", error=str(exc))
        except Exception as exc:
            self._update(status="failed", error=str(exc))

    def cancel_download(self) -> None:
        self._cancel.set()

    def remove_pack(self, pack_id: str) -> None:
        if pack_id not in PACKS:
            raise ValueError("Unknown voice pack.")
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("Pause the current download before removing a pack.")
            directory = safe_child_path(self.settings.model_packs_directory, pack_id)
            if not (directory / "installed.json").is_file():
                raise ValueError("Only packs downloaded by Luna can be removed here.")
            shutil.rmtree(directory)

    def shutdown(self) -> None:
        self._cancel.set()
        if self._thread:
            self._thread.join(timeout=2)
