"""FastAPI web process for Luna."""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import anyio
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import __version__
from .audio_utils import InvalidAudioError
from .config import Settings, configure_offline_environment
from .errors import ApiError, GenerationBusyError, GenerationTimeoutError, WorkerDiedError
from .lifecycle import monitor_application, remove_runtime_file, write_runtime_file
from .schemas import LANGUAGES, GenerationRequest, OutputMetadata
from .security import new_session_token, require_local_request, validate_uploaded_filename
from .storage import Storage
from .text_chunking import chunk_text
from .worker_manager import WorkerManager


def _now() -> datetime:
    return datetime.now(UTC)


def _configure_logging(settings: Settings) -> logging.Logger:
    logger = logging.getLogger("luna")
    if logger.handlers:
        return logger
    logger.setLevel(settings.log_level.upper())
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = RotatingFileHandler(
        settings.log_directory / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    terminal_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    terminal_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(terminal_handler)
    return logger


def _api_error_response(error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message, "request_id": error.request_id}},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    settings.ensure_directories()
    storage = Storage(settings)
    storage.cleanup_temp()
    logger = _configure_logging(settings)
    token = new_session_token()
    app.state.token = token
    app.state.worker_manager = WorkerManager(settings)
    app.state.last_heartbeat = _now()
    app.state.last_api_activity = _now()
    app.state.shutdown_requested = False
    app.state.server = getattr(app.state, "server", None)
    runtime_path = write_runtime_file(settings, token)
    monitor = asyncio.create_task(monitor_application(app))
    logger.info("application started pid=%s port=%s", runtime_path and __import__("os").getpid(), settings.port)
    try:
        yield
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
        app.state.worker_manager.shutdown()
        remove_runtime_file(settings)
        for handler in list(logger.handlers):
            handler.flush()
            handler.close()
            logger.removeHandler(handler)


