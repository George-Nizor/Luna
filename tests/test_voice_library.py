from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from app.generation_policy import generation_policy
from app.model_catalog import PACKS, ModelCatalog, verify_file
from app.schemas import OutputMetadata
from app.storage import Storage, utc_now


def test_policy_varies_with_engine_language_and_audio_budget(test_settings):
    test_settings.text_chunk_target_characters = 350
    test_settings.text_chunk_max_characters = 500
    english = generation_policy(test_settings, "david", "best", "English")
    japanese = generation_policy(test_settings, "david", "best", "Japanese")
    qwen = generation_policy(test_settings, "qwen:ryan", "best", "English")
    assert english.chunk_max_characters == 200
    assert japanese.chunk_max_characters == 60
    assert qwen.supports_instruction
    assert qwen.chunk_max_characters == 100
    assert generation_policy(test_settings, "qwen:ryan", "fast", "English").chunk_max_characters == 140
    test_settings.max_new_tokens = 100
    assert generation_policy(test_settings, "qwen:ryan", "fast", "English").chunk_max_characters == 8


def test_official_voices_route_to_distinct_real_checkpoints(app_client):
    client, _ = app_client
    for quality, size in (("fast", "0.6B"), ("best", "1.7B")):
        response = client.post("/api/generate", json={
            "voice": "qwen:ryan", "quality": quality, "text": "Complete local speech.", "seed": 42,
            "instruction": "Calm narration" if quality == "best" else "",
        })
        assert response.status_code == 200, response.text
        output = response.json()
        assert output["model_id"] == f"Qwen/Qwen3-TTS-12Hz-{size}-CustomVoice"
        assert output["seed"] == 42
        assert output["voice"] == "qwen:ryan"
        assert output["text"] == "Complete local speech."
        assert output["sample_rate"] > 0 and output["size_bytes"] > 44
        assert output["generation_seconds"] >= 0
        fetched = client.get("/api/outputs/" + output["id"]).json()
        assert fetched["text"] == output["text"]
        assert fetched["audio_available"]


def test_fast_rejects_style_instead_of_silently_ignoring_it(app_client):
    client, _ = app_client
    response = client.post("/api/generate", json={
        "voice": "qwen:ryan", "quality": "fast", "text": "Hello.", "instruction": "Whisper",
    })
    assert response.status_code == 422


def test_visible_limit_is_enforced_by_api_including_utf16(app_client, test_settings):
    client, _ = app_client
    test_settings.max_text_characters = 20
    policy = client.get("/api/generation-policy?voice=qwen:ryan&quality=fast").json()
    assert policy["max_text_characters"] == 20
    response = client.post("/api/generate", json={"voice": "qwen:ryan", "text": "😀" * 11})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TEXT_TOO_LONG"
    accepted = client.post("/api/generate", json={"voice": "qwen:ryan", "text": "😀" * 10})
    assert accepted.status_code == 200
    assert accepted.json()["text_character_count"] == 20



def test_selection_is_persistent_and_downloads_are_allowlisted(app_client, test_settings):
    client, _ = app_client
    response = client.post("/api/voices/selection", json={"voices": ["qwen:ryan", "qwen:sohee"]})
    assert response.status_code == 200
    assert ModelCatalog(test_settings).enabled_voices() == ["qwen:ryan", "qwen:sohee"]
    assert client.post("/api/voices/selection", json={"voices": []}).status_code == 422
    assert client.post("/api/models/download", json={"pack_id": "https://evil.example/model"}).status_code == 422
    assert client.delete("/api/models/not-a-pack").status_code == 422


