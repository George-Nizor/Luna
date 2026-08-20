"""Spawned inference worker entrypoint."""

from __future__ import annotations

import gc
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any

import psutil


def _process_creation_time(pid: int) -> float | None:
    try:
        return float(psutil.Process(pid).create_time())
    except (psutil.Error, OSError):
        return None


def _watch_parent(parent_pid: int, parent_creation_time: float | None) -> None:
    while True:
        time.sleep(2)
        try:
            process = psutil.Process(parent_pid)
            if parent_creation_time is not None and abs(process.create_time() - parent_creation_time) > 0.01:
                os._exit(0)
        except (psutil.Error, OSError):
            os._exit(0)


def _make_engine(config: dict[str, Any], model_id: str):
    if config["engine"] == "fake":
        from .engines.fake import FakeVoiceEngine

        return FakeVoiceEngine(delay_seconds=float(config["fake_delay_seconds"]), fail=bool(config["fake_fail"])), None
    if model_id == "david":
        from .engines.xtts_clone import XttsAttenboroughEngine

        return XttsAttenboroughEngine(
            Path(str(config.get("fixed_models_directory") or Path(str(config["data_directory"])) / "models"))
            / "xtts"
            / "david_attenborough",
            allow_cpu=bool(config["allow_cpu"]),
            silence_ms=int(config["chunk_silence_milliseconds"]),
        ), None
    if model_id in {"egirl-fast", "egirl-best"}:
        from .engines.rvc_egirl import EgirlRvcEngine

        quality = model_id.removeprefix("egirl-")
        qwen_model_id = str(config[f"qwen_{quality}_model"])
        qwen_path_value = config.get(f"qwen_{quality}_path")

        return EgirlRvcEngine(
            rvc_directory=Path(
                str(config.get("fixed_models_directory") or Path(str(config["data_directory"])) / "models")
            )
            / "rvc"
            / "egirl",
            qwen_model_id=qwen_model_id,
            qwen_model_source=Path(str(qwen_path_value)) if qwen_path_value else None,
            allow_cpu=bool(config["allow_cpu"]),
            max_new_tokens=int(config["max_new_tokens"]),
            offline_mode=bool(config["offline_mode"]),
        ), None
    # This is intentionally the only import path for the Qwen adapter.
    from .engines.qwen_clone import QwenCloneEngine

    return (
        QwenCloneEngine(
            model_id=model_id,
            model_source=(
                Path(str(config["qwen_best_path"]))
                if model_id == config["qwen_best_model"] and config.get("qwen_best_path")
                else Path(str(config["qwen_fast_path"]))
                if model_id == config["qwen_fast_model"] and config.get("qwen_fast_path")
                else None
            ),
            allow_cpu=bool(config["allow_cpu"]),
            max_new_tokens=int(config["max_new_tokens"]),
            offline_mode=bool(config["offline_mode"]),
        ),
        None,
    )


def worker_main(
    request_queue: Any,
    response_queue: Any,
    config: dict[str, Any],
    parent_pid: int,
    parent_creation_time: float | None,
    model_id: str,
) -> None:
    """Run until shutdown, idle expiry, parent loss, or an unrecoverable error."""
    watchdog = threading.Thread(target=_watch_parent, args=(parent_pid, parent_creation_time), daemon=True)
    watchdog.start()
    engine = None
    last_activity = time.monotonic()
    try:
        while True:
            idle_timeout = int(config["worker_idle_seconds"])
            timeout = 1.0
            try:
                message = request_queue.get(timeout=timeout)
            except queue.Empty:
                if idle_timeout > 0 and time.monotonic() - last_activity >= idle_timeout:
                    if engine is not None:
                        engine.close()
                        engine = None
                    gc.collect()
                    try:
                        response_queue.put({"type": "stopped", "reason": "idle", "model_id": model_id})
                    except (OSError, EOFError):
                        pass
                    return
                continue

            last_activity = time.monotonic()
            message_type = message.get("type")
            if message_type == "shutdown":
                if engine is not None:
                    engine.close()
                    engine = None
                try:
                    response_queue.put({"type": "stopped", "reason": "shutdown", "model_id": model_id})
                except (OSError, EOFError):
                    pass
                return
            if message_type == "ping":
                response_queue.put({"type": "pong", "model_id": model_id})
                continue
            if message_type != "generate":
                continue

            job_id = str(message["job_id"])
            loading = False
            try:
                if engine is None:
                    loading = True
                    response_queue.put({"type": "loading_model", "job_id": job_id, "model_id": model_id})
                    engine, _ = _make_engine(config, model_id)
                    engine.load()
                    cuda_available = getattr(engine, "cuda_active", None)
                    response_queue.put(
                        {
                            "type": "ready",
                            "job_id": job_id,
                            "model_id": model_id,
                            "cuda_available": cuda_available,
                        }
                    )
                response_queue.put({"type": "progress", "job_id": job_id, "message": "Generating"})
                result = engine.generate(
                    text_chunks=list(message["text_chunks"]),
                    language=str(message["language"]),
                    reference_audio_path=Path(str(message["reference_audio_path"])),
                    reference_transcript=str(message["reference_transcript"]),
                    profile_id=str(message["profile_id"]),
                    output_path=Path(str(message["output_path"])),
                    silence_ms=int(message["silence_ms"]),
                )
                response_queue.put(
                    {
                        "type": "success",
                        "job_id": job_id,
                        "sample_rate": result.sample_rate,
                        "duration_seconds": result.duration_seconds,
                        "chunk_count": result.chunk_count,
                        "model_id": model_id,
                    }
                )
            except Exception as exc:  # worker boundary converts engine failures to serializable errors
                error_type = type(exc).__name__
                if error_type == "CudaUnavailableError":
                    code = "CUDA_UNAVAILABLE"
                elif "out of memory" in str(exc).lower() or error_type == "OutOfMemoryError":
                    code = "CUDA_OUT_OF_MEMORY"
                elif loading or (error_type in {"ImportError", "ModuleNotFoundError"} and engine is None):
                    code = "MODEL_LOAD_FAILED"
                elif engine is not None and not getattr(engine, "loaded", True):
                    code = "MODEL_LOAD_FAILED"
                else:
                    code = "GENERATION_FAILED"
                response_queue.put(
                    {
                        "type": "error",
                        "job_id": job_id,
                        "code": code,
                        "message": str(exc) or "The worker could not complete the request.",
                        "error_type": error_type,
                    }
                )
                if code in {"CUDA_OUT_OF_MEMORY", "MODEL_LOAD_FAILED"}:
                    if engine is not None:
                        engine.close()
                        engine = None
                    try:
                        response_queue.put({"type": "stopped", "reason": code, "model_id": model_id})
                    except (OSError, EOFError):
                        pass
                    return
    finally:
        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass
        gc.collect()
