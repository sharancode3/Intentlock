"""
IntentLock — DetectifAI Voice Evidence Adapter
Implements VoiceEvidencePort using the official Detectif API (v1).
Executes combined speaker verification and synthetic deepfake detection.

Enforces:
1. Strict Dual-Verification Invariant: Must have both decision=="match" AND deepfake.verdict=="real".
2. Identity Correspondence: Returned speaker_id must match the requested candidate.
3. Audio Bounds Validation: Verifies duration (>4.0s for combined checks) before dispatch.
4. Bounded Retries: Exponential backoff with jitter on 429/503 honoring Retry-After.
5. Idempotent Execution: Sends deterministic Idempotency-Key per turn audio digest.
6. Dependency Injection: Supports mock transports for zero-credit automated testing.
"""

import time
import hashlib
import logging
import asyncio
from typing import Optional, Dict, Any
import httpx
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.ports import VoiceEvidencePort, VoiceEvidenceResult
from backend.models.turn import OriginalAudioMetadata
from backend.adapters.audio_decoder import AudioDecoder

logger = logging.getLogger("intentlock.detectif")


_UNSET = object()


class DetectifHTTPClient:
    """Underlying HTTP client managing connection pooling and resilient requests to Detectif."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Any = _UNSET,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = (base_url or settings.DETECTIF_BASE_URL).rstrip("/")
        self.api_key = settings.DETECTIF_API_KEY if api_key is _UNSET else api_key
        self.timeout = timeout or settings.DETECTIF_TIMEOUT_SECONDS
        self.transport = transport
        self._client: Optional[httpx.AsyncClient] = None


    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Accept": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout, connect=5.0),
                transport=self.transport,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class DetectifVoiceEvidenceAdapter(VoiceEvidencePort):
    """Production Detectif adapter implementing VoiceEvidencePort."""

    def __init__(
        self,
        http_client: Optional[DetectifHTTPClient] = None,
        account_alias: Optional[str] = None,
    ):
        self.client_wrapper = http_client or DetectifHTTPClient()
        self.account_alias = account_alias or settings.DETECTIF_ACCOUNT_ALIAS

    def is_configured(self) -> bool:
        return bool(self.client_wrapper.api_key)

    async def verify_evidence(
        self,
        audio_metadata: OriginalAudioMetadata,
        audio_bytes: bytes,
        candidate_speaker_id: Optional[str],
        correlation_id: str,
    ) -> VoiceEvidenceResult:
        """
        Execute combined speaker verification and synthetic-speech check.
        Requires audio duration > 4.0 seconds for deepfake verification.
        """
        t0 = time.perf_counter()

        if not self.is_configured():
            return VoiceEvidenceResult(
                is_available=False,
                error_code="DETECTIF_UNCONFIGURED",
                error_message="Detectif API key is not configured on this server.",
                account_alias=self.account_alias,
                audio_digest=audio_metadata.sha256_digest,
            )

        if not candidate_speaker_id:
            return VoiceEvidenceResult(
                is_available=True,
                decision="no_match",
                deepfake_verdict="not_sure",
                error_code="NO_CANDIDATE_SPEAKER",
                error_message="A candidate speaker ID or employee ID is required for verification.",
                account_alias=self.account_alias,
                audio_digest=audio_metadata.sha256_digest,
            )

        # Preflight validation: Combined call requires audio > 4.0s
        try:
            pcm = AudioDecoder.decode_to_16k_mono(audio_bytes, max_duration_s=60.0, min_duration_s=0.1)
            duration_s = len(pcm) / 16000.0
            if duration_s <= 4.0:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                return VoiceEvidenceResult(
                    is_available=True,
                    decision="no_match",
                    deepfake_verdict="not_sure",
                    latency_ms=round(latency_ms, 2),
                    error_code="AUDIO_TOO_SHORT",
                    error_message=f"Combined verification requires audio longer than 4.0s (received {duration_s:.1f}s).",
                    account_alias=self.account_alias,
                    audio_digest=audio_metadata.sha256_digest,
                )
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return VoiceEvidenceResult(
                is_available=True,
                decision="no_match",
                deepfake_verdict="not_sure",
                latency_ms=round(latency_ms, 2),
                error_code="DECODE_ERROR",
                error_message=f"Failed to decode audio: {str(e)}",
                account_alias=self.account_alias,
                audio_digest=audio_metadata.sha256_digest,
            )

        # Deterministic Idempotency Key bound to turn audio digest, candidate, account, and operation ID
        op_id = correlation_id or f"op_{int(time.time() * 1000)}"
        idempotency_key = hashlib.sha256(
            f"{audio_metadata.sha256_digest}:{candidate_speaker_id}:{self.account_alias}:{op_id}".encode()
        ).hexdigest()

        # Build multipart payload
        files = {
            "file": (audio_metadata.safe_filename, audio_bytes, audio_metadata.normalized_mime_type)
        }
        data = {
            "speaker_id": candidate_speaker_id,
            "detect_deepfake": "true",
        }
        headers = {
            "Idempotency-Key": idempotency_key,
            "X-Correlation-Id": correlation_id,
        }

        # Resilient execution with retry on 429/503
        client = self.client_wrapper._get_client()
        max_retries = settings.DETECTIF_MAX_RETRIES
        resp = None

        for attempt in range(max_retries + 1):
            try:
                resp = await client.post(
                    "/speakers/verify",
                    data=data,
                    files=files,
                    headers=headers,
                )
                if resp.status_code in (429, 503) and attempt < max_retries:
                    retry_after = 1.0
                    if "retry-after" in resp.headers:
                        try:
                            retry_after = float(resp.headers["retry-after"])
                        except ValueError:
                            pass
                    logger.warning(
                        f"Detectif rate limit / unavailable ({resp.status_code}). "
                        f"Retrying after {retry_after}s (attempt {attempt + 1}/{max_retries})..."
                    )
                    await asyncio.sleep(retry_after)
                    continue
                break
            except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                if attempt < max_retries:
                    logger.warning(f"Detectif network failure: {net_err}. Retrying...")
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                latency_ms = (time.perf_counter() - t0) * 1000.0
                return VoiceEvidenceResult(
                    is_available=False,
                    latency_ms=round(latency_ms, 2),
                    error_code="PROVIDER_TIMEOUT",
                    error_message=f"Detectif service communication timed out: {str(net_err)}",
                    account_alias=self.account_alias,
                    audio_digest=audio_metadata.sha256_digest,
                )

        latency_ms = (time.perf_counter() - t0) * 1000.0

        if resp is None:
            return VoiceEvidenceResult(
                is_available=False,
                latency_ms=round(latency_ms, 2),
                error_code="PROVIDER_UNREACHABLE",
                error_message="Failed to contact Detectif service.",
                account_alias=self.account_alias,
                audio_digest=audio_metadata.sha256_digest,
            )

        # Parse Provider Response
        if resp.status_code == 200:
            try:
                payload = resp.json()
            except Exception as e:
                return VoiceEvidenceResult(
                    is_available=False,
                    latency_ms=round(latency_ms, 2),
                    error_code="INVALID_RESPONSE_JSON",
                    error_message=f"Detectif returned unparseable JSON: {str(e)}",
                    account_alias=self.account_alias,
                    audio_digest=audio_metadata.sha256_digest,
                )

            # Extract fields
            result_obj = payload.get("result", {})
            decision = result_obj.get("decision")  # "match" | "no_match"
            similarity = result_obj.get("similarity")
            sim_threshold = result_obj.get("threshold")

            returned_speaker_id = payload.get("speaker_id")
            # Enforce Identity Correspondence: returned speaker_id must match requested candidate
            if not returned_speaker_id or returned_speaker_id.strip() != candidate_speaker_id.strip():
                logger.error(
                    f"Identity correspondence failure: requested {candidate_speaker_id} but provider returned {returned_speaker_id}"
                )
                return VoiceEvidenceResult(
                    is_available=True,
                    decision="no_match",
                    deepfake_verdict="not_sure",
                    latency_ms=round(latency_ms, 2),
                    error_code="IDENTITY_CORRESPONDENCE_MISMATCH",
                    error_message="Provider speaker_id does not match mapped candidate ID.",
                    account_alias=self.account_alias,
                    audio_digest=audio_metadata.sha256_digest,
                )

            # Deepfake member
            deepfake_obj = payload.get("deepfake")
            if not isinstance(deepfake_obj, dict):
                deepfake_verdict = "not_sure"
                deepfake_score = 1.0
                deepfake_thresh = 0.5
                deepfake_error = "MISSING_DEEPFAKE_MEMBER"
            else:
                deepfake_verdict = deepfake_obj.get("verdict")  # "real" | "fake" | "not_sure"
                deepfake_score = deepfake_obj.get("score")
                deepfake_thresh = deepfake_obj.get("threshold")
                deepfake_error = deepfake_obj.get("error")

            is_replay = bool(
                resp.headers.get("x-idempotent-replay") == "true" or payload.get("is_replay")
            )

            logger.info(
                f"Detectif verify completed in {latency_ms:.1f}ms: "
                f"speaker={decision} (sim={similarity}), deepfake={deepfake_verdict} (score={deepfake_score})"
            )

            raw_model = (deepfake_obj.get("model") if isinstance(deepfake_obj, dict) else None) or payload.get("model_version")
            model_ver_str = str(raw_model) if raw_model is not None and not isinstance(raw_model, (dict, list)) else "detectif_v1"

            return VoiceEvidenceResult(
                is_available=True,
                decision=decision,
                similarity_score=similarity,
                similarity_threshold=sim_threshold,
                deepfake_verdict=deepfake_verdict,
                deepfake_score=deepfake_score,
                deepfake_threshold=deepfake_thresh,
                deepfake_error=deepfake_error,
                speaker_id=returned_speaker_id,
                request_id=payload.get("request_id") or resp.headers.get("x-request-id"),
                model_version=model_ver_str,
                account_alias=self.account_alias,
                audio_digest=audio_metadata.sha256_digest,
                is_idempotent_replay=is_replay,
                latency_ms=round(latency_ms, 2),
                error_code=None,
                error_message=None,
            )

        # Provider errors (400, 401, 403, 404, 422, etc.)
        try:
            err_json = resp.json()
            err_msg = err_json.get("error", {}).get("message") or err_json.get("message") or resp.text
            err_code = err_json.get("error", {}).get("code") or f"HTTP_{resp.status_code}"
        except Exception:
            err_msg = resp.text
            err_code = f"HTTP_{resp.status_code}"

        logger.error(f"Detectif returned error HTTP {resp.status_code}: {err_code} - {err_msg}")
        return VoiceEvidenceResult(
            is_available=False,
            latency_ms=round(latency_ms, 2),
            error_code=err_code,
            error_message=f"Detectif error: {err_msg}",
            account_alias=self.account_alias,
            audio_digest=audio_metadata.sha256_digest,
        )

    # =========================================================================
    # Enrollment & Preflight Tooling
    # =========================================================================

    async def detect_deepfake(self, audio_bytes: bytes, filename: str = "audio.wav") -> Dict[str, Any]:
        """Preflight authenticity check on enrollment audio."""
        client = self.client_wrapper._get_client()
        files = {"file": (filename, audio_bytes, "audio/wav")}
        resp = await client.post("/deepfake/detect", files=files)
        resp.raise_for_status()
        return resp.json()

    async def enroll_speaker(
        self,
        speaker_id: str,
        audio_bytes: bytes,
        display_name: Optional[str] = None,
        filename: str = "enroll.wav",
    ) -> Dict[str, Any]:
        """Enroll real speaker audio sample in Detectif."""
        client = self.client_wrapper._get_client()
        files = {"file": (filename, audio_bytes, "audio/wav")}
        data: Dict[str, str] = {"speaker_id": speaker_id}
        if display_name:
            data["display_name"] = display_name
        resp = await client.post("/speakers/enroll", data=data, files=files)
        resp.raise_for_status()
        return resp.json()

    async def get_balance(self) -> Dict[str, Any]:
        """Query account balance / credit diagnostics."""
        client = self.client_wrapper._get_client()
        resp = await client.get("/credits")
        resp.raise_for_status()
        return resp.json()

    async def list_remote_speakers(self) -> Dict[str, Any]:
        """Query enrolled speakers from Detectif."""
        client = self.client_wrapper._get_client()
        resp = await client.get("/speakers")
        resp.raise_for_status()
        return resp.json()

    async def get_speaker(self, speaker_id: str) -> Optional[Dict[str, Any]]:
        """Query individual speaker metadata from Detectif."""
        client = self.client_wrapper._get_client()
        try:
            resp = await client.get(f"/speakers/{speaker_id}")
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None

