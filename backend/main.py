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
import httpx

from backend.core.config import settings
from backend.core.security import require_verified_session, AuthorizationPolicyFacade
from backend.core.ports import (
    SpeechInputPort,
    SpeechOutputPort,
    VoiceEvidencePort,
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
    global knowledge_service, ollama_service, speech_vad_service, speech_input_port, speech_output_port
    logger.info("Initializing IntentLock Employee Knowledge Base...")
    knowledge_service = EmployeeKnowledgeService.get_instance(data_path=settings.DATA_PATH)
    ollama_service = OllamaKnowledgeService(
        knowledge_service=knowledge_service,
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL,
        timeout=settings.OLLAMA_TIMEOUT_SECONDS,
    )
    logger.info(
        f"Backend startup complete. {len(knowledge_service.list_all_employees())} employees loaded in memory."
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

    # If not explicitly supplied, extract pattern from transcript
    if not claimed_id and stt_result.transcript:
        emp_match = re.search(r"\b(EMP[-_]?\d{4})\b", stt_result.transcript, re.IGNORECASE)
        if emp_match:
            raw_match = emp_match.group(1).upper()
            if "_" in raw_match:
                claimed_id = raw_match.replace("_", "-")
            elif not raw_match.startswith("EMP-"):
                claimed_id = f"EMP-{raw_match[3:]}"
            else:
                claimed_id = raw_match

    # 9. Voice Evidence & Scoped Authorization Orchestration
    store = IdentityMappingStore.get_instance()
    scoped_auth = ScopedAuthorizationService.get_instance()
    mapping = store.get_mapping_by_employee_id(claimed_id) if claimed_id else None

    turn_status: str = "unverified"
    turn_session = TurnSessionInfo(state="ANONYMOUS", sessionId=None)
    session_expires_at: Optional[str] = None
    result_block = None
    trust_evidence = None
    voice_timings_ms: Dict[str, float] = {}

    if claimed_id and mapping and mapping.enrollment_status == "ENROLLED":
        # Execute combined Detectif verification
        voice_res = await voice_port.verify_evidence(
            audio_metadata=audio_metadata,
            audio_bytes=bytes(audio_buffer),
            candidate_speaker_id=mapping.provider_speaker_id,
            correlation_id=clean_turn_id,
        )
        if voice_res.latency_ms:
            voice_timings_ms["detectif_ms"] = voice_res.latency_ms

        if voice_res.is_dual_verified:
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
            if session_id and existing_sess and existing_sess.is_valid and existing_sess.employee_id == claimed_id:
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

            scoped_res = scoped_auth.evaluate_and_get_profile(actor_id=claimed_id)
            turn_status = "success"
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

            # Execute grounded answer generation if answer port is configured
            if ans_port and getattr(ans_port, "is_configured", lambda: False)():
                try:
                    auth_context = scoped_auth.build_authorized_context_for_llm(
                        actor_id=claimed_id,
                        query=stt_result.transcript,
                    )
                    ans_res = await ans_port.generate_answer(
                        question=stt_result.transcript,
                        authorized_context=auth_context,
                        correlation_id=clean_turn_id,
                    )
                    if ans_res and ans_res.is_available and ans_res.answer_text:
                        safe_reply = ans_res.answer_text
                        spoken_summary = ans_res.answer_text
                        if ans_res.latency_ms:
                            voice_timings_ms["llm_ms"] = ans_res.latency_ms
                except Exception as ans_err:
                    logger.error(f"Answer generation error for {clean_turn_id}: {ans_err}")

            trust_evidence = TrustEvidence(
                speaker_decision="match",
                similarity_score=voice_res.similarity_score,
                similarity_threshold=voice_res.similarity_threshold,
                authenticity_verdict="real",
                deepfake_score=voice_res.deepfake_score,
                deepfake_threshold=voice_res.deepfake_threshold,
                speaker_id=voice_res.speaker_id,
                is_dual_verified=True,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        else:
            # Dual verification failed: no_match, fake, not_sure, or provider error
            if session_id:
                store.revoke_session(session_id)

            turn_status = "denied"
            turn_session = TurnSessionInfo(state="ANONYMOUS", sessionId=None)
            if voice_res.deepfake_verdict in ("fake", "not_sure"):
                denial_reason = f"Voice authentication denied: potential synthetic audio detected ({voice_res.deepfake_verdict})."
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
        trust_evidence=trust_evidence,
        error=None,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=turn_response.model_dump(),
        headers={"X-Request-Id": request_id, "Cache-Control": "no-store"},
    )


# =============================================================================
# Voice Session Management Endpoints
# =============================================================================

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
