"""FastAPI web process for Luna."""

from __future__ import annotations

import asyncio
import logging
import secrets
import shutil
import time
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
from .generation_policy import QWEN_SPEAKERS, generation_policy
from .lifecycle import monitor_application, remove_runtime_file, write_runtime_file
from .model_catalog import PACKS, ModelCatalog, pack_source
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
        app.state.model_catalog.shutdown()
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
        if len(payload.text.encode('utf-16-le')) // 2 > selected_settings.max_text_characters:
            raise ApiError("TEXT_TOO_LONG", "Text exceeds the configured character limit.", 422)
        voice = payload.voice
        # David's repository contains a single complete XTTS fine-tune. It has
        # no fast/best checkpoint pair, so the interface calls its one path
        # Original (the older API quality value remains best). E-Girl and profile voices can select
        # either Qwen source engine.
        if voice not in {"david", "egirl", "profile"} and voice not in {f"qwen:{speaker}" for speaker in QWEN_SPEAKERS}:
            raise ApiError("INVALID_REQUEST", "Unknown voice. Choose one from the voice library.", 422)
        quality = "best" if voice == "david" else (payload.quality or selected_settings.default_quality)
        policy = generation_policy(selected_settings, voice, quality, payload.language)
        if payload.instruction.strip() and not policy.supports_instruction:
            raise ApiError("INVALID_REQUEST", "Style instructions require a Qwen voice in High mode.", 422)
        if payload.temperature is not None and not policy.supports_sampling:
            raise ApiError("INVALID_REQUEST", "Sampling temperature is available for Qwen-based voices.", 422)
        temperature = payload.temperature if payload.temperature is not None else 0.7
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
                target=policy.chunk_target_characters,
                maximum=policy.chunk_max_characters,
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
        elif voice.startswith("qwen:"):
            pack_id = "qwen-voices-fast" if quality == "fast" else "qwen-voices-high"
            model_id = PACKS[pack_id]["repository"]
            display_name = QWEN_SPEAKERS[voice.removeprefix("qwen:")][0]
            output_profile_id = voice
        else:
            model_id = selected_settings.model_id(quality)
            display_name = profile.name if profile else "Voice profile"
            output_profile_id = profile.id if profile else ""
        if selected_settings.engine != "fake":
            catalog = app.state.model_catalog.snapshot()
            if voice == "profile":
                pack_id = "qwen-clone-fast" if quality == "fast" else "qwen-clone-high"
                available = pack_source(selected_settings, pack_id) is not None
            else:
                available = quality in next(item["qualities"] for item in catalog["voices"] if item["id"] == voice)
            if not available:
                raise ApiError("MODEL_NOT_INSTALLED", "This voice and quality need a local model. Open the voice library to download it.", 422)
        source_pack = None
        if voice == "egirl" and selected_settings.engine != "fake":
            custom_pack = "qwen-voices-fast" if quality == "fast" else "qwen-voices-high"
            source_pack = custom_pack if pack_source(selected_settings, custom_pack) else "qwen-clone-fast" if quality == "fast" else "qwen-clone-high"
            model_id = f"egirl-{quality}:{source_pack}"
        seed = payload.seed if payload.seed is not None else secrets.randbits(32)
        started = time.monotonic()
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
                instruction=payload.instruction.strip(),
                seed=seed,
                temperature=temperature,
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
                text_character_count=len(text.encode('utf-16-le')) // 2,
                chunk_count=int(result["chunk_count"]),
                duration_seconds=float(result["duration_seconds"]),
                created_at=now,
                text=text, voice=voice, instruction=payload.instruction.strip(), seed=seed,
                sample_rate=int(result["sample_rate"]), size_bytes=output_path.stat().st_size,
                generation_seconds=round(time.monotonic() - started, 3),
                parameters={**policy.as_dict(), "max_new_tokens": selected_settings.max_new_tokens,
                            "silence_ms": selected_settings.chunk_silence_milliseconds,
                            "temperature": temperature if policy.supports_sampling else None,
                            "top_p": 0.9 if policy.supports_sampling else None,
                            "source_model": result.get("source_model", model_id),
                            "model_revision": result.get("model_revision")},
            )
            app.state.storage.save_output_metadata(metadata)
            app.state.last_api_activity = now
            return {
                **metadata.model_dump(mode="json"),
                "audio_url": f"/api/outputs/{output_id}/audio",
                "download_url": f"/api/outputs/{output_id}/download",
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

    @app.get("/api/models")
    async def model_catalog(request: Request):
        guard(request, state_changing=False)
        return {**app.state.model_catalog.snapshot(), "fake": selected_settings.engine == "fake"}

    @app.post("/api/voices/selection")
    async def voice_selection(request: Request):
        guard(request, state_changing=True)
        try:
            body = await request.json()
            voices = body.get("voices")
            if not isinstance(voices, list) or any(not isinstance(v, str) for v in voices):
                raise ValueError("Choose voices from the catalog.")
            app.state.model_catalog.save_selection(voices)
        except (ValueError, AttributeError) as exc:
            raise ApiError("INVALID_REQUEST", str(exc), 422) from exc
        return app.state.model_catalog.snapshot()

    @app.post("/api/models/download")
    async def download_model(request: Request):
        guard(request, state_changing=True)
        try:
            body = await request.json()
            pack_id = body.get("pack_id")
            if not isinstance(pack_id, str):
                raise ValueError("Choose a voice pack from the catalog.")
            return app.state.model_catalog.start_download(pack_id)
        except (ValueError, AttributeError) as exc:
            raise ApiError("INVALID_REQUEST", str(exc), 422) from exc
        except RuntimeError as exc:
            raise ApiError("DOWNLOAD_BUSY", str(exc), 409) from exc

    @app.post("/api/models/download/pause")
    async def pause_download(request: Request):
        guard(request, state_changing=True)
        app.state.model_catalog.cancel_download()
        return {"status": "pausing"}

    @app.delete("/api/models/{pack_id}")
    async def remove_model(pack_id: str, request: Request):
        guard(request, state_changing=True)
        try:
            if pack_id not in PACKS:
                raise ValueError("Unknown voice pack.")
            # Never remove weights that may be in use by the GPU worker.
            await anyio.to_thread.run_sync(app.state.worker_manager.unload)
            app.state.model_catalog.remove_pack(pack_id)
        except GenerationBusyError as exc:
            raise ApiError("GENERATION_BUSY", "A generation is using the local models.", 409) from exc
        except (ValueError, RuntimeError) as exc:
            raise ApiError("INVALID_REQUEST", str(exc), 422) from exc
        return {"status": "removed"}

    @app.get("/api/generation-policy")
    async def get_generation_policy(request: Request, voice: str = "david", quality: str = "best", language: str = "English"):
        guard(request, state_changing=False)
        if (voice not in app.state.model_catalog.voice_ids and voice != "profile") or quality not in {"fast", "best"} or language not in LANGUAGES:
            raise ApiError("INVALID_REQUEST", "Unsupported voice, quality, or language.", 422)
        return generation_policy(selected_settings, voice, quality, language).as_dict()

    def output_record(output: OutputMetadata) -> dict:
        record = output.model_dump(mode="json")
        try:
            path = app.state.storage.output_audio_path(output.id)
            record["audio_available"] = path.is_file()
            record["size_bytes"] = path.stat().st_size
        except (OSError, ValueError):
            record["audio_available"] = False
        return record

    @app.get("/api/outputs")
    async def list_outputs(request: Request, offset: int = 0, limit: int = 50, q: str = "", voice: str = "", quality: str = "", sort: str = "newest"):
        guard(request, state_changing=False)
        if offset < 0 or not 1 <= limit <= 100 or sort not in {"newest", "oldest"} or quality not in {"", "fast", "best"}:
            raise ApiError("INVALID_REQUEST", "Invalid library filter or page size.", 422)
        all_outputs = app.state.storage.list_outputs()
        records = {item.id: output_record(item) for item in all_outputs}
        outputs = [item for item in all_outputs
                   if (not q or q.casefold() in f"{item.profile_name} {item.text or ''} {item.model_id}".casefold())
                   and (not voice or item.voice == voice or item.profile_id == voice)
                   and (not quality or item.quality == quality)]
        if sort == "oldest":
            outputs.reverse()
        page = [records[output.id] for output in outputs[offset:offset + limit]]
        return {"outputs": page, "total": len(outputs), "offset": offset, "limit": limit,
                "stats": {"count": len(all_outputs), "size_bytes": sum(record["size_bytes"] for record in records.values() if record["audio_available"]),
                          "duration_seconds": sum(item.duration_seconds for item in all_outputs)},
                "history_limit": selected_settings.output_history_limit}

    @app.get("/api/outputs/{output_id}")
    async def output_details(output_id: str, request: Request):
        guard(request, state_changing=False)
        try:
            return output_record(app.state.storage.get_output(output_id))
        except (ValueError, FileNotFoundError) as exc:
            raise ApiError("OUTPUT_NOT_FOUND", "Generated output not found.", 404) from exc

    @app.get("/api/outputs/{output_id}/metadata")
    async def output_metadata(output_id: str, request: Request):
        guard(request, state_changing=False)
        try:
            output = app.state.storage.get_output(output_id)
        except (ValueError, FileNotFoundError) as exc:
            raise ApiError("OUTPUT_NOT_FOUND", "Generated output not found.", 404) from exc
        return JSONResponse(output.model_dump(mode="json"), headers={
            "Content-Disposition": f'attachment; filename="{app.state.storage.download_name(output)[:-4]}.json"'
        })

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
        except OSError as exc:
            raise ApiError("OUTPUT_DELETE_FAILED", "Could not delete this recording. Check folder permissions or close apps using the file and try again.", 409) from exc
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

    app.state.model_catalog = ModelCatalog(selected_settings)
    app.state.storage = Storage(selected_settings)
    return app


app = create_app()