def test_metadata_export_search_and_pagination(app_client):
    client, _ = app_client
    ids = []
    for text in ("Blue moon.", "Green grass.", "Blue sky."):
        response = client.post("/api/generate", json={"voice": "qwen:aiden", "quality": "fast", "text": text})
        assert response.status_code == 200
        ids.append(response.json()["id"])
    page = client.get("/api/outputs?q=blue&limit=1").json()
    assert page["total"] == 2
    assert page["outputs"][0]["id"] == ids[2]
    assert client.get("/api/outputs?q=blue&limit=1&offset=1").json()["outputs"][0]["id"] == ids[0]
    metadata = client.get(f"/api/outputs/{ids[0]}/metadata")
    assert metadata.json()["text"] == "Blue moon."
    assert "attachment" in metadata.headers["content-disposition"]
    assert client.get("/api/outputs?limit=0").status_code == 422


def test_default_history_never_deletes_the_31st_generation(test_settings):
    storage = Storage(test_settings)
    for index in range(35):
        import uuid
        output_id = str(uuid.uuid4())
        storage.begin_output(output_id)
        storage.save_output_metadata(OutputMetadata(
            id=output_id, profile_id="fixed:david-attenborough", profile_name="David", language="English",
            quality="best", model_id="david", text_character_count=index, chunk_count=1,
            duration_seconds=1, created_at=utc_now(),
        ))
    assert len(storage.list_outputs()) == 35


def test_old_metadata_is_readable_but_cannot_invent_original_text(test_settings):
    storage = Storage(test_settings)
    output_id = "00000000-0000-4000-8000-000000000001"
    directory, _ = storage.begin_output(output_id)
    metadata = {
        "id": output_id, "profile_id": "fixed:david-attenborough", "profile_name": "David",
        "language": "English", "quality": "best", "model_id": "david",
        "text_character_count": 10, "chunk_count": 1, "duration_seconds": 1,
        "created_at": utc_now().isoformat(),
    }
    (directory / "metadata.json").write_text(json.dumps(metadata))
    assert storage.get_output(output_id).text is None
    assert storage.list_outputs()[0].id == output_id


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


def tiny_pack(monkeypatch):
    import app.model_catalog as module
    data = b"trusted tiny model file"
    entry = {"path": "model.safetensors", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    pack = {"id": "tiny", "repository": "Qwen/test", "revision": "a" * 40, "files": [entry],
            "size_bytes": len(data), "kind": "voices", "quality": "fast", "license": "Apache-2.0"}
    monkeypatch.setitem(PACKS, "tiny", pack)
    return module, data


def test_download_resumes_and_checks_before_installing(test_settings, monkeypatch):
    module, data = tiny_pack(monkeypatch)
    staging = test_settings.model_packs_directory / ".tiny.partial"
    staging.mkdir()
    (staging / "model.safetensors.part").write_bytes(data[:5])
    observed = []
    def open_response(request, timeout):
        observed.append(request.get_header("Range"))
        return Response(data[5:], 206, {"Content-Range": f"bytes 5-{len(data)-1}/{len(data)}"})
    monkeypatch.setattr(module, "urlopen", open_response)
    catalog = ModelCatalog(test_settings)
    catalog._download("tiny")
    assert observed == ["bytes=5-"]
    destination = test_settings.model_packs_directory / "tiny"
    assert verify_file(destination / "model.safetensors", PACKS["tiny"]["files"][0])
    assert (destination / "installed.json").exists()


def test_early_eof_keeps_partial_bytes_for_resume(test_settings, monkeypatch):
    module, data = tiny_pack(monkeypatch)
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: Response(data[:5]))
    catalog = ModelCatalog(test_settings)
    catalog._job = {"status": "downloading"}
    catalog._download("tiny")
    assert catalog._job["status"] == "failed"
    assert (test_settings.model_packs_directory / ".tiny.partial" / "model.safetensors.part").read_bytes() == data[:5]
    assert not (test_settings.model_packs_directory / "tiny").exists()


def test_corrupt_complete_model_never_becomes_installed(test_settings, monkeypatch):
    module, data = tiny_pack(monkeypatch)
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: Response(b"x" * len(data)))
    catalog = ModelCatalog(test_settings)
    catalog._job = {"status": "downloading"}
    catalog._download("tiny")
    assert "Checksum" in catalog._job["error"]
    assert not (test_settings.model_packs_directory / "tiny").exists()


