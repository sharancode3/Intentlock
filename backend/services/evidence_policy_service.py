"""
IntentLock — Authoritative Evidence Policy Service
Enforces strict policy-driven verification routing for Detectif AI biometrics:
- Evaluates turn context, active sessions, operations, and claims.
- Decides whether a biometric provider call is required, reusable, or zero-call.
- Distinguishes speaker-only, deepfake-only, and combined verification modes.
- Guarantees deepfake-only never creates or authenticates an employee session.
- Ensures LLM / model outputs cannot bypass or dictate evidence requirements.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.core.config import settings

logger = logging.getLogger("intentlock.evidence_policy")


class EvidenceCheckMode(str, Enum):
    NO_CHECK = "none"
    REUSE = "reuse"
    COMBINED = "combined"
    SPEAKER_ONLY = "speaker"
    DEEPFAKE_ONLY = "deepfake"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"


class EvidencePolicyDecision(BaseModel):
    mode: EvidenceCheckMode
    requires_provider_call: bool = False
    reason_code: str
    reason_description: str
    candidate_id: Optional[str] = None
    audio_min_duration_s: float = 0.0
    evidence_freshness: str = "fresh_this_turn"  # "fresh_this_turn" | "reused_from_session" | "none"


class EvidencePolicyContext(BaseModel):
    actor_id: Optional[str] = None
    candidate_employee_id: Optional[str] = None
    spoken_claim_id: Optional[str] = None
    session_id: Optional[str] = None
    session_valid: bool = False
    session_age_s: float = 0.0
    session_actor_id: Optional[str] = None
    operation: str = "query"
    is_mutation: bool = False
    has_audio: bool = True
    audio_duration_s: Optional[float] = None
    explicit_mode_requested: Optional[str] = None


class EvidencePolicyService:
    _instance: Optional["EvidencePolicyService"] = None

    @classmethod
    def get_instance(cls) -> "EvidencePolicyService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def evaluate_turn_requirements(
        self,
        context: EvidencePolicyContext,
        enrollment_mapping: Optional[Any] = None,
    ) -> EvidencePolicyDecision:
        """
        Authoritatively evaluates required evidence according to the Evidence Matrix:
        Section 5:
        A. Public Help: 0 provider calls.
        B. Initial Employee Entry: Combined check (audio > 4.0s).
        C. Reuse of Authorized Result: 0 provider calls (rechart, back, cancel, view switch).
        D. New Private Read: Valid session reuse within TTL or Combined check.
        E. Speaker-Only: Dedicated speaker verification (audio > 1.0s).
        F. Deepfake-Only: Dedicated authenticity check (audio > 3.0s). Never authenticates an employee session.
        G. Protected Edits / Confirm: Fresh audio verification required (Combined check).
        H. Identity Change / Expiry: Session cleared, step-up Combined check.
        """
        op = (context.operation or "query").lower().strip()

        # 1. Public Help / FAQ / Capabilities
        if op in ("help", "faq", "public_info", "list_capabilities", "greeting", "none") and not context.candidate_employee_id and not context.spoken_claim_id:
            return EvidencePolicyDecision(
                mode=EvidenceCheckMode.NO_CHECK,
                requires_provider_call=False,
                reason_code="PUBLIC_HELP",
                reason_description="Public inquiry requires zero provider checks.",
                evidence_freshness="none",
            )

        # 2. Navigation / Back / Cancel
        if op in ("cancel", "back", "reset"):
            return EvidencePolicyDecision(
                mode=EvidenceCheckMode.NO_CHECK,
                requires_provider_call=False,
                reason_code="NAVIGATION_CANCEL",
                reason_description="Navigation or cancellation requires zero provider checks.",
                evidence_freshness="none" if not context.session_valid else "reused_from_session",
            )

        # 3. Detect Claim Conflicts
        if context.session_valid and context.session_actor_id:
            if context.candidate_employee_id and context.candidate_employee_id.strip().upper() != context.session_actor_id.strip().upper():
                logger.warning(
                    "EvidencePolicy: Claim conflict (session=%s vs candidate=%s)",
                    context.session_actor_id, context.candidate_employee_id
                )
                return EvidencePolicyDecision(
                    mode=EvidenceCheckMode.DENIED,
                    requires_provider_call=False,
                    reason_code="CLAIM_CONFLICT",
                    reason_description="Candidate identity conflicts with active verified session.",
                    evidence_freshness="none",
                )
            if context.spoken_claim_id and context.spoken_claim_id.strip().upper() != context.session_actor_id.strip().upper():
                logger.warning(
                    "EvidencePolicy: Claim conflict (session=%s vs spoken=%s)",
                    context.session_actor_id, context.spoken_claim_id
                )
                return EvidencePolicyDecision(
                    mode=EvidenceCheckMode.DENIED,
                    requires_provider_call=False,
                    reason_code="CLAIM_CONFLICT",
                    reason_description="Spoken identity claim conflicts with active verified session.",
                    evidence_freshness="none",
                )

        # 4. Protected Action Confirmation (Strictly Fresh Biometrics Required)
        if op == "confirm" or (context.is_mutation and op.startswith("confirm")):
            target_candidate = context.session_actor_id or context.candidate_employee_id or context.spoken_claim_id
            if not target_candidate:
                return EvidencePolicyDecision(
                    mode=EvidenceCheckMode.DENIED,
                    requires_provider_call=False,
                    reason_code="NO_CANDIDATE_FOR_MUTATION",
                    reason_description="Protected mutation confirmation requires an identified candidate.",
                    evidence_freshness="none",
                )
            if not context.has_audio:
                return EvidencePolicyDecision(
                    mode=EvidenceCheckMode.UNAVAILABLE,
                    requires_provider_call=False,
                    reason_code="NO_AUDIO_FOR_CONFIRMATION",
                    reason_description="Fresh audio is required to confirm protected mutations.",
                    candidate_id=target_candidate,
                    evidence_freshness="none",
                )
            return EvidencePolicyDecision(
                mode=EvidenceCheckMode.COMBINED,
                requires_provider_call=True,
                reason_code="PROTECTED_MUTATION_CONFIRMATION",
                reason_description="Protected mutation confirmation requires fresh combined biometric verification.",
                candidate_id=target_candidate,
                audio_min_duration_s=4.0,
                evidence_freshness="fresh_this_turn",
            )

        # 5. Contextual Reuse (presentation / rechart / summarize / drilldown / details)
        if context.session_valid and context.session_actor_id:
            ttl = settings.SESSION_TTL_SECONDS
            if context.session_age_s <= ttl:
                if op in ("rechart", "view_switch", "reformat", "summarize", "drilldown", "details") or (
                    not context.is_mutation and not context.candidate_employee_id and not context.spoken_claim_id
                ):
                    return EvidencePolicyDecision(
                        mode=EvidenceCheckMode.REUSE,
                        requires_provider_call=False,
                        reason_code="REUSE_SESSION_EVIDENCE",
                        reason_description="Reusing valid session evidence for presentation transformation.",
                        candidate_id=context.session_actor_id,
                        evidence_freshness="reused_from_session",
                    )

        # 6. Explicit Deepfake-Only Request (Authenticity Check / Enrollment Preflight)
        if context.explicit_mode_requested == "deepfake":
            if not context.has_audio:
                return EvidencePolicyDecision(
                    mode=EvidenceCheckMode.UNAVAILABLE,
                    requires_provider_call=False,
                    reason_code="NO_AUDIO_FOR_DEEPFAKE",
                    reason_description="Audio is required for deepfake detection.",
                    evidence_freshness="none",
                )
            return EvidencePolicyDecision(
                mode=EvidenceCheckMode.DEEPFAKE_ONLY,
                requires_provider_call=True,
                reason_code="DEEPFAKE_DETECTION_REQUESTED",
                reason_description="Standalone audio authenticity assessment requested.",
                candidate_id=None,
                audio_min_duration_s=3.0,
                evidence_freshness="fresh_this_turn",
            )

        # 7. Explicit Speaker-Only Request
        if context.explicit_mode_requested == "speaker":
            target_candidate = context.candidate_employee_id or context.spoken_claim_id or context.session_actor_id
            if not target_candidate:
                return EvidencePolicyDecision(
                    mode=EvidenceCheckMode.DENIED,
                    requires_provider_call=False,
                    reason_code="NO_CANDIDATE_SPEAKER",
                    reason_description="Speaker verification requires a candidate speaker ID.",
                    evidence_freshness="none",
                )
            if not context.has_audio:
                return EvidencePolicyDecision(
                    mode=EvidenceCheckMode.UNAVAILABLE,
                    requires_provider_call=False,
                    reason_code="NO_AUDIO_FOR_SPEAKER",
                    reason_description="Audio is required for speaker verification.",
                    candidate_id=target_candidate,
                    evidence_freshness="none",
                )
            return EvidencePolicyDecision(
                mode=EvidenceCheckMode.SPEAKER_ONLY,
                requires_provider_call=True,
                reason_code="SPEAKER_VERIFICATION_REQUESTED",
                reason_description="Speaker-only verification requested.",
                candidate_id=target_candidate,
                audio_min_duration_s=1.0,
                evidence_freshness="fresh_this_turn",
            )

        # 8. Initial Employee Entry / Login or New Private Read
        target_candidate = context.candidate_employee_id or context.spoken_claim_id
        if target_candidate:
            target_candidate = target_candidate.strip().upper()
            if enrollment_mapping is not None and getattr(enrollment_mapping, "enrollment_status", None) != "ENROLLED":
                return EvidencePolicyDecision(
                    mode=EvidenceCheckMode.DENIED,
                    requires_provider_call=False,
                    reason_code="UNENROLLED_CANDIDATE",
                    reason_description=f"Candidate '{target_candidate}' is not enrolled in voice biometrics.",
                    candidate_id=target_candidate,
                    evidence_freshness="none",
                )
            if not context.has_audio:
                return EvidencePolicyDecision(
                    mode=EvidenceCheckMode.UNAVAILABLE,
                    requires_provider_call=False,
                    reason_code="NO_AUDIO_FOR_LOGIN",
                    reason_description="Audio is required for employee identity verification.",
                    candidate_id=target_candidate,
                    evidence_freshness="none",
                )
            if context.audio_duration_s is not None and context.audio_duration_s <= 4.0:
                return EvidencePolicyDecision(
                    mode=EvidenceCheckMode.UNAVAILABLE,
                    requires_provider_call=False,
                    reason_code="AUDIO_TOO_SHORT",
                    reason_description=f"Combined verification requires audio longer than 4.0s (received {context.audio_duration_s:.1f}s).",
                    candidate_id=target_candidate,
                    audio_min_duration_s=4.0,
                    evidence_freshness="none",
                )
            return EvidencePolicyDecision(
                mode=EvidenceCheckMode.COMBINED,
                requires_provider_call=True,
                reason_code="INITIAL_EMPLOYEE_ENTRY",
                reason_description="Initial employee entry requires combined speaker verification and authenticity detection.",
                candidate_id=target_candidate,
                audio_min_duration_s=4.0,
                evidence_freshness="fresh_this_turn",
            )

        # 9. Active session default query
        if context.session_valid and context.session_actor_id:
            return EvidencePolicyDecision(
                mode=EvidenceCheckMode.REUSE,
                requires_provider_call=False,
                reason_code="ACTIVE_SESSION_QUERY",
                reason_description="Query evaluated under active verified session.",
                candidate_id=context.session_actor_id,
                evidence_freshness="reused_from_session",
            )

        # 10. Unauthenticated anonymous query
        return EvidencePolicyDecision(
            mode=EvidenceCheckMode.NO_CHECK,
            requires_provider_call=False,
            reason_code="ANONYMOUS_QUERY",
            reason_description="Anonymous query without identity claims.",
            evidence_freshness="none",
        )
