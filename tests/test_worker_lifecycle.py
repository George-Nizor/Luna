import time

from app.worker_manager import WorkerManager


def test_worker_starts_generates_and_unloads(test_settings, tmp_path):
    manager = WorkerManager(test_settings)
    output = tmp_path / "output.wav"
    result = manager.generate(
        model_id=test_settings.qwen_fast_model,
        text_chunks=["Hello"],
        language="English",
        reference_audio_path=None,
        reference_transcript="",
        profile_id="fixed:test",
        output_path=output,
        silence_ms=10,
    )
    assert result["chunk_count"] == 1
    assert output.exists()
    assert manager.snapshot().pid is not None
    manager.unload()
    assert manager.snapshot().pid is None


def test_worker_idle_exit(test_settings, tmp_path):
    manager = WorkerManager(test_settings)
    manager.generate(
        model_id=test_settings.qwen_fast_model,
        text_chunks=["Hello"],
        language="English",
        reference_audio_path=None,
        reference_transcript="",
        profile_id="fixed:test",
        output_path=tmp_path / "output.wav",
        silence_ms=10,
    )
    deadline = time.time() + 8
    while time.time() < deadline and manager.snapshot().pid is not None:
        time.sleep(0.2)
    assert manager.snapshot().pid is None
    manager.shutdown()
