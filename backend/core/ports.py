"""
IntentLock — Gateway Integration Ports & Fallback Adapters
Defines typed internal application interfaces for Speech Input, Speech Output,
Voice Evidence (Detectif), and Policy-Scoped Knowledge Retrieval.

During Stage 1, all production adapters report truthful unconfigured/unavailable
status and fail closed.
"""

from typing import Optional, Dict, Any, Protocol, runtime_checkable
from pydantic import BaseModel
from backend.models.turn import OriginalAudioMetadata, TrustEvidence


class SpeechInputResult(BaseModel):
    is_available: bool = False
    transcript: Optional[str] = None
    confidence: Optional[float] = None
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None
    speech_duration_s: Optional[float] = None


class SpeechOutputResult(BaseModel):
    is_available: bool = False
    audio_bytes: Optional[bytes] = None
    audio_format: Optional[str] = None
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None


class VoiceEvidenceResult(BaseModel):
    is_available: bool = False
    decision: Optional[str] = None  # "match" | "no_match"
    similarity_score: Optional[float] = None
    similarity_threshold: Optional[float] = None
    deepfake_verdict: Optional[str] = None  # "real" | "fake" | "not_sure"
    deepfake_score: Optional[float] = None
    deepfake_threshold: Optional[float] = None
    deepfake_error: Optional[str] = None
    speaker_id: Optional[str] = None
    request_id: Optional[str] = None
    model_version: Optional[str] = None
    account_alias: Optional[str] = None
    audio_digest: Optional[str] = None
    is_idempotent_replay: bool = False
    latency_ms: Optional[float] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def is_dual_verified(self) -> bool:
        """Dual verification requires BOTH speaker match AND real authenticity without errors."""
        return (
            self.is_available
            and self.decision == "match"
            and self.deepfake_verdict == "real"
            and not self.deepfake_error
            and not self.error_code
        )


class ScopedQueryResult(BaseModel):
    is_authorized: bool = False
    query: str
    answer: str
    matched_employees: list = []
    source_references: list = []
    reason_denied: Optional[str] = None


class AnswerResult(BaseModel):
    is_available: bool = False
    answer_text: str
    grounded: bool = False
    sources: list = []
    model: Optional[str] = None
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None


@runtime_checkable
class SpeechInputPort(Protocol):
    """Internal contract for transcribing caller audio into text."""
    async def transcribe(
        self,
        audio_metadata: OriginalAudioMetadata,
        audio_bytes: bytes,
        client_turn_id: str,
    ) -> SpeechInputResult:
        ...


@runtime_checkable
class SpeechOutputPort(Protocol):
    """Internal contract for synthesizing verified text into audio."""
    async def synthesize(
        self,
        text: str,
        client_turn_id: str,
    ) -> SpeechOutputResult:
        ...


@runtime_checkable
class VoiceEvidencePort(Protocol):
    """Internal contract for evaluating speaker verification & authenticity (Detectif)."""
    async def verify_evidence(
        self,
        audio_metadata: OriginalAudioMetadata,
        audio_bytes: bytes,
        candidate_speaker_id: Optional[str],
        correlation_id: str,
    ) -> VoiceEvidenceResult:
        ...


@runtime_checkable
class AuthorizationPolicyPort(Protocol):
    """Internal contract for enforcing trusted actor and field-level record scope."""
    def evaluate_scope(
        self,
        actor_id: Optional[str],
        requested_record_id: Optional[str],
        action: str,
    ) -> bool:
        ...


@runtime_checkable
class AnswerGenerationPort(Protocol):
    """Internal contract for grounded answer generation via Responses API."""
    async def generate_answer(
        self,
        question: str,
        authorized_context: Dict[str, Any],
        correlation_id: str,
    ) -> AnswerResult:
        ...


# =============================================================================
# Stage 1 Default Adapters (Truthfully Unavailable & Fail-Closed)
# =============================================================================

class UnavailableSpeechInputAdapter:
    """Default adapter indicating upstream speech-to-speech service is not connected."""
    async def transcribe(
        self,
        audio_metadata: OriginalAudioMetadata,
        audio_bytes: bytes,
        client_turn_id: str,
    ) -> SpeechInputResult:
        return SpeechInputResult(
            is_available=False,
            error_message="Speech-to-text service is unconfigured or unavailable.",
        )


class UnavailableSpeechOutputAdapter:
    """Default adapter indicating upstream text-to-speech service is not connected."""
    async def synthesize(
        self,
        text: str,
        client_turn_id: str,
    ) -> SpeechOutputResult:
        return SpeechOutputResult(
            is_available=False,
            error_message="Text-to-speech service is unconfigured or unavailable.",
        )


class UnavailableVoiceEvidenceAdapter:
    """Default adapter indicating Detectif verification provider is not connected."""
    async def verify_evidence(
        self,
        audio_metadata: OriginalAudioMetadata,
        audio_bytes: bytes,
        candidate_speaker_id: Optional[str],
        correlation_id: str,
    ) -> VoiceEvidenceResult:
        return VoiceEvidenceResult(
            is_available=False,
            error_code="DETECTIF_NOT_CONFIGURED",
            error_message="Voice verification provider is unconfigured or unavailable.",
        )


class UnavailableAnswerAdapter:
    """Default adapter indicating answer generation service is not connected."""
    def is_configured(self) -> bool:
        return False

    async def generate_answer(
        self,
        question: str,
        authorized_context: Dict[str, Any],
        correlation_id: str,
    ) -> AnswerResult:
        return AnswerResult(
            is_available=False,
            answer_text="Answer generation is unconfigured or unavailable.",
            grounded=False,
            error_message="Answer generator not configured.",
        )



class FailClosedPolicyAdapter:
    """Default policy adapter denying all private access in absence of verified server session."""
    def evaluate_scope(
        self,
        actor_id: Optional[str],
        requested_record_id: Optional[str],
        action: str,
    ) -> bool:
        # Without a validated backend session, private access is always denied
        return False
