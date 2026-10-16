"""
IntentLock — Canonical Voice Turn Contract Models
Defines request metadata and response envelopes matching frontend types
and Stage 1 unavailable specifications.
"""

from typing import Optional, Dict, Any, Literal, List
from pydantic import BaseModel, Field
from backend.models.errors import SafeErrorDetail

SessionState = Literal["ANONYMOUS", "VERIFYING", "VERIFIED", "EXPIRED"]

ResultBlockType = Literal[
    "PUBLIC_FAQ",
    "EMPLOYEE_PROFILE",
    "TICKET_LIST",
    "TEAM_METRIC_CHART",
    "READBACK_CONFIRMATION",
    "DENIAL_BANNER",
    "ACTION_RECEIPT",
    "TRUST_TRACE_GRAPH",
    "PROTECTED_DOCUMENT_PREVIEW",
    "DATA_TABLE",
    "ORG_TREE",
]


class SessionActor(BaseModel):
    employeeId: str
    fullName: str
    role: str
    designation: Optional[str] = None
    department: str
    teamId: Optional[str] = None
    expiresInSeconds: Optional[int] = 90


class TurnSessionInfo(BaseModel):
    state: SessionState = "ANONYMOUS"
    sessionId: Optional[str] = None
    actor: Optional[SessionActor] = None


class GenericResultBlock(BaseModel):
    id: str
    type: ResultBlockType
    title: str
    timestamp: str
    isSensitive: bool = False
    payload: Dict[str, Any] = Field(default_factory=dict)


class TrustEvidence(BaseModel):
    freshness: Literal["fresh_this_turn", "reused_from_session", "not_required"] = "fresh_this_turn"
    reason: Optional[str] = None
    speaker_decision: Optional[str] = None  # "match" | "no_match"
    similarity_score: Optional[float] = None
    similarity_threshold: Optional[float] = None
    authenticity_verdict: Optional[str] = None  # "real" | "fake" | "not_sure"
    deepfake_score: Optional[float] = None
    deepfake_threshold: Optional[float] = None
    speaker_id: Optional[str] = None
    is_dual_verified: bool = False
    timestamp: Optional[str] = None


class SpokenAudioPayload(BaseModel):
    """Container for synthesized response audio delivered to client."""
    mime_type: str = "audio/wav"
    sample_rate: int = 24000
    channels: int = 1
    byte_count: int
    base64_audio: str
    duration_ms: Optional[float] = None


class VoiceTurnResponse(BaseModel):
    """
    Canonical envelope for POST /api/v1/voice/turn.
    Supports unavailable, unverified (speech active, Detectif unconfigured),
    verified success, and denied states.
    """
    api_version: str = Field("1", description="Contract API version")
    request_id: str = Field(..., description="Server-assigned correlation identifier")
    client_turn_id: str = Field(..., description="Client correlation turn ID preserved across retries")
    status: Literal["unavailable", "success", "error", "unverified", "denied", "clarification"] = "unavailable"
    session: TurnSessionInfo = Field(default_factory=TurnSessionInfo)
    session_expires_at: Optional[str] = None
    transcript: Optional[str] = None
    assistant_message: Optional[str] = None
    spoken_summary: Optional[str] = None
    speech_audio: Optional[SpokenAudioPayload] = None
    speech_timings_ms: Optional[Dict[str, float]] = None
    result_block: Optional[GenericResultBlock] = None
    result_blocks: List[GenericResultBlock] = Field(default_factory=list)
    primary_result_id: Optional[str] = None
    trust_evidence: Optional[TrustEvidence] = None
    error: Optional[SafeErrorDetail] = None



class OriginalAudioMetadata(BaseModel):
    """
    Server-computed request-scoped metadata for uploaded audio,
    preserving raw bytes integrity for downstream Detectif verification.
    """
    safe_filename: str
    declared_content_type: str
    normalized_mime_type: str
    byte_count: int
    sha256_digest: str
