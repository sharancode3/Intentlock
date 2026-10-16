"""
IntentLock — Local Voice & Render Testing Gateway
Provides the isolated local test composition for downstream voice-and-render testing:
microphone input -> real VAD/STT -> left user transcript -> scoped dataset retrieval
-> local model -> left assistant reply text -> right visual result -> actual TTS/playback.

SECURITY & ARCHITECTURAL INVARIANTS:
- Isolated test application; does not weaken or alter production verification in backend/main.py.
- Binds strictly to loopback (127.0.0.1) with explicit allowed origins.
- Resolves test contexts strictly server-side from allowlisted fixture IDs.
- Never accepts arbitrary client actor roles or claimed biometric scores.
- Never mints a production token; marks all responses with test_mode=True.
- Reuses existing canonical EmployeeKnowledgeService, EmployeeVisibilityService, and Ollama.
"""

import os
import base64
import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.core.config import settings
from backend.services.employee_knowledge_service import EmployeeKnowledgeService
from backend.services.employee_visibility_service import EmployeeVisibilityService
from backend.services.ollama_knowledge_service import OllamaKnowledgeService

from backend.test_integration.test_actor_contexts import (
    TestActorContext,
    ALLOWLISTED_TEST_CONTEXTS,
    resolve_test_actor,
)
from backend.test_integration.test_speech_service import (
    transcribe_audio_bytes,
    synthesize_speech,
    get_whisper_model,
    get_kokoro_model,
)
from backend.test_integration.test_result_builder import build_result_block_for_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_gateway")

# Global services
knowledge_service: Optional[EmployeeKnowledgeService] = None
ollama_service: Optional[OllamaKnowledgeService] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global knowledge_service, ollama_service
    logger.info("Initializing IntentLock Local Render Test Gateway...")
    knowledge_service = EmployeeKnowledgeService.get_instance(data_path=settings.DATA_PATH)
    ollama_service = OllamaKnowledgeService(
        knowledge_service=knowledge_service,
        base_url=settings.OLLAMA_BASE_URL,
        model="qwen2.5:3b",  # Exact installed model
        timeout=25.0,
    )
    # Pre-warm speech models in background thread
    logger.info("Pre-warming Faster-Whisper and Kokoro models...")
    try:
        get_whisper_model()
        get_kokoro_model()
    except Exception as e:
        logger.warning(f"Error warming speech models: {e}")
    logger.info("Render Test Gateway ready.")
    yield
    logger.info("Shutting down Render Test Gateway.")

test_app = FastAPI(
    title="IntentLock Local Voice & Render Test Gateway",
    version="1.0.0-test",
    description="Isolated loopback testing service for post-verification voice and render verification.",
    lifespan=lifespan,
)

# Strict loopback CORS
test_app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TextTurnRequest(BaseModel):
    text: str
    fixture_id: Optional[str] = "employee_self"
    conversation_id: Optional[str] = None
    turn_id: Optional[str] = None

class TurnResponse(BaseModel):
    turn_id: str
    conversation_id: str
    fixture_id: str
    actor_context: Dict[str, Any]
    user_transcript: str
    assistant_text: str
    result_block: Dict[str, Any]
    tts_audio_base64: str
    audio_mime_type: str
    test_mode: bool = True
    security_notice: str = "Local render test — Detectif verification not run"

@test_app.get("/api/test/health", tags=["Health"])
def test_health():
    """Health check for local render test services."""
    svc = EmployeeKnowledgeService.get_instance()
    emps = len(svc.list_all_employees())
    whisper_ready = get_whisper_model() is not None
    kokoro_ready = get_kokoro_model() is not None

    return {
        "status": "HEALTHY",
        "test_mode": True,
        "security_notice": "Local render test — Detectif verification not run",
        "indexed_employees": emps,
        "whisper_ready": whisper_ready,
        "kokoro_ready": kokoro_ready,
        "ollama_model": "qwen2.5:3b",
    }

