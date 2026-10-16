"""
IntentLock — FastAPI Backend Application
Central entrypoint providing:
1. Truthful Liveness and Readiness Health Endpoints
2. Canonical Bounded Voice-Turn Gateway (/api/v1/voice/turn)
3. Fail-Closed Route Protection and Authorization Policy Facade
4. Grounded Employee Knowledge Retrieval and Canonical Truth Index
"""

import os
import re
import uuid
import base64
import hashlib
import json
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    Response,
    Query,
    Form,
    File,
    UploadFile,
    Depends,
    status,
)
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field
import httpx

from backend.core.config import settings
from backend.core.security import require_verified_session, AuthorizationPolicyFacade
from backend.core.ports import (
    SpeechInputPort,
    SpeechOutputPort,
    VoiceEvidencePort,
    VoiceEvidenceResult,
    AnswerGenerationPort,
    UnavailableSpeechInputAdapter,
    UnavailableSpeechOutputAdapter,
    UnavailableVoiceEvidenceAdapter,
    UnavailableAnswerAdapter,
    FailClosedPolicyAdapter,
)
from backend.adapters import (
    AudioDecoder,
    SpeechVADService,
    FasterWhisperSTTAdapter,
    KokoroTTSAdapter,
)
from backend.adapters.detectif_adapter import DetectifVoiceEvidenceAdapter
from backend.adapters.openai_answer_adapter import OpenAIAnswerAdapter
from backend.voice_preview import register_voice_preview
from backend.adapters.identity_mapping_store import IdentityMappingStore
from backend.core.scoped_authorization import ScopedAuthorizationService
from backend.services.employee_knowledge_service import EmployeeKnowledgeService
from backend.services.ticket_knowledge_service import TicketKnowledgeService
from backend.services.conversation_dispatch import ConversationDispatcher, parse_local, conversation_store, block
from backend.services.conversation_dispatch import IntentPlan
from backend.services.employee_visibility_service import EmployeeVisibilityService
from backend.services.ollama_knowledge_service import OllamaKnowledgeService
from backend.models.knowledge import (
    KnowledgeQueryRequest,
    KnowledgeQueryResponse,
    HealthResponse,
    LivenessResponse,
    ReadinessResponse,
    EmployeeSummaryItem,
)
from backend.models.turn import (
    VoiceTurnResponse,
    TurnSessionInfo,
    SessionActor,
    OriginalAudioMetadata,
    SpokenAudioPayload,
    TrustEvidence,
)
from backend.models.errors import SafeErrorDetail, SafeErrorResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("intentlock_backend")

# Global singleton service instances
knowledge_service: Optional[EmployeeKnowledgeService] = None
ollama_service: Optional[OllamaKnowledgeService] = None

# Active adapter instances (default to fail-closed, unavailable)
speech_vad_service: Optional[SpeechVADService] = None
speech_input_port: SpeechInputPort = UnavailableSpeechInputAdapter()
speech_output_port: SpeechOutputPort = UnavailableSpeechOutputAdapter()
voice_evidence_port: VoiceEvidencePort = UnavailableVoiceEvidenceAdapter()
answer_port: AnswerGenerationPort = UnavailableAnswerAdapter()
policy_port = FailClosedPolicyAdapter()


def get_speech_input_port() -> SpeechInputPort:
    """Dependency provider for speech input adapter."""
    return speech_input_port


def get_speech_output_port() -> SpeechOutputPort:
    """Dependency provider for speech output adapter."""
    return speech_output_port


def get_voice_evidence_port() -> VoiceEvidencePort:
    """Dependency provider for voice evidence (Detectif) adapter."""
    return voice_evidence_port


def get_answer_port() -> AnswerGenerationPort:
    """Dependency provider for answer generation (OpenAI) adapter."""
    return answer_port


def set_speech_adapters(input_port: SpeechInputPort, output_port: SpeechOutputPort):
    """Runtime injector for testing or switching speech adapters."""
    global speech_input_port, speech_output_port
    speech_input_port = input_port
    speech_output_port = output_port


def set_voice_evidence_port(port: VoiceEvidencePort):
    """Runtime injector for testing or switching voice evidence adapter."""
    global voice_evidence_port
    voice_evidence_port = port


def set_answer_port(port: AnswerGenerationPort):
    """Runtime injector for testing or switching answer generation adapter."""
    global answer_port
    answer_port = port



@asynccontextmanager
async def lifespan(app: FastAPI):
    global knowledge_service, ollama_service, speech_vad_service, speech_input_port, speech_output_port, ticket_service
    logger.info("Initializing IntentLock Employee Knowledge Base...")
    knowledge_service = EmployeeKnowledgeService.get_instance(data_path=settings.DATA_PATH)
    logger.info("Initializing IntentLock Ticket Knowledge Base...")
    ticket_service = TicketKnowledgeService.get_instance()
    ollama_service = OllamaKnowledgeService(
        knowledge_service=knowledge_service,
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL,
        timeout=settings.OLLAMA_TIMEOUT_SECONDS,
    )
    logger.info(
        f"Backend startup complete. {len(knowledge_service.list_all_employees())} employees and {len(ticket_service.list_all_tickets())} tickets loaded in memory."
    )

    # Initialize real speech pipeline if configured and not running in offline test mode
    if settings.ENABLE_SPEECH_PIPELINE and os.getenv("INTENTLOCK_OFFLINE_TESTS") != "1":
        try:
            logger.info("Initializing IntentLock Open-Source Speech Pipeline (VAD, STT, TTS)...")
            speech_vad_service = SpeechVADService.get_instance(threshold=settings.SPEECH_VAD_THRESHOLD)

            stt_adapter = FasterWhisperSTTAdapter(
                model_name=settings.SPEECH_STT_MODEL,
                device=settings.SPEECH_STT_DEVICE,
                compute_type=settings.SPEECH_STT_COMPUTE_TYPE,
                vad_service=speech_vad_service,
            )
            stt_adapter.warmup()

            tts_adapter = KokoroTTSAdapter(
                lang_code=settings.SPEECH_TTS_LANG,
                voice=settings.SPEECH_TTS_VOICE,
                speed=settings.SPEECH_TTS_SPEED,
                device="cpu",
            )
            tts_adapter.warmup()

            speech_input_port = stt_adapter
            speech_output_port = tts_adapter
            logger.info("Speech Pipeline (Silero VAD + Faster-Whisper + Kokoro TTS) loaded and warmed up successfully.")
        except Exception as e:
            logger.error(f"Speech pipeline initialization failed: {e}. Falling back to unavailable adapters.")
            speech_input_port = UnavailableSpeechInputAdapter()
            speech_output_port = UnavailableSpeechOutputAdapter()

    # Initialize Voice Evidence Adapter (Detectif)
    global voice_evidence_port, answer_port
    if settings.DETECTIF_API_KEY and os.getenv("INTENTLOCK_OFFLINE_TESTS") != "1":
        logger.info("Detectif API key configured. Initializing DetectifVoiceEvidenceAdapter...")
        voice_evidence_port = DetectifVoiceEvidenceAdapter(account_alias=settings.DETECTIF_ACCOUNT_ALIAS)
    else:
        logger.info("Detectif API key unconfigured. Using UnavailableVoiceEvidenceAdapter (fail-closed).")
        voice_evidence_port = UnavailableVoiceEvidenceAdapter()

    # Initialize Answer Generation Adapter (OpenAI or Unavailable)
    if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY and os.getenv("INTENTLOCK_OFFLINE_TESTS") != "1":
        logger.info(f"OpenAI configured ({settings.OPENAI_MODEL}). Initializing OpenAIAnswerAdapter...")
        answer_port = OpenAIAnswerAdapter(
            model=settings.OPENAI_MODEL,
            max_output_tokens=settings.OPENAI_MAX_OUTPUT_TOKENS,
        )
    else:
        logger.info("OpenAI answer generation unconfigured or in offline test mode. Using UnavailableAnswerAdapter.")
        answer_port = UnavailableAnswerAdapter()

    yield
    logger.info("Shutting down IntentLock backend.")
    if isinstance(voice_evidence_port, DetectifVoiceEvidenceAdapter):
        await voice_evidence_port.client_wrapper.close()
    if isinstance(answer_port, OpenAIAnswerAdapter):
        await answer_port.close()