def test_git_blob_hash_verification(tmp_path: Path):
    data = b"config"
    entry = {"size": len(data), "git_blob_sha1": hashlib.sha1(b"blob 6\0" + data).hexdigest()}
    source = tmp_path / "config.json"
    source.write_bytes(data)
    assert verify_file(source, entry)
    source.write_bytes(b"broken")
    assert not verify_file(source, entry)


def test_download_cancellation_does_not_install(test_settings, monkeypatch):
    _, _data = tiny_pack(monkeypatch)
    catalog = ModelCatalog(test_settings)
    catalog._job = {"status": "downloading"}
    catalog.cancel_download()
    catalog._download("tiny")
    assert catalog._job["status"] == "paused"


def test_audio_budget_exhaustion_is_an_error():
    import numpy as np

    from app.engines.qwen_clone import ensure_audio_budget
    with pytest.raises(RuntimeError, match="audio limit"):
        ensure_audio_budget(np.zeros(24000 * 10), 24000, 100)

def test_history_survives_changing_output_directory(test_settings, tmp_path):
    storage = Storage(test_settings)
    output_id = "00000000-0000-4000-8000-000000000001"
    old_root = test_settings.outputs_directory
    directory, audio_path = storage.begin_output(output_id)
    audio_path.write_bytes(b"audio")
    storage.save_output_metadata(OutputMetadata(
        id=output_id, profile_id="fixed:david-attenborough", profile_name="David",
        language="English", quality="best", model_id="david", text_character_count=5,
        chunk_count=1, duration_seconds=1, created_at=utc_now(),
    ))
    test_settings.output_history_directories = [str(old_root)]
    test_settings.output_directory = tmp_path / "new-outputs"
    storage = Storage(test_settings)
    assert storage.list_outputs()[0].id == output_id
    assert storage.output_audio_path(output_id) == audio_path
    storage.delete_output(output_id)
    assert not directory.exists()


def test_symlinks_inside_a_storage_root_are_rejected(tmp_path):
    from app.security import safe_child_path
    root = tmp_path / "root"
    root.mkdir()
    (root / "actual").mkdir()
    (root / "linked").symlink_to(root / "actual", target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        safe_child_path(root, "linked/file.json")


def test_sampling_parameter_is_recorded_and_validated(app_client):
    client, _ = app_client
    response = client.post("/api/generate", json={
        "voice": "qwen:ryan", "quality": "best", "text": "Temperature comparison.", "temperature": 0.6,
    })
    assert response.status_code == 200
    assert response.json()["parameters"]["temperature"] == 0.6
    for invalid in (0, 2):
        assert client.post("/api/generate", json={
            "voice": "qwen:ryan", "text": "Invalid sampling.", "temperature": invalid,
        }).status_code == 422
    assert client.post("/api/generate", json={
        "voice": "david", "text": "Original settings.", "temperature": 0.6,
    }).status_code == 422


def test_delete_keeps_history_when_audio_is_in_use(app_client, monkeypatch):
    client, _ = app_client
    generated = client.post("/api/generate", json={"voice": "qwen:ryan", "text": "Keep my history."}).json()
    output_id = generated["id"]
    original_unlink = Path.unlink

    def deny_open_audio(path, *args, **kwargs):
        if path.name == "output.wav" and path.parent.name == output_id:
            raise PermissionError("The recording is open in another app")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_open_audio)
    deleted = client.delete("/api/outputs/" + output_id)
    assert deleted.status_code == 409
    assert deleted.json()["error"]["code"] == "OUTPUT_DELETE_FAILED"
    preserved = client.get("/api/outputs/" + output_id).json()
    assert preserved["text"] == "Keep my history."
    assert preserved["audio_available"]