@test_app.get("/api/test/fixtures", tags=["Fixtures"])
def list_test_fixtures():
    """List available bounded fictional actor contexts for testing."""
    return {
        "fixtures": [
            {
                "fixture_id": ctx.fixture_id,
                "employee_id": ctx.employee_id,
                "full_name": ctx.full_name,
                "role": ctx.role,
                "department": ctx.department,
                "scope_description": ctx.scope_description,
                "can_view_team": ctx.can_view_team,
                "can_view_all": ctx.can_view_all,
            }
            for ctx in ALLOWLISTED_TEST_CONTEXTS.values()
        ]
    }

def process_turn_intent(
    query_text: str,
    actor: TestActorContext,
    turn_id: str,
    conversation_id: str,
) -> TurnResponse:
    """
    Core business logic processing finalized user query:
    1. Scope enforcement
    2. Canonical retrieval
    3. Ollama generation
    4. Deterministic ResultBlock construction
    5. Kokoro neural TTS synthesis
    """
    global ollama_service
    svc = ollama_service or OllamaKnowledgeService(model="qwen2.5:3b", timeout=25.0)

    q_clean = query_text.strip()
    if not q_clean:
        q_clean = "(Silence or unvoiced input)"

    # Check for forbidden cross-scope requests
    q_lower = q_clean.lower()
    is_denied = False
    denial_reason = None

    # Anonymous visitor attempting to query private employee files
    if actor.role == "anonymous":
        if any(w in q_lower for w in ["employee", "salary", "who is", "profile", "report", "project", "aarav", "priya", "team"]):
            is_denied = True
            denial_reason = "Anonymous visitors cannot query private employee or team records."

    # Employee attempting to view forbidden other employee's private profile or team records
    elif actor.fixture_id == "employee_self":
        # Can only view own info (Aarav EMP-1001) or general public info
        if any(w in q_lower for w in ["who reports to", "team of", "direct reports", "salary", "bonus", "performance"]):
            is_denied = True
            denial_reason = f"Employee {actor.full_name} ({actor.employee_id}) does not have manager authorization to view team reporting or performance data."
        elif any(name in q_lower for name in ["priya", "vikram", "ishaan", "arvind", "kavya", "rahul"]):
            # If asking about others while in self-scope
            if "priya" in q_lower and ("report" in q_lower or "manager" in q_lower):
                pass  # Asking who their own manager is is permitted
            elif not any(w in q_lower for w in ["who is", "public"]):
                is_denied = True
                denial_reason = f"Access to private records for other employees is restricted for your employee scope ({actor.full_name})."

    # Manager attempting to access cross-department director/exec records
    elif actor.fixture_id == "manager_team":
        if any(w in q_lower for w in ["executive compensation", "ceo salary", "cto private", "board minutes"]):
            is_denied = True
            denial_reason = f"Manager {actor.full_name} ({actor.employee_id}) is restricted to Engineering Team scope."

    if is_denied:
        answer_text = (
            f"Access Denied: {denial_reason} "
            f"Your current test profile is {actor.full_name} ({actor.employee_id}, {actor.scope_description})."
        )
        retrieved_emps: List[Dict[str, Any]] = []
    else:
        # Retrieve through canonical knowledge service
        is_auth = actor.role != "anonymous"
        retrieved_emps, filters = svc.interpret_and_retrieve(
            query=q_clean,
            actor_id=actor.employee_id if is_auth else None,
            actor_role=actor.role if is_auth else None,
            is_authenticated=is_auth,
        )

        # Enforce scope filtering: non-executives can only view permitted IDs
        if actor.permitted_employee_ids is not None:
            retrieved_emps = [
                e for e in retrieved_emps
                if e.get("employee_id") in actor.permitted_employee_ids
            ]

        # Call Ollama for factual grounded answer
        try:
            ollama_res = svc.answer_query(
                query=q_clean,
                actor_id=actor.employee_id if is_auth else None,
                actor_role=actor.role if is_auth else None,
                is_authenticated=is_auth,
            )
            answer_text = ollama_res.get("answer", "")
        except Exception as e:
            logger.warning(f"Ollama generation fallback: {e}")
            # Factual grounded fallback from retrieved records
            if retrieved_emps:
                names = [e["identity"]["full_name"] for e in retrieved_emps]
                answer_text = f"Found {len(retrieved_emps)} employee(s) within your permitted scope: {', '.join(names)}."
            else:
                answer_text = "I do not have record of that information within your permitted scope."

    # Build typed visual ResultBlock
    result_block = build_result_block_for_query(
        query=q_clean,
        actor=actor,
        retrieved_employees=retrieved_emps,
        answer_text=answer_text,
        is_denied=is_denied,
        denial_reason=denial_reason,
    )

    # Synthesize real Kokoro neural speech
    wav_bytes, mime = synthesize_speech(answer_text, voice="af_sarah")
    b64_audio = base64.b64encode(wav_bytes).decode("ascii")

    return TurnResponse(
        turn_id=turn_id,
        conversation_id=conversation_id,
        fixture_id=actor.fixture_id,
        actor_context=actor.model_dump(),
        user_transcript=q_clean,
        assistant_text=answer_text,
        result_block=result_block,
        tts_audio_base64=b64_audio,
        audio_mime_type=mime,
        test_mode=True,
        security_notice="Local render test — Detectif verification not run",
    )