app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="IntentLock Shared AI Assistance Workspace — Backend & Gateway Foundation",
    lifespan=lifespan,
)

register_voice_preview(app, settings, get_speech_input_port, lambda: speech_vad_service)


# =============================================================================
# Middleware: Request Correlation & Streaming Size Limit
# =============================================================================

class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming_id = request.headers.get("X-Request-Id")
        if incoming_id and re.match(r"^[a-zA-Z0-9_-]{1,64}$", incoming_id):
            request_id = incoming_id
        else:
            request_id = f"req_{uuid.uuid4().hex[:12]}"

        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id

        # Attach no-store cache control for sensitive, turn, or private routes
        path = request.url.path
        if "/voice/turn" in path or "/knowledge/" in path or "/employees" in path:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"

        return response


class BoundedRequestStreamingMiddleware(BaseHTTPMiddleware):
    """
    Enforces a strict upper bound on total request bytes before and during streaming,
    preventing unbounded multipart memory/disk exhaustion on chunked or missing-length requests.
    """
    async def dispatch(self, request: Request, call_next):
        max_bytes = settings.MAX_REQUEST_BYTES

        # 1. Reject if Content-Length header is present and exceeds max limit
        content_length_header = request.headers.get("content-length")
        if content_length_header:
            try:
                cl = int(content_length_header)
                if cl > max_bytes:
                    request_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:12]}"
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": f"Total request payload exceeds maximum limit of {max_bytes} bytes.",
                                "retryable": False,
                            }
                        },
                        headers={"X-Request-Id": request_id, "Cache-Control": "no-store"},
                    )
            except ValueError:
                pass

        # 2. Count streamed chunks for chunked or missing Content-Length ingress
        original_receive = request.receive
        accumulated_bytes = 0

        async def bounded_receive():
            nonlocal accumulated_bytes
            message = await original_receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                accumulated_bytes += len(body)
                if accumulated_bytes > max_bytes:
                    request.state.payload_too_large = True
                    raise HTTPException(
                        status_code=413,
                        detail=f"Total request payload exceeds maximum limit of {max_bytes} bytes.",
                    )
            return message

        request._receive = bounded_receive
        try:
            return await call_next(request)
        except HTTPException as exc:
            if exc.status_code == 413 or getattr(request.state, "payload_too_large", False):
                request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "PAYLOAD_TOO_LARGE",
                            "message": f"Total request payload exceeds maximum limit of {max_bytes} bytes.",
                            "retryable": False,
                        }
                    },
                    headers={"X-Request-Id": request_id, "Cache-Control": "no-store"},
                )
            raise


app.add_middleware(BoundedRequestStreamingMiddleware)
app.add_middleware(RequestCorrelationMiddleware)

# Explicit CORS configuration for frontend origins (No Wildcards)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],

    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)


