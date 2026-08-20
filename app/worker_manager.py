"""Main-process controller for the isolated inference worker."""

from __future__ import annotations

import multiprocessing
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from .config import Settings
from .errors import GenerationBusyError, GenerationTimeoutError, WorkerDiedError
from .worker_process import worker_main


@dataclass(slots=True)
class WorkerSnapshot:
    status: str = "stopped"
    pid: int | None = None
    model_id: str | None = None
    last_activity: float | None = None
    cuda_available: bool | None = None


class WorkerManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._process: multiprocessing.Process | None = None
        self._request_queue: Any = None
        self._response_queue: Any = None
        self._snapshot = WorkerSnapshot()
        self._lock = threading.Lock()
        self._generation_lock = threading.Lock()
        self._accepting = True
        self.active_profile_id: str | None = None
        self.active_job_id: str | None = None

    @property
    def generation_active(self) -> bool:
        return self._generation_lock.locked()

    def _reconcile(self) -> None:
        if self._process is not None and not self._process.is_alive():
            try:
                self._process.close()
            except (OSError, ValueError):
                pass
            self._close_queues()
            self._process = None
            self._snapshot = WorkerSnapshot(status="stopped")

    def snapshot(self) -> WorkerSnapshot:
        self._reconcile()
        return WorkerSnapshot(
            status=self._snapshot.status,
            pid=self._process.pid if self._process and self._process.is_alive() else None,
            model_id=self._snapshot.model_id if self._process else None,
            last_activity=self._snapshot.last_activity,
            cuda_available=self._snapshot.cuda_available,
        )

    def _close_queues(self) -> None:
        for channel in (self._request_queue, self._response_queue):
            if channel is not None:
                try:
                    # Queue feeder threads can otherwise block shutdown after
                    # an interrupted or force-terminated ML worker on Windows.
                    channel.cancel_join_thread()
                    channel.close()
                except (OSError, AssertionError):
                    pass
        self._request_queue = None
        self._response_queue = None

    def _start(self, model_id: str) -> None:
        ctx = multiprocessing.get_context("spawn")
        self._request_queue = ctx.Queue()
        self._response_queue = ctx.Queue()
        parent = psutil.Process(os.getpid())
        self._snapshot = WorkerSnapshot(status="starting", model_id=model_id, last_activity=time.monotonic())
        self._process = ctx.Process(
            target=worker_main,
            args=(
                self._request_queue,
                self._response_queue,
                self.settings.worker_dict(),
                os.getpid(),
                float(parent.create_time()),
                model_id,
            ),
            name="luna-inference",
        )
        self._process.daemon = False
        self._process.start()

    def _stop_process(self, *, force: bool = False) -> None:
        process = self._process
        if process is None:
            self._snapshot = WorkerSnapshot(status="stopped")
            return
        self._snapshot.status = "stopping"
        if not force and process.is_alive() and self._request_queue is not None:
            try:
                self._request_queue.put({"type": "shutdown"})
                process.join(timeout=5)
            except (OSError, EOFError):
                pass
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=2)
        try:
            process.close()
        except (OSError, ValueError):
            pass
        self._close_queues()
        self._process = None
        self._snapshot = WorkerSnapshot(status="stopped")

    def _ensure_worker(self, model_id: str) -> None:
        self._reconcile()
        if self._process is not None and self._process.is_alive() and self._snapshot.model_id != model_id:
            self._stop_process()
        if self._process is None:
            self._start(model_id)

    def generate(
        self,
        *,
        model_id: str,
        text_chunks: list[str],
        language: str,
        reference_audio_path: Path | None,
        reference_transcript: str,
        profile_id: str,
        output_path: Path,
        silence_ms: int,
    ) -> dict[str, Any]:
        if not self._accepting:
            raise RuntimeError("application is shutting down")
        if not self._generation_lock.acquire(blocking=False):
            raise GenerationBusyError()
        job_id = str(uuid.uuid4())
        self.active_job_id = job_id
        self.active_profile_id = profile_id
        try:
            with self._lock:
                self._ensure_worker(model_id)
                self._snapshot.status = "loading_model" if self._snapshot.status == "starting" else "generating"
                self._snapshot.last_activity = time.monotonic()
                assert self._request_queue is not None and self._response_queue is not None
                request_queue = self._request_queue
                response_queue = self._response_queue
                request_queue.put(
                    {
                        "type": "generate",
                        "job_id": job_id,
                        "text_chunks": text_chunks,
                        "language": language,
                        "reference_audio_path": str(reference_audio_path),
                        "reference_transcript": reference_transcript,
                        "profile_id": profile_id,
                        "output_path": str(output_path),
                        "silence_ms": silence_ms,
                    }
                )
                deadline = time.monotonic() + self.settings.generation_timeout_seconds
                while time.monotonic() < deadline:
                    remaining = max(0.05, min(0.5, deadline - time.monotonic()))
                    try:
                        response = response_queue.get(timeout=remaining)
                    except queue.Empty:
                        if self._process is None or not self._process.is_alive():
                            raise WorkerDiedError("The inference worker exited unexpectedly.")
                        continue
                    except (OSError, EOFError, ValueError) as exc:
                        raise WorkerDiedError("The inference worker queues closed unexpectedly.") from exc
                    response_type = response.get("type")
                    self._snapshot.last_activity = time.monotonic()
                    if response_type == "loading_model":
                        self._snapshot.status = "loading_model"
                    elif response_type == "ready":
                        self._snapshot.status = "ready"
                        self._snapshot.cuda_available = response.get("cuda_available")
                    elif response_type == "progress":
                        self._snapshot.status = "generating"
                    elif response_type == "success" and response.get("job_id") == job_id:
                        self._snapshot.status = "ready"
                        return response
                    elif response_type == "error" and response.get("job_id") == job_id:
                        self._snapshot.status = "error"
                        error = RuntimeError(str(response.get("message", "Generation failed")))
                        setattr(error, "code", response.get("code", "GENERATION_FAILED"))
                        raise error
                    elif response_type == "stopped":
                        self._snapshot = WorkerSnapshot(status="stopped")
                self._stop_process(force=True)
                raise GenerationTimeoutError()
        finally:
            self.active_job_id = None
            self.active_profile_id = None
            self._generation_lock.release()

    def unload(self, *, force: bool = False) -> str:
        if self.generation_active and not force:
            raise GenerationBusyError()
        self._stop_process(force=force)
        return self._snapshot.status

    def shutdown(self) -> None:
        self._accepting = False
        if self.generation_active:
            self._stop_process(force=True)
        else:
            self._stop_process(force=False)
        self.active_job_id = None
        self.active_profile_id = None
        self._close_queues()

    def reopen(self) -> None:
        self._accepting = True