@test_app.post("/api/test/turn/audio", response_model=TurnResponse, tags=["Turn"])
async def handle_audio_turn(
    audio_file: UploadFile = File(...),
    fixture_id: str = Form("employee_self"),
    conversation_id: Optional[str] = Form(None),
    turn_id: Optional[str] = Form(None),
):
    """
    Real voice turn processing:
    1. Reads uploaded audio container (WebM/Opus or WAV).
    2. Transcribes with Faster-Whisper (Silero VAD filtered).
    3. Queries canonical employee dataset with server-bound TestActorContext.
    4. Generates grounded answer via local Ollama.
    5. Returns typed ResultBlock for contextual right pane.
    6. Synthesizes real neural audio via Kokoro ONNX for playback.
    """
    raw_audio = await audio_file.read()
    if not raw_audio:
        raise HTTPException(status_code=400, detail="Empty audio buffer received.")

    t_id = turn_id or f"turn-{int(os.times().system * 1000)}"
    c_id = conversation_id or "conv-local-test"

    actor = resolve_test_actor(fixture_id)

    # Real Faster-Whisper transcription
    transcript = transcribe_audio_bytes(raw_audio)
    if not transcript:
        transcript = "(No speech detected or utterance was below audio threshold)"

    return process_turn_intent(
        query_text=transcript,
        actor=actor,
        turn_id=t_id,
        conversation_id=c_id,
    )

@test_app.post("/api/test/turn/text", response_model=TurnResponse, tags=["Turn"])
def handle_text_turn(req: TextTurnRequest):
    """
    Direct typed text input testing (supporting keyboard users and test automation).
    """
    t_id = req.turn_id or f"turn-{int(os.times().system * 1000)}"
    c_id = req.conversation_id or "conv-local-test"
    actor = resolve_test_actor(req.fixture_id)

    return process_turn_intent(
        query_text=req.text,
        actor=actor,
        turn_id=t_id,
        conversation_id=c_id,
    )

@test_app.post("/api/test/tts", tags=["TTS"])
def handle_tts_synthesis(text: str = Form(...), voice: str = Form("af_sarah")):
    """Direct TTS generation endpoint returning base64 WAV."""
    wav_bytes, mime = synthesize_speech(text, voice=voice)
    b64 = base64.b64encode(wav_bytes).decode("ascii")
    return {
        "audio_base64": b64,
        "mime_type": mime,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.test_integration.test_gateway:test_app", host="127.0.0.1", port=8001, reload=False)