# =============================================================================
# Global Exception Handlers (Sanitized, Safe Responses)
# =============================================================================

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    if getattr(request.state, "payload_too_large", False) or exc.status_code == 413:
        payload = SafeErrorResponse(
            api_version="1",
            request_id=request_id,
            error=SafeErrorDetail(
                code="PAYLOAD_TOO_LARGE",
                message=f"Total request payload exceeds maximum limit of {settings.MAX_REQUEST_BYTES} bytes.",
                retryable=False,
            ),
        )
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content=payload.model_dump(),
            headers={"X-Request-Id": request_id, "Cache-Control": "no-store"},
        )

    code = "HTTP_ERROR"
    if exc.status_code == 400:
        code = "BAD_REQUEST"
    elif exc.status_code == 401:
        code = "UNAUTHORIZED"
    elif exc.status_code == 403:

        code = "FORBIDDEN"
    elif exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 413:
        code = "PAYLOAD_TOO_LARGE"
    elif exc.status_code == 415:
        code = "UNSUPPORTED_MEDIA_TYPE"

    payload = SafeErrorResponse(
        api_version="1",
        request_id=request_id,
        error=SafeErrorDetail(
            code=code,
            message=str(exc.detail),
            retryable=False,
        ),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(),
        headers={"X-Request-Id": request_id, "Cache-Control": "no-store"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    logger.error(f"Unhandled server error on {request.method} {request.url.path} [{request_id}]: {exc}", exc_info=True)
    payload = SafeErrorResponse(
        api_version="1",
        request_id=request_id,
        error=SafeErrorDetail(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred. Please contact support with the request ID.",
            retryable=False,
        ),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=payload.model_dump(),
        headers={"X-Request-Id": request_id, "Cache-Control": "no-store"},
    )


# =============================================================================
# Truthful Health & Diagnostics Endpoints
# =============================================================================

@app.get("/", tags=["Root"])
def root_index():
    """Root endpoint welcoming visitors and providing API documentation links."""
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "documentation": "/docs",
        "health": "/health/live",
        "readiness": "/health/ready",
    }


@app.get("/health/live", response_model=LivenessResponse, tags=["Health"])
@app.get(f"{settings.API_V1_PREFIX}/health/live", response_model=LivenessResponse, tags=["Health"])
def health_live():
    """
    Truthful Liveness Endpoint.
    Returns HTTP 200 if the backend process is running and responding.
    """
    return LivenessResponse(
        status="live",
        project=settings.PROJECT_NAME,
        version=settings.VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health/ready", tags=["Health"])
@app.get(f"{settings.API_V1_PREFIX}/health/ready", tags=["Health"])
def health_ready(response: Response):
    """
    Truthful Readiness Endpoint.
    In Stage 1, returns HTTP 503 because the voice processing pipeline (Detectif & Speech)
    is unconfigured. Truthfully reports distinct states of all components.
    """
    svc = EmployeeKnowledgeService.get_instance()
    dataset_ready = svc.is_loaded and len(svc.list_all_employees()) > 0

    ollama_ready = False
    try:
        with httpx.Client(timeout=0.5) as client:
            res = client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            ollama_ready = res.status_code == 200
    except Exception:
        ollama_ready = False

    stt_ready = getattr(speech_input_port, "is_ready", lambda: False)()
    tts_ready = getattr(speech_output_port, "is_ready", lambda: False)()
    speech_ready = stt_ready and tts_ready

    evidence_ready = getattr(voice_evidence_port, "is_configured", lambda: False)()
    components = {
        "dataset": "ready" if dataset_ready else "not_ready",
        "speech_service": "ready" if speech_ready else "unavailable",
        "voice_evidence": "ready" if evidence_ready else "unconfigured",
    }

    if settings.LLM_PROVIDER == "openai":
        openai_ready = bool(settings.OPENAI_API_KEY)
        components["openai"] = "ready" if openai_ready else "unconfigured"
        llm_ready = openai_ready
    else:
        components["ollama"] = "ready" if ollama_ready else "unreachable"
        llm_ready = ollama_ready

    is_fully_ready = dataset_ready and speech_ready and evidence_ready and llm_ready
    if not is_fully_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_fully_ready else "not_ready",
        "project": settings.PROJECT_NAME,
        "components": components,
        "reason": (
            "System is fully configured and ready."
            if is_fully_ready
            else "Subsystem components (speech, voice evidence, or LLM) are not fully ready."
        ),
    }


@app.get(f"{settings.API_V1_PREFIX}/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """
    Legacy Health Check Endpoint.
    Reports indexed employee count, LLM reachability, and explicit voice pipeline readiness.
    """
    svc = EmployeeKnowledgeService.get_instance()
    total_emps = len(svc.list_all_employees())

    ollama_online = False
    if settings.LLM_PROVIDER == "openai":
        ollama_online = bool(settings.OPENAI_API_KEY)
        llm_model = settings.OPENAI_MODEL
    else:
        try:
            with httpx.Client(timeout=0.5) as client:
                res = client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                ollama_online = res.status_code == 200
        except Exception:
            ollama_online = False
        llm_model = settings.OLLAMA_MODEL

    stt_ready = getattr(speech_input_port, "is_ready", lambda: False)()
    tts_ready = getattr(speech_output_port, "is_ready", lambda: False)()
    evidence_ready = getattr(voice_evidence_port, "is_configured", lambda: False)()
    speech_ready = stt_ready and tts_ready
    voice_pipeline_ready = speech_ready and evidence_ready

    return HealthResponse(
        status="HEALTHY",
        project=settings.PROJECT_NAME,
        version=settings.VERSION,
        indexed_employees_count=total_emps,
        ollama_model=llm_model,
        ollama_reachable=ollama_online,
        data_source=settings.DATA_PATH,
        voice_pipeline_ready=voice_pipeline_ready,
    )




# =============================================================================
# Canonical Voice Turn Endpoint (POST /api/v1/voice/turn)
# =============================================================================

@app.post(
    f"{settings.API_V1_PREFIX}/voice/turn",
    response_model=VoiceTurnResponse,
    status_code=status.HTTP_200_OK,
    tags=["Voice Gateway"],
)
async def process_voice_turn(
    request: Request,
    audio_file: UploadFile = File(..., description="Uploaded speech recording"),
    client_turn_id: str = Form(..., description="Client correlation turn ID"),
    session_id: Optional[str] = Form(None, description="Optional opaque session identifier"),
    candidate_employee_id: Optional[str] = Form(None, description="Optional claimed employee ID (e.g. EMP-1001)"),
    client_timestamp: Optional[str] = Form(None, description="Client diagnostic timestamp"),
    stt_port: SpeechInputPort = Depends(get_speech_input_port),
    tts_port: SpeechOutputPort = Depends(get_speech_output_port),
    voice_port: VoiceEvidencePort = Depends(get_voice_evidence_port),
    ans_port: AnswerGenerationPort = Depends(get_answer_port),
):
    """
    Canonical Voice Turn Ingress Endpoint.
    Validates bounded media transport, computes SHA-256 digest, normalizes MIME type,
    executes real VAD, Faster-Whisper STT, Detectif dual verification (match + real),
    scoped authorization, pre-LLM context filtering, and Kokoro TTS synthesis.
    Returns 503 unavailable envelope when speech adapters are unconfigured (Stage 1 contract).
    """
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")

    # 1. Validate client_turn_id
    clean_turn_id = client_turn_id.strip()
    if not clean_turn_id or len(clean_turn_id) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_turn_id must be a non-empty string with maximum length of 128 characters.",
        )

    # 2. Check total Content-Length header against max request limit
    content_length_header = request.headers.get("content-length")
    if content_length_header:
        try:
            cl = int(content_length_header)
            if cl > settings.MAX_REQUEST_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Total request payload exceeds maximum limit of {settings.MAX_REQUEST_BYTES} bytes.",
                )
        except ValueError:
            pass

    # 3. Validate declared media type (handle parameters like codecs=opus)
    declared_type = audio_file.content_type or "application/octet-stream"
    normalized_mime = declared_type.split(";")[0].strip().lower()
    if normalized_mime not in settings.ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported audio media type '{declared_type}'. Allowed types: {', '.join(settings.ALLOWED_AUDIO_TYPES)}",
        )

    # 4. Stream read audio chunks to enforce size bound and compute SHA-256
    hasher = hashlib.sha256()
    audio_buffer = bytearray()
    total_bytes = 0
    chunk_size = 64 * 1024  # 64 KiB chunks

    try:
        while True:
            chunk = await audio_file.read(chunk_size)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > settings.MAX_AUDIO_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Audio file size exceeds operational limit of {settings.MAX_AUDIO_BYTES} bytes (8 MiB).",
                )
            hasher.update(chunk)
            audio_buffer.extend(chunk)
    finally:
        await audio_file.close()

    if total_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio file is empty (0 bytes).",
        )

    # 5. Build request-scoped audio metadata
    safe_filename = os.path.basename(audio_file.filename or "utterance.bin")
    sha256_digest = hasher.hexdigest()

    audio_metadata = OriginalAudioMetadata(
        safe_filename=safe_filename,
        declared_content_type=declared_type,
        normalized_mime_type=normalized_mime,
        byte_count=total_bytes,
        sha256_digest=sha256_digest,
    )

    # Exact delivery retries use the same logical turn and audio. A cached
    # private response is usable only while its original session remains valid.
    replay_store = IdentityMappingStore.get_instance()
    replay_key = "voice_" + hashlib.sha256(
        f"{clean_turn_id}|{(candidate_employee_id or '').strip().upper()}|{(session_id or '').strip()}".encode()
    ).hexdigest()
    replay = replay_store.get_idempotency_entry(replay_key)
    if replay:
        if replay["audio_digest"] != sha256_digest:
            raise HTTPException(status_code=409, detail="This logical turn ID was already used with different audio.")
        cached = replay["response"]
        cached_session_id = (cached.get("session") or {}).get("sessionId")
        if not cached_session_id or ((valid := replay_store.get_session(cached_session_id)) and valid.is_valid):
            return JSONResponse(status_code=200, content=cached, headers={"Cache-Control": "no-store", "X-Request-Id": request_id})
        raise HTTPException(status_code=401, detail="The original verified session is no longer valid for this turn.")

    logger.info(
        f"Audio turn received [{request_id}]: turn_id={clean_turn_id} bytes={total_bytes} "
        f"mime={normalized_mime} sha256={sha256_digest[:12]}..."
    )

    # 6. If speech port is unconfigured/unavailable -> Return documented Stage 1 unavailable envelope
    if isinstance(stt_port, UnavailableSpeechInputAdapter) or not getattr(stt_port, "is_available", True):
        unavailable_envelope = VoiceTurnResponse(
            api_version="1",
            request_id=request_id,
            client_turn_id=clean_turn_id,
            status="unavailable",
            session=TurnSessionInfo(state="ANONYMOUS", sessionId=None),
            session_expires_at=None,
            transcript=None,
            assistant_message=None,
            spoken_summary=None,
            result_block=None,
            trust_evidence=None,
            error=SafeErrorDetail(
                code="VOICE_PIPELINE_NOT_READY",
                message="Voice processing is not connected yet. Please try again when the service is ready.",
                retryable=False,
            ),
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=unavailable_envelope.model_dump(),
            headers={"X-Request-Id": request_id, "Cache-Control": "no-store"},
        )

    # 7. Execute real STT and VAD pipeline
    stt_result = await stt_port.transcribe(audio_metadata, bytes(audio_buffer), clean_turn_id)

    if stt_result.error_message == "NO_SPEECH_DETECTED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No speech detected in audio file. Please speak clearly into the microphone.",
        )

    if stt_result.error_message and stt_result.error_message.startswith("DECODE_ERROR"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio decoding failed: {stt_result.error_message}",
        )

    if stt_result.transcript is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech transcription failed: {stt_result.error_message or 'Unknown STT error'}",
        )

    # Plan from the final transcript before any biometric call. Clear public
    # requests and unsupported commands never consume Detectif credits.
    transcript_text = stt_result.transcript or ""
    store = IdentityMappingStore.get_instance()
    existing_for_plan = store.get_session(session_id.strip()) if session_id and session_id.strip() else None
    selected_claim = candidate_employee_id.strip().upper() if candidate_employee_id and candidate_employee_id.strip() else None
    if existing_for_plan and existing_for_plan.is_valid and selected_claim and selected_claim != existing_for_plan.employee_id:
        store.revoke_session(existing_for_plan.session_id)
        conversation_store.clear(existing_for_plan.session_id)
        raise HTTPException(status_code=400, detail="Caller identity claim conflict: selected employee does not match the active session.")
    explicit_self_claim = re.search(
        r"\b(?:i am|i'm|my employee id is|my id is|log me in as)\b.{0,55}?\b((?:EMP|RND|EXE)[-_]?\d{4})\b",
        transcript_text, re.I,
    )
    if explicit_self_claim and selected_claim and explicit_self_claim.group(1).upper().replace("_", "-") != selected_claim:
        if existing_for_plan and existing_for_plan.is_valid:
            store.revoke_session(existing_for_plan.session_id)
            conversation_store.clear(existing_for_plan.session_id)
        raise HTTPException(status_code=400, detail="Spoken identity claim conflicts with the selected identity.")
    plan_state = conversation_store.get(existing_for_plan.session_id, existing_for_plan.employee_id) if existing_for_plan and existing_for_plan.is_valid else None
    intent_plan = parse_local(transcript_text, plan_state)
    if intent_plan.operation == "clarify" and hasattr(ans_port, "plan_request"):
        proposed = await ans_port.plan_request(transcript_text, bool(plan_state and plan_state.active_id))
        if proposed:
            intent_plan = proposed
    if intent_plan.operation in ("help", "clarify"):
        public_text = (
            "I can show your profile, permitted direct reports, reporting tree, and scoped tickets. "
            "You can ask for a ticket chart or switch an authorized result to a table."
            if intent_plan.operation == "help" else
            "Please ask for a profile, direct reports, reporting tree, or tickets, and include a specific target when needed."
        )
        public_block = block("PUBLIC_FAQ", "IntentLock help", {
            "question": "Supported requests", "answer": public_text,
            "category": "Help", "source_document": "IntentLock supported capabilities",
        }, sensitive=False)
        tts_result = await tts_port.synthesize(public_text, clean_turn_id)
        audio_payload = None
        if tts_result.audio_bytes:
            dur_ms = (len(tts_result.audio_bytes) - 44) / (24000.0 * 2.0) * 1000.0
            audio_payload = SpokenAudioPayload(
                mime_type="audio/wav",
                sample_rate=24000,
                channels=1,
                byte_count=len(tts_result.audio_bytes),
                base64_audio=base64.b64encode(tts_result.audio_bytes).decode("ascii"),
                duration_ms=round(dur_ms, 1),
            )
        response = VoiceTurnResponse(
            request_id=request_id, client_turn_id=clean_turn_id, status="success",
            transcript=transcript_text, assistant_message=public_text, spoken_summary=public_text,
            speech_audio=audio_payload,
            speech_timings_ms={"stt_ms": stt_result.latency_ms or 0.0, "tts_ms": tts_result.latency_ms or 0.0},
            result_block=public_block, result_blocks=[public_block],
            primary_result_id=public_block.id,
            session=TurnSessionInfo(state="VERIFIED", sessionId=existing_for_plan.session_id,
                actor=SessionActor(employeeId=existing_for_plan.employee_id, fullName=existing_for_plan.full_name,
                    role=existing_for_plan.role, department=existing_for_plan.department,
                    teamId=existing_for_plan.team_id, expiresInSeconds=existing_for_plan.seconds_remaining))
                if existing_for_plan and existing_for_plan.is_valid else TurnSessionInfo(),
            session_expires_at=existing_for_plan.expires_at if existing_for_plan and existing_for_plan.is_valid else None,
        )
        return JSONResponse(status_code=200, content=response.model_dump(), headers={"Cache-Control": "no-store"})
    reusing_result = bool((plan_state and plan_state.active_id and intent_plan.operation in ("rechart", "back")) or
                          (existing_for_plan and existing_for_plan.is_valid and intent_plan.operation == "cancel"))
    if not reusing_result and stt_result.speech_duration_s is not None and stt_result.speech_duration_s < 4.2:
        guidance = "Please speak a full request for at least five seconds so I can verify the voice evidence."
        tts_result = await tts_port.synthesize(guidance, clean_turn_id)
        audio_payload = None
        if tts_result.audio_bytes:
            dur_ms = (len(tts_result.audio_bytes) - 44) / (24000.0 * 2.0) * 1000.0
            audio_payload = SpokenAudioPayload(
                mime_type="audio/wav",
                sample_rate=24000,
                channels=1,
                byte_count=len(tts_result.audio_bytes),
                base64_audio=base64.b64encode(tts_result.audio_bytes).decode("ascii"),
                duration_ms=round(dur_ms, 1),
            )
        response = VoiceTurnResponse(request_id=request_id, client_turn_id=clean_turn_id,
            status="clarification", transcript=transcript_text, assistant_message=guidance,
            spoken_summary=guidance, speech_audio=audio_payload,
            speech_timings_ms={"stt_ms": stt_result.latency_ms or 0.0, "tts_ms": tts_result.latency_ms or 0.0},
            session=TurnSessionInfo(state="VERIFIED", sessionId=existing_for_plan.session_id,
                actor=SessionActor(employeeId=existing_for_plan.employee_id, fullName=existing_for_plan.full_name,
                    role=existing_for_plan.role, department=existing_for_plan.department,
                    teamId=existing_for_plan.team_id, expiresInSeconds=existing_for_plan.seconds_remaining))
                if existing_for_plan and existing_for_plan.is_valid else TurnSessionInfo(),
            session_expires_at=existing_for_plan.expires_at if existing_for_plan and existing_for_plan.is_valid else None)
        return JSONResponse(status_code=200, content=response.model_dump(), headers={"Cache-Control": "no-store"})

    # 8. Extract or resolve candidate employee ID and enforce claim consistency
    claimed_id: Optional[str] = None
    existing_sess = None
    if session_id and session_id.strip():
        existing_sess = IdentityMappingStore.get_instance().get_session(session_id.strip())
        if existing_sess:
            if not existing_sess.is_valid:
                # Session is expired or revoked
                IdentityMappingStore.get_instance().revoke_session(session_id.strip())
                existing_sess = None
            elif candidate_employee_id and candidate_employee_id.strip().upper() != existing_sess.employee_id:
                # Claim Conflict! Prevent caller A from asserting identity B on active session
                logger.warning(
                    f"Claim conflict on turn [{clean_turn_id}]: session={existing_sess.employee_id} vs candidate={candidate_employee_id}"
                )
                IdentityMappingStore.get_instance().revoke_session(session_id.strip())
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Caller identity claim conflict: candidate employee ID does not match active session identity.",
                )
            else:
                claimed_id = existing_sess.employee_id

    if not claimed_id and candidate_employee_id and candidate_employee_id.strip():
        claimed_id = candidate_employee_id.strip().upper()

    # An employee ID mentioned as a requested target is not an actor claim.
    self_claim = explicit_self_claim
    if self_claim:
        spoken_claim = self_claim.group(1).upper().replace("_", "-")
        if claimed_id and spoken_claim != claimed_id:
            if existing_sess and existing_sess.is_valid:
                store.revoke_session(existing_sess.session_id)
                conversation_store.clear(existing_sess.session_id)
            raise HTTPException(status_code=400, detail="Spoken identity claim conflicts with the selected or active identity.")
        claimed_id = spoken_claim

    # 9. Voice Evidence & Scoped Authorization Orchestration
    scoped_auth = ScopedAuthorizationService.get_instance()
    mapping = store.get_mapping_by_employee_id(claimed_id) if claimed_id else None

    turn_status: str = "unverified"
    turn_session = TurnSessionInfo(state="ANONYMOUS", sessionId=None)
    session_expires_at: Optional[str] = None
    result_block = None
    trust_evidence = None
    voice_timings_ms: Dict[str, float] = {}

    if claimed_id and mapping and mapping.enrollment_status == "ENROLLED":
        # A valid existing result can be reformatted or revisited without new
        # biometric evidence. Any new private read still requires fresh evidence.
        reuse_snapshot = bool(existing_sess and existing_sess.is_valid and
                              ((plan_state and intent_plan.operation in ("rechart", "back")) or intent_plan.operation == "cancel"))
        voice_res = VoiceEvidenceResult() if reuse_snapshot else await voice_port.verify_evidence(
            audio_metadata=audio_metadata, audio_bytes=bytes(audio_buffer),
            candidate_speaker_id=mapping.provider_speaker_id, correlation_id=clean_turn_id,
        )
        if voice_res.latency_ms:
            voice_timings_ms["detectif_ms"] = voice_res.latency_ms

        provider_identity_ok = reuse_snapshot or (
            voice_res.speaker_id == mapping.provider_speaker_id
            and (not voice_res.account_alias or voice_res.account_alias == mapping.account_alias)
        )
        logger.info("voice_trace %s", json.dumps({
            "turn_id": clean_turn_id, "request_id": request_id,
            "selected_candidate": selected_claim, "spoken_self_claim": self_claim.group(1).upper() if self_claim else None,
            "session_actor": existing_sess.employee_id if existing_sess and existing_sess.is_valid else None,
            "mapped_speaker": mapping.provider_speaker_id, "mapped_account": mapping.account_alias,
            "audio_digest": sha256_digest, "provider_request_id": voice_res.request_id,
            "provider_model": voice_res.model_version, "provider_speaker": voice_res.speaker_id,
            "provider_account": voice_res.account_alias, "speaker_decision": voice_res.decision,
            "speaker_score": voice_res.similarity_score, "speaker_threshold": voice_res.similarity_threshold,
            "authenticity_verdict": voice_res.deepfake_verdict, "deepfake_score": voice_res.deepfake_score,
            "deepfake_threshold": voice_res.deepfake_threshold, "provider_error": voice_res.error_code,
            "identity_correspondence": provider_identity_ok,
            "evidence_freshness": "reused_from_session" if reuse_snapshot else "fresh_this_turn",
            "operation": intent_plan.operation,
        }, sort_keys=True))
        if reuse_snapshot or (voice_res.is_dual_verified and provider_identity_ok):
            # Dual verification succeeded: MATCH + REAL
            know_svc = knowledge_service or EmployeeKnowledgeService.get_instance()
            emp_data = know_svc.get_employee_by_id(claimed_id) if know_svc else None
            full_name = emp_data["identity"]["full_name"] if emp_data else (mapping.display_name or claimed_id)
            role = emp_data["employment"]["designation"] if emp_data else "Employee"
            # Display role uses the frontend enum; policy still evaluates canonical records.
            app_role = {"EMP-1001": "employee", "EMP-2001": "manager", "EMP-4002": "executive"}.get(claimed_id, "employee")
            dept = emp_data["employment"]["department"] if emp_data else "General"
            team = emp_data["employment"].get("team") if emp_data else None

            # Issue or refresh server session (fixation resistant)
            if reuse_snapshot:
                session_rec = existing_sess
            elif session_id and existing_sess and existing_sess.is_valid and existing_sess.employee_id == claimed_id:
                session_rec = store.refresh_session(session_id, ttl_seconds=settings.SESSION_TTL_SECONDS)
                if not session_rec:
                    session_rec = store.create_session(
                        session_id=session_id,
                        employee_id=claimed_id,
                        full_name=full_name,
                        role=app_role,
                        department=dept,
                        team_id=team,
                        account_alias=mapping.account_alias,
                        ttl_seconds=settings.SESSION_TTL_SECONDS,
                    )
            else:
                new_session_id = f"sess_{uuid.uuid4().hex}"
                session_rec = store.create_session(
                    session_id=new_session_id,
                    employee_id=claimed_id,
                    full_name=full_name,
                    role=app_role,
                    department=dept,
                    team_id=team,
                    account_alias=mapping.account_alias,
                    ttl_seconds=settings.SESSION_TTL_SECONDS,
                )

            scoped_res = ConversationDispatcher(scoped_auth).dispatch(
                claimed_id, session_rec.session_id, intent_plan,
                spoken_text=transcript_text,
                evidence_digest=sha256_digest if not reuse_snapshot else "",
            )
            logger.info("voice_policy %s", json.dumps({
                "turn_id": clean_turn_id, "actor": claimed_id, "operation": intent_plan.operation,
                "target": intent_plan.ticket_id or (re.search(r"\b(?:EMP|RND|EXE)[-_]?\d{4}\b", intent_plan.entity or "", re.I).group(0).upper()
                    if re.search(r"\b(?:EMP|RND|EXE)[-_]?\d{4}\b", intent_plan.entity or "", re.I) else None),
                "authorized": scoped_res.is_authorized,
                "renderer": scoped_res.result_block.type if scoped_res.result_block else None,
            }, sort_keys=True))

            turn_status = "success" if scoped_res.is_authorized else "denied"
            turn_session = TurnSessionInfo(
                state="VERIFIED",
                sessionId=session_rec.session_id,
                actor=SessionActor(
                    employeeId=claimed_id,
                    fullName=full_name,
                    role=app_role,
                    designation=role,
                    department=dept,
                    teamId=team,
                    expiresInSeconds=session_rec.seconds_remaining,
                ),
            )
            session_expires_at = session_rec.expires_at
            result_block = scoped_res.result_block
            spoken_summary = scoped_res.spoken_summary
            safe_reply = scoped_res.spoken_summary

            # The deterministic dispatcher owns the spoken factual summary.
            # A generative answer cannot replace a denial or change its scope.

            trust_evidence = TrustEvidence(
                freshness="reused_from_session" if reuse_snapshot else "fresh_this_turn",
                reason="authorized_result_navigation" if reuse_snapshot else "new_private_read_or_action",
                speaker_decision="match" if not reuse_snapshot else None,
                similarity_score=voice_res.similarity_score,
                similarity_threshold=voice_res.similarity_threshold,
                authenticity_verdict="real" if not reuse_snapshot else None,
                deepfake_score=voice_res.deepfake_score,
                deepfake_threshold=voice_res.deepfake_threshold,
                speaker_id=voice_res.speaker_id if not reuse_snapshot else mapping.provider_speaker_id,
                is_dual_verified=True,
                timestamp=datetime.now(timezone.utc).isoformat() if not reuse_snapshot else existing_sess.last_verified_at,
            )

        else:
            # Dual verification failed: no_match, fake, not_sure, or provider error
            if session_id:
                store.revoke_session(session_id)
                conversation_store.clear(session_id)

            turn_status = "denied"
            turn_session = TurnSessionInfo(state="ANONYMOUS", sessionId=None)
            if voice_res.deepfake_verdict == "fake":
                denial_reason = "Voice authentication denied: provider classified this recording as synthetic audio."
            elif voice_res.deepfake_verdict == "not_sure":
                denial_reason = "Voice authenticity was inconclusive. Please try a clear full phrase."
            elif voice_res.is_dual_verified and not provider_identity_ok:
                denial_reason = "Voice verification returned inconsistent speaker or account evidence."
            elif voice_res.decision == "no_match":
                denial_reason = f"Voice authentication denied: speaker does not match enrolled profile for {claimed_id}."
            elif voice_res.error_code:
                denial_reason = f"Voice authentication service unavailable: {voice_res.error_message}"
            else:
                denial_reason = "Voice verification failed dual biometric authenticity requirements."

            result_block = scoped_auth.build_denial_result_block(denial_reason, claimed_id)
            spoken_summary = denial_reason
            safe_reply = denial_reason
            trust_evidence = TrustEvidence(
                freshness="fresh_this_turn",
                reason="verification_failed",
                speaker_decision=voice_res.decision,
                similarity_score=voice_res.similarity_score,
                similarity_threshold=voice_res.similarity_threshold,
                authenticity_verdict=voice_res.deepfake_verdict,
                deepfake_score=voice_res.deepfake_score,
                deepfake_threshold=voice_res.deepfake_threshold,
                speaker_id=voice_res.speaker_id,
                is_dual_verified=False,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    elif claimed_id:
        # Candidate ID was claimed, but no active enrollment exists in Detectif
        turn_status = "unverified"
        turn_session = TurnSessionInfo(state="ANONYMOUS", sessionId=None)
        denial_reason = f"Employee {claimed_id} is not enrolled in Detectif voice verification. Access to private records remains restricted."
        result_block = scoped_auth.build_denial_result_block(denial_reason, claimed_id)
        spoken_summary = denial_reason
        safe_reply = denial_reason
        trust_evidence = None

    else:
        # Anonymous public question
        turn_status = "unverified"
        turn_session = TurnSessionInfo(state="ANONYMOUS", sessionId=None)
        safe_reply = (
            f"I received your question: \"{stt_result.transcript}\". "
            "To access your private employee profile or tickets, please state your employee ID for Detectif voice verification."
        )
        spoken_summary = safe_reply
        result_block = None
        trust_evidence = None

    # 10. Execute real TTS synthesis
    tts_result = await tts_port.synthesize(spoken_summary, clean_turn_id)
    spoken_payload = None
    if tts_result.audio_bytes:
        b64_audio = base64.b64encode(tts_result.audio_bytes).decode("ascii")
        duration_ms = (len(tts_result.audio_bytes) - 44) / (24000.0 * 2.0) * 1000.0
        spoken_payload = SpokenAudioPayload(
            mime_type="audio/wav",
            sample_rate=24000,
            channels=1,
            byte_count=len(tts_result.audio_bytes),
            base64_audio=b64_audio,
            duration_ms=round(duration_ms, 1),
        )

    # 11. Assemble complete VoiceTurnResponse
    timings = {
        "stt_ms": stt_result.latency_ms or 0.0,
        "tts_ms": tts_result.latency_ms or 0.0,
    }
    timings.update(voice_timings_ms)

    turn_response = VoiceTurnResponse(
        api_version="1",
        request_id=request_id,
        client_turn_id=clean_turn_id,
        status=turn_status,
        session=turn_session,
        session_expires_at=session_expires_at,
        transcript=stt_result.transcript,
        assistant_message=safe_reply,
        spoken_summary=spoken_summary,
        speech_audio=spoken_payload,
        speech_timings_ms=timings,
        result_block=result_block,
        result_blocks=[result_block] if result_block else [],
        primary_result_id=result_block.id if result_block else None,
        trust_evidence=trust_evidence,
        error=None,
    )

    replay_store.save_idempotency_record(replay_key, sha256_digest, claimed_id or "", turn_response.model_dump())

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=turn_response.model_dump(),
        headers={"X-Request-Id": request_id, "Cache-Control": "no-store"},
    )


# =============================================================================
# Voice Session Management Endpoints
# =============================================================================

class ResultActionRequest(BaseModel):
    action: str = Field(max_length=32)
    source_result_id: str = Field(max_length=96)
    target_id: Optional[str] = Field(default=None, max_length=32)
    view: Optional[str] = Field(default=None, max_length=16)
    group_by: Optional[str] = Field(default=None, max_length=16)


@app.post(f"{settings.API_V1_PREFIX}/voice/result-action", tags=["Voice Gateway"])
def process_result_action(action: ResultActionRequest, auth: Dict[str, Any] = Depends(require_verified_session)):
    """Click actions may revisit delivered data but cannot introduce private scope."""
    state = conversation_store.get(auth["session_id"], auth["employee_id"])
    source = state.snapshots.get(action.source_result_id)
    if not source:
        raise HTTPException(status_code=403, detail="The selected result is no longer available in this session.")
    state.active_id = source.block.id
    if action.action == "open_profile":
        if not action.target_id or action.target_id not in source.visible_ids:
            raise HTTPException(status_code=403, detail="The selected person is outside this result.")
        cached = next((snapshot for snapshot in state.snapshots.values()
                       if snapshot.block.type == "EMPLOYEE_PROFILE" and
                       snapshot.visible_ids == [action.target_id]), None)
        if not cached:
            return JSONResponse(status_code=409, content={
                "status": "verification_required",
                "assistant_message": "Please ask for this person's details by voice so the new private fields can be verified.",
            })
        result = cached.block
        state.remember(cached)
        return {"status": "success", "assistant_message": f"Showing {result.title}.", "result_block": result.model_dump()}
    if action.action == "rechart":
        if action.view not in ("TABLE", "BAR", "PIE", "LINE", "AREA") or action.group_by not in (None, "priority", "status"):
            raise HTTPException(status_code=400, detail="Unsupported view or grouping.")
        result = ConversationDispatcher().dispatch(auth["employee_id"], auth["session_id"],
            IntentPlan(operation="rechart", view=action.view, group_by=action.group_by))
        if not result.is_authorized or not result.result_block:
            raise HTTPException(status_code=403, detail=result.spoken_summary)
        return {"status": "success", "assistant_message": result.spoken_summary,
                "result_block": result.result_block.model_dump()}
    if action.action == "select_ticket":
        if not action.target_id or action.target_id not in source.visible_ids:
            raise HTTPException(status_code=403, detail="The selected ticket is outside this result.")
        state.selected_ticket_id = action.target_id
        return {
            "status": "success",
            "assistant_message": f"Selected ticket {action.target_id}. You can ask to view, update, or comment on this ticket.",
            "selected_ticket_id": action.target_id,
        }
    raise HTTPException(status_code=400, detail="Unsupported result action.")

@app.post(
    f"{settings.API_V1_PREFIX}/voice/session/end",
    tags=["Voice Gateway"],
)
def end_voice_session(
    session_id: Optional[str] = Form(None),
    request: Request = None,
):
    """Explicitly terminate and purge an active voice session."""
    store = IdentityMappingStore.get_instance()
    token = session_id
    if not token and request:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
        elif "X-Session-Token" in request.headers:
            token = request.headers.get("X-Session-Token", "").strip()
        elif "X-Session-Id" in request.headers:
            token = request.headers.get("X-Session-Id", "").strip()
    if token:
        store.revoke_session(token)
        conversation_store.clear(token)
    return {
        "status": "session_terminated",
        "session": {"state": "ANONYMOUS", "sessionId": None},
        "message": "Session explicitly terminated. All private context wiped.",
    }


# =============================================================================
# Knowledge Query Endpoint (Gated, Rejects Untrusted Client Claims)
# =============================================================================

@app.post(
    f"{settings.API_V1_PREFIX}/knowledge/query",
    response_model=KnowledgeQueryResponse,
    tags=["Knowledge"],
)
def query_employee_knowledge(req: KnowledgeQueryRequest):
    """
    Query employee/company knowledge.
    Gated centrally: client-authored authority claims are rejected.
    In Stage 1 & 2 without verified voice sessions, all private employee queries fail closed.
    """
    # 1. Detect and reject client-asserted privilege elevation
    AuthorizationPolicyFacade.reject_untrusted_client_claims(
        actor_id=req.actor_id,
        actor_role=req.actor_role,
        is_authenticated=req.is_authenticated,
    )

    # 2. Unauthenticated calls fail closed
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Unauthenticated access to the employee knowledge base is denied. Voice verification required via /api/v1/voice/turn.",
    )


# =============================================================================
# Direct Employee Directory Endpoints (Protected & Gated)
# =============================================================================

@app.get(f"{settings.API_V1_PREFIX}/employees/me", tags=["Employees"])
def get_current_employee_profile(
    _auth: Dict[str, Any] = Depends(require_verified_session),
):
    """Retrieve the authenticated caller's own scoped profile."""
    scoped_service = ScopedAuthorizationService.get_instance()
    res = scoped_service.evaluate_and_get_profile(actor_id=_auth["employee_id"])
    if not res.is_authorized or not res.result_block:
        raise HTTPException(status_code=res.status_code, detail=res.denial_reason)
    return {"employee": res.result_block.payload.get("employee", {})}


@app.get(f"{settings.API_V1_PREFIX}/employees", tags=["Employees"])
def list_employees(
    department: Optional[str] = Query(None, description="Filter by department"),
    role: Optional[str] = Query(None, description="Filter by designation keyword"),
    limit: int = Query(50, ge=1, le=100),
    _auth: Dict[str, Any] = Depends(require_verified_session),
):
    """List employees. Protected: requires active verified session."""
    return {"total": 0, "employees": []}


@app.get(f"{settings.API_V1_PREFIX}/employees/search", tags=["Employees"])
def search_employees(
    q: str = Query(..., min_length=1, description="Search query"),
    _auth: Dict[str, Any] = Depends(require_verified_session),
):
    """Search employees. Protected: requires active verified session."""
    return {"query": q, "count": 0, "results": []}


@app.get(f"{settings.API_V1_PREFIX}/employees/{{employee_id}}", tags=["Employees"])
def get_employee(
    employee_id: str,
    _auth: Dict[str, Any] = Depends(require_verified_session),
):
    """Retrieve detailed employee profile with authoritative scope evaluation."""
    scoped_service = ScopedAuthorizationService.get_instance()
    res = scoped_service.evaluate_and_get_profile(actor_id=_auth["employee_id"], target_id=employee_id)
    if not res.is_authorized:
        return JSONResponse(
            status_code=res.status_code,
            content=res.result_block.model_dump() if res.result_block else {"error": res.denial_reason},
        )
    return {"employee": res.result_block.payload.get("employee", {})}


@app.get(f"{settings.API_V1_PREFIX}/employees/{{employee_id}}/reporting", tags=["Employees"])
def get_employee_reporting_tree(
    employee_id: str,
    _auth: Dict[str, Any] = Depends(require_verified_session),
):
    """Retrieve employee reporting tree. Protected: requires active verified session."""
    return {}


# =============================================================================
# Direct Ticket Endpoints (Protected & Gated)
# =============================================================================

@app.get(f"{settings.API_V1_PREFIX}/tickets", tags=["Tickets"])
def list_scoped_tickets(
    status: Optional[str] = Query(None, description="Filter by status"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    q: Optional[str] = Query(None, description="Freeform query keyword"),
    _auth: Dict[str, Any] = Depends(require_verified_session),
):
    """Retrieve tickets authorized for the active authenticated session."""
    scoped_service = ScopedAuthorizationService.get_instance()
    query_str = q or status or priority
    res = scoped_service.evaluate_and_get_tickets(actor_id=_auth["employee_id"], query=query_str)
    if not res.is_authorized or not res.result_block:
        raise HTTPException(status_code=res.status_code, detail=res.denial_reason)
    return res.result_block.payload


@app.get(f"{settings.API_V1_PREFIX}/tickets/{{ticket_id}}", tags=["Tickets"])
def get_scoped_ticket(
    ticket_id: str,
    _auth: Dict[str, Any] = Depends(require_verified_session),
):
    """Retrieve single ticket with authoritative scope verification."""
    scoped_service = ScopedAuthorizationService.get_instance()
    res = scoped_service.evaluate_and_get_tickets(actor_id=_auth["employee_id"], query=ticket_id)
    if not res.is_authorized:
        return JSONResponse(
            status_code=res.status_code,
            content=res.result_block.model_dump() if res.result_block else {"error": res.denial_reason},
        )
    return res.result_block.payload


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