def create_app(settings: Settings | None = None) -> FastAPI:
    selected_settings = settings or Settings.from_env(Path(__file__).resolve().parents[1])
    selected_settings.ensure_directories()
    configure_offline_environment(selected_settings)
    app = FastAPI(title=selected_settings.app_name, version=__version__, lifespan=lifespan)
    app.state.settings = selected_settings
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError):
        return _api_error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError):
        return _api_error_response(ApiError("INVALID_REQUEST", "The request body is invalid.", 422))

    def guard(request: Request, *, state_changing: bool, require_token: bool = True) -> None:
        app.state.last_api_activity = _now()
        require_local_request(
            host_header=request.headers.get("host"),
            origin=request.headers.get("origin"),
            token=request.headers.get("x-local-token") or request.query_params.get("token"),
            session_token=app.state.token,
            settings=selected_settings,
            state_changing=state_changing,
        )

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        template = Path(__file__).parent / "templates" / "index.html"
        html = template.read_text(encoding="utf-8").replace("{{ session_token }}", app.state.token)
        return HTMLResponse(html)

    @app.get("/api/health")
    async def health(request: Request):
        return {"status": "ok", "app": "luna", "version": __version__}

    @app.get("/api/status")
    async def status(request: Request):
        guard(request, state_changing=False)
        snapshot = app.state.worker_manager.snapshot()
        worker_remaining = None
        if snapshot.last_activity is not None and snapshot.status != "stopped" and selected_settings.worker_idle_seconds > 0:
            worker_remaining = max(0, int(selected_settings.worker_idle_seconds - (asyncio.get_running_loop().time() - snapshot.last_activity)))
        last_activity = max(app.state.last_heartbeat, app.state.last_api_activity)
        app_remaining = None
        if selected_settings.app_idle_shutdown_seconds > 0:
            app_remaining = max(0, int(selected_settings.app_idle_shutdown_seconds - (_now() - last_activity).total_seconds()))
        return {
            "app_status": "shutting_down" if app.state.shutdown_requested else "running",
            "worker_status": snapshot.status,
            "worker_pid": snapshot.pid,
            "worker_model_id": snapshot.model_id,
            "generation_active": app.state.worker_manager.generation_active,
            "cuda_available": snapshot.cuda_available,
            "last_activity": last_activity.isoformat(),
            "worker_idle_seconds_remaining": worker_remaining,
            "application_idle_seconds_remaining": app_remaining,
        }

    @app.post("/api/heartbeat")
    async def heartbeat(request: Request):
        guard(request, state_changing=True)
        app.state.last_heartbeat = _now()
        return {"status": "ok"}

    @app.get("/api/profiles")
    async def list_profiles(request: Request):
        guard(request, state_changing=False)
        return {"profiles": [profile.model_dump(mode="json") for profile in app.state.storage.list_profiles()]}

    @app.post("/api/profiles")
    async def create_profile(
        request: Request,
        name: str = Form(...),
        language: str = Form("English"),
        reference_transcript: str = Form(...),
        consent_confirmed: str = Form("false"),
        reference_audio: UploadFile = File(...),
    ):
        guard(request, state_changing=True)
        if language not in LANGUAGES:
            raise ApiError("INVALID_REQUEST", "Unsupported profile language.", 422)
        try:
            validate_uploaded_filename(reference_audio.filename)
        except ValueError as exc:
            raise ApiError("INVALID_AUDIO", str(exc), 422) from exc
        temp_path = selected_settings.temp_directory / f"{uuid.uuid4()}.upload"
        try:
            with temp_path.open("xb") as handle:
                size = 0
                while True:
                    block = await reference_audio.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > selected_settings.max_reference_file_mb * 1024 * 1024:
                        raise InvalidAudioError("The reference audio exceeds the configured file size limit.")
                    handle.write(block)
            confirmed = consent_confirmed.strip().lower() in {"1", "true", "yes", "on"}
            profile = app.state.storage.create_profile(
                name=name,
                language=language,
                reference_transcript=reference_transcript,
                consent_confirmed=confirmed,
                uploaded_path=temp_path,
            )
            return profile.model_dump(mode="json")
        except (ValueError, InvalidAudioError) as exc:
            raise ApiError("INVALID_AUDIO" if isinstance(exc, InvalidAudioError) else "INVALID_REQUEST", str(exc), 422) from exc
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    @app.delete("/api/profiles/{profile_id}")
    async def delete_profile(profile_id: str, request: Request):
        guard(request, state_changing=True)
        if app.state.worker_manager.active_profile_id == profile_id:
            raise ApiError("GENERATION_BUSY", "This profile is being used by an active generation.", 409)
        try:
            app.state.storage.delete_profile(profile_id)
        except (ValueError, FileNotFoundError) as exc:
            raise ApiError("PROFILE_NOT_FOUND", "Voice profile not found.", 404) from exc
        return {"status": "deleted"}

    @app.get("/api/profiles/{profile_id}/reference")
    async def profile_reference(profile_id: str, request: Request):
        guard(request, state_changing=False)
        try:
            path = app.state.storage.reference_path(profile_id)
        except (ValueError, FileNotFoundError) as exc:
            raise ApiError("PROFILE_NOT_FOUND", "Voice profile not found.", 404) from exc
        return FileResponse(path, media_type="audio/wav", filename="reference.wav")

    @app.post("/api/generate")
    async def generate(request: Request):
        guard(request, state_changing=True)
        if app.state.shutdown_requested:
            raise ApiError("APPLICATION_SHUTTING_DOWN", "The application is shutting down.", 503)
        try:
            payload = GenerationRequest.model_validate(await request.json())
        except (ValidationError, ValueError) as exc:
            raise ApiError("INVALID_REQUEST", "The generation request is invalid.", 422) from exc
        if payload.language not in LANGUAGES:
            raise ApiError("INVALID_REQUEST", "Unsupported generation language.", 422)
        text = payload.text.strip()
        if not text:
            raise ApiError("INVALID_REQUEST", "Text cannot be empty.", 422)
        if len(text) > selected_settings.max_text_characters:
            raise ApiError("TEXT_TOO_LONG", "Text exceeds the configured character limit.", 422)
        voice = payload.voice
        # David's repository contains a single complete XTTS fine-tune. It has
        # no fast/best checkpoint pair, so its one configured path is exposed
        # honestly as fixed Best quality. E-Girl and profile voices can select
        # either Qwen source engine.
        quality = "best" if voice == "david" else (payload.quality or selected_settings.default_quality)
        is_profile = voice == "profile"
        profile = None
        reference_path = None
        if is_profile:
            if not payload.profile_id:
                raise ApiError("INVALID_REQUEST", "Choose a saved voice profile.", 422)
            try:
                profile = app.state.storage.get_profile(payload.profile_id)
                reference_path = app.state.storage.reference_path(payload.profile_id)
            except FileNotFoundError as exc:
                raise ApiError("PROFILE_NOT_FOUND", "Voice profile not found.", 404) from exc
            except (ValueError, OSError) as exc:
                raise ApiError("INVALID_REQUEST", str(exc), 422) from exc
        try:
            chunks = chunk_text(
                text,
                target=selected_settings.text_chunk_target_characters,
                maximum=selected_settings.text_chunk_max_characters,
            )
        except ValueError as exc:
            raise ApiError("INVALID_REQUEST", str(exc), 422) from exc
        if voice == "david":
            model_id = "david"
            display_name = "David Attenborough"
            output_profile_id = "fixed:david-attenborough"
        elif voice == "egirl":
            model_id = f"egirl-{quality}"
            display_name = "E-Girl"
            output_profile_id = "fixed:egirl-rvc"
        else:
            model_id = selected_settings.model_id(quality)
            display_name = profile.name if profile else "Voice profile"
            output_profile_id = profile.id if profile else ""
        output_id = str(uuid.uuid4())
        try:
            _, output_path = app.state.storage.begin_output(output_id)
        except OSError as exc:
            raise ApiError("GENERATION_FAILED", "Could not create the output directory.", 500) from exc
        try:
            from functools import partial

            run_worker = partial(
                app.state.worker_manager.generate,
                model_id=model_id,
                text_chunks=chunks,
                language=payload.language,
                reference_audio_path=reference_path,
                reference_transcript=profile.reference_transcript if profile else "",
                profile_id=profile.id if profile else output_profile_id,
                output_path=output_path,
                silence_ms=selected_settings.chunk_silence_milliseconds,
            )
            result = await anyio.to_thread.run_sync(run_worker)
            now = _now()
            metadata = OutputMetadata(
                id=output_id,
                profile_id=output_profile_id,
                profile_name=display_name,
                language=payload.language,
                quality=quality,
                model_id=model_id,
                text_character_count=len(text),
                chunk_count=int(result["chunk_count"]),
                duration_seconds=float(result["duration_seconds"]),
                created_at=now,
            )
            app.state.storage.save_output_metadata(metadata)
            app.state.last_api_activity = now
            return {
                "id": output_id,
                "profile_id": output_profile_id,
                "profile_name": display_name,
                "quality": quality,
                "model_id": metadata.model_id,
                "chunk_count": metadata.chunk_count,
                "duration_seconds": metadata.duration_seconds,
                "audio_url": f"/api/outputs/{output_id}/audio",
                "download_url": f"/api/outputs/{output_id}/download",
                "created_at": metadata.created_at.isoformat(),
            }
        except GenerationBusyError as exc:
            raise ApiError("GENERATION_BUSY", "Another generation is already running.", 409) from exc
        except GenerationTimeoutError as exc:
            raise ApiError("GENERATION_TIMEOUT", "Generation exceeded the configured time limit.", 504) from exc
        except WorkerDiedError as exc:
            raise ApiError("WORKER_DIED", "The inference worker exited unexpectedly.", 500) from exc
        except RuntimeError as exc:
            code = getattr(exc, "code", "GENERATION_FAILED")
            status_code = 503 if code in {"CUDA_UNAVAILABLE", "MODEL_LOAD_FAILED"} else 500
            raise ApiError(code, str(exc), status_code) from exc
        finally:
            if not (output_path.exists() and (output_path.parent / "metadata.json").exists()):
                shutil.rmtree(selected_settings.outputs_directory / output_id, ignore_errors=True)

    @app.get("/api/outputs")
    async def list_outputs(request: Request):
        guard(request, state_changing=False)
        return {"outputs": [output.model_dump(mode="json") for output in app.state.storage.list_outputs()]}

    @app.get("/api/outputs/{output_id}/audio")
    async def output_audio(output_id: str, request: Request):
        guard(request, state_changing=False)
        try:
            app.state.storage.get_output(output_id)
            path = app.state.storage.output_audio_path(output_id)
        except (ValueError, FileNotFoundError) as exc:
            raise ApiError("OUTPUT_NOT_FOUND", "Generated output not found.", 404) from exc
        return FileResponse(path, media_type="audio/wav", filename="output.wav")

    @app.get("/api/outputs/{output_id}/download")
    async def output_download(output_id: str, request: Request):
        guard(request, state_changing=False)
        try:
            metadata = app.state.storage.get_output(output_id)
            path = app.state.storage.output_audio_path(output_id)
        except (ValueError, FileNotFoundError) as exc:
            raise ApiError("OUTPUT_NOT_FOUND", "Generated output not found.", 404) from exc
        return FileResponse(path, media_type="audio/wav", filename=app.state.storage.download_name(metadata))

    @app.delete("/api/outputs/{output_id}")
    async def delete_output(output_id: str, request: Request):
        guard(request, state_changing=True)
        try:
            app.state.storage.delete_output(output_id)
        except (ValueError, FileNotFoundError) as exc:
            raise ApiError("OUTPUT_NOT_FOUND", "Generated output not found.", 404) from exc
        return {"status": "deleted"}

    @app.post("/api/worker/unload")
    async def unload_worker(request: Request):
        guard(request, state_changing=True)
        body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
        force = bool(body.get("force", False)) if isinstance(body, dict) else False
        try:
            from functools import partial

            state = await anyio.to_thread.run_sync(partial(app.state.worker_manager.unload, force=force))
        except GenerationBusyError as exc:
            raise ApiError("GENERATION_BUSY", "A generation is active; use force to unload it.", 409) from exc
        return {"status": state}

    @app.post("/api/app/shutdown")
    async def shutdown(request: Request):
        guard(request, state_changing=True)
        app.state.shutdown_requested = True
        return {"status": "shutting_down"}

    app.state.storage = Storage(selected_settings)
    return app


app = create_app()
