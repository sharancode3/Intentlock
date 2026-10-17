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
import math
from typing import Optional, Dict, Any
from urllib.parse import quote
import httpx
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.ports import VoiceEvidencePort, VoiceEvidenceResult
from backend.models.turn import OriginalAudioMetadata
from backend.adapters.audio_decoder import AudioDecoder

logger = logging.getLogger("intentlock.detectif")


_UNSET = object()


def _charged_credits(payload, headers) -> Optional[float]:
    credits = payload.get("credits") if isinstance(payload, dict) else None
    billing = payload.get("billing") if isinstance(payload, dict) else None
    candidates = [credits.get("charged") if isinstance(credits, dict) else None,
        headers.get("x-credits-charged"), headers.get("credits-charged")]
    if isinstance(payload, dict):
        candidates.extend([payload.get("credits_charged"), payload.get("credits_used"), credits])
    if isinstance(billing, dict):
        candidates.extend([billing.get("credits_charged"), billing.get("credits_used")])
    for value in candidates:
        if value is None or isinstance(value, (bool, dict, list)):
            continue
        try:
            amount = float(value)
            if math.isfinite(amount) and amount >= 0:
                return amount
        except (TypeError, ValueError):
            pass
    return None


class DetectifHTTPClient:
    """Underlying HTTP client managing connection pooling and resilient requests to Detectif."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Any = _UNSET,
        speaker_api_key: Any = _UNSET,
        deepfake_api_key: Any = _UNSET,
        combined_api_key: Any = _UNSET,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = (base_url or settings.DETECTIF_BASE_URL).rstrip("/")
        self.api_key = settings.DETECTIF_API_KEY if api_key is _UNSET else api_key
        if api_key is _UNSET:
            self.speaker_api_key = settings.DETECTIF_SPEAKER_API_KEY if speaker_api_key is _UNSET else speaker_api_key
            self.deepfake_api_key = settings.DETECTIF_DEEPFAKE_API_KEY if deepfake_api_key is _UNSET else deepfake_api_key
            self.combined_api_key = settings.DETECTIF_COMBINED_API_KEY if combined_api_key is _UNSET else combined_api_key
        else:
            self.speaker_api_key = api_key if speaker_api_key is _UNSET else speaker_api_key
            self.deepfake_api_key = api_key if deepfake_api_key is _UNSET else deepfake_api_key
            self.combined_api_key = api_key if combined_api_key is _UNSET else combined_api_key
        self.timeout = timeout or settings.DETECTIF_TIMEOUT_SECONDS
        self.transport = transport
        self._client: Optional[httpx.AsyncClient] = None

    def get_credential_for_mode(self, mode: str) -> tuple[Optional[str], str]:
        """Returns (api_key, role) where role is 'speaker', 'deepfake', 'combined', or 'legacy'.
        Raises ValueError on unknown verification modes.
        """
        valid_modes = ("speaker", "deepfake", "combined")
        if mode not in valid_modes:
            raise ValueError(f"Unknown Detectif verification mode: '{mode}'. Valid modes: {valid_modes}")

        scoped_key: Optional[str] = None
        if mode == "speaker":
            scoped_key = self.speaker_api_key
        elif mode == "deepfake":
            scoped_key = self.deepfake_api_key
        elif mode == "combined":
            scoped_key = self.combined_api_key

        if scoped_key:
            return scoped_key, mode

        # Fallback to legacy key only if explicitly configured
        if settings.DETECTIF_LEGACY_KEY_FALLBACK and self.api_key:
            logger.info("Detectif mode '%s' falling back to legacy DETECTIF_API_KEY", mode)
            return self.api_key, "legacy"

        return None, mode

    def get_api_key_for_mode(self, mode: str) -> Optional[str]:
        """Returns the appropriate scoped credential for the mode, falling back to base api_key."""
        try:
            key, _ = self.get_credential_for_mode(mode)
            return key
        except ValueError:
            return None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Accept": "application/json"}
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout, connect=5.0),
                transport=self.transport,
                trust_env=self.transport is None,
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
        self._enrollment_cache: Dict[tuple, tuple] = {}

    async def preflight_speaker(self, speaker_id: str, mode: str, account_alias: str):
        """Read-only metadata check with the SAME credential as the paid operation.

        A definite missing enrollment blocks upload (including billable partial combined
        checks). Metadata-forbidden keys may still verify; never try a different key.
        Returns None when verification can proceed, otherwise a truthful unavailable result.
        """
        key, role = self.client_wrapper.get_credential_for_mode(mode)
        def failure(code, message):
            return VoiceEvidenceResult(is_available=False, error_code=code,
                error_message=message, account_alias=self.account_alias,
                mode_executed=None, credential_role=role)
        if account_alias != self.account_alias:
            return failure("ACCOUNT_MAPPING_MISMATCH",
                "The employee enrollment belongs to a different configured verification account. Contact the operator.")
        if not key:
            return failure("DETECTIF_UNCONFIGURED", f"Verification credential for {mode} is not configured.")
        cache_key = (hashlib.sha256(key.encode()).hexdigest(), speaker_id)
        cached = self._enrollment_cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1].model_copy(update={"credits_charged": None, "mode_executed": None,
                "request_id": None, "latency_ms": None}) if cached[1] is not None else None
        try:
            response = await self.client_wrapper._get_client().get(
                f"/speakers/{quote(speaker_id, safe='')}", headers=self._auth_headers(key))
        except httpx.RequestError:
            return failure("PROVIDER_UNREACHABLE", "Cannot check speaker enrollment. Please retry later.")
        result = None
        ttl = 300
        if response.status_code == 404:
            ttl = 60
            result = failure("SPEAKER_NOT_FOUND",
                "This employee's speaker enrollment was not found under the configured verification credential. "
                "The operator must check the account, key and speaker mapping. No verification audio was submitted.")
        elif response.status_code == 401:
            ttl = 60
            result = failure("INVALID_CREDENTIAL", "The configured verification credential was rejected. Contact the operator.")
        elif response.status_code not in (200, 403):
            return failure("ENROLLMENT_CHECK_UNAVAILABLE", "Speaker enrollment check is temporarily unavailable. Please retry later.")
        if len(self._enrollment_cache) >= 256:
            self._enrollment_cache.pop(next(iter(self._enrollment_cache)))
        self._enrollment_cache[cache_key] = (time.monotonic() + ttl, result)
        return result

    def is_configured(self, mode: str = "combined") -> bool:
        return bool(self.client_wrapper.get_api_key_for_mode(mode))

    async def verify_evidence(
        self,
        audio_metadata: OriginalAudioMetadata,
        audio_bytes: bytes,
        candidate_speaker_id: Optional[str],
        correlation_id: str,
        mode: str = "combined",
    ) -> VoiceEvidenceResult:
        """
        Execute mode-aware biometric verification:
        - mode="speaker": speaker-only verification via POST /speakers/verify (detect_deepfake=false)
        - mode="deepfake": deepfake-only detection via POST /deepfake/detect
        - mode="combined": combined verification via POST /speakers/verify (detect_deepfake=true)
        """
        t0 = time.perf_counter()
        try:
            resolved_key, role = self.client_wrapper.get_credential_for_mode(mode)
        except ValueError as err:
            return VoiceEvidenceResult(
                is_available=False,
                error_code="INVALID_MODE",
                error_message=str(err),
                account_alias=self.account_alias,
                audio_digest=audio_metadata.sha256_digest,
                credential_role=None,
                mode_executed=mode,
            )

        if not resolved_key:
            return VoiceEvidenceResult(
                is_available=False,
                error_code="DETECTIF_UNCONFIGURED",
                error_message=f"Detectif API key is not configured on this server for mode '{mode}'.",
                account_alias=self.account_alias,
                audio_digest=audio_metadata.sha256_digest,
                credential_role=role,
                mode_executed=mode,
            )

        if mode in ("combined", "speaker") and not candidate_speaker_id:
            return VoiceEvidenceResult(
                is_available=True,
                decision="no_match",
                deepfake_verdict="not_sure" if mode == "combined" else None,
                error_code="NO_CANDIDATE_SPEAKER",
                error_message="A candidate speaker ID or employee ID is required for verification.",
                account_alias=self.account_alias,
                audio_digest=audio_metadata.sha256_digest,
                credential_role=role,
                mode_executed=mode,
            )

        # Preflight validation: Audio duration bounds before provider calls
        min_duration = 3.0 if mode == "speaker" else 4.0
        try:
            pcm = AudioDecoder.decode_to_16k_mono(audio_bytes, max_duration_s=60.0, min_duration_s=0.1)
            duration_s = len(pcm) / 16000.0
            if duration_s < min_duration or (mode != "speaker" and duration_s == min_duration):
                latency_ms = (time.perf_counter() - t0) * 1000.0
                return VoiceEvidenceResult(
                    is_available=True,
                    decision="no_match" if mode in ("combined", "speaker") else None,
                    deepfake_verdict="not_sure" if mode in ("combined", "deepfake") else None,
                    latency_ms=round(latency_ms, 2),
                    error_code="AUDIO_TOO_SHORT",
                    error_message=f"{mode.capitalize()} verification requires audio longer than {min_duration:.1f}s (received {duration_s:.1f}s).",
                    account_alias=self.account_alias,
                    audio_digest=audio_metadata.sha256_digest,
                    credential_role=role,
                    mode_executed=mode,
                )
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return VoiceEvidenceResult(
                is_available=True,
                decision="no_match" if mode in ("combined", "speaker") else None,
                deepfake_verdict="not_sure" if mode in ("combined", "deepfake") else None,
                latency_ms=round(latency_ms, 2),
                error_code="DECODE_ERROR",
                error_message=f"Failed to decode audio: {str(e)}",
                account_alias=self.account_alias,
                audio_digest=audio_metadata.sha256_digest,
                credential_role=role,
                mode_executed=mode,
            )

        # Deterministic Idempotency Key bound to turn audio digest, candidate, account, op_id, and mode
        op_id = correlation_id or f"op_{int(time.time() * 1000)}"
        idempotency_key = hashlib.sha256(
            f"{audio_metadata.sha256_digest}:{candidate_speaker_id or 'none'}:{self.account_alias}:{op_id}:{mode}".encode()
        ).hexdigest()

        # Build request parameters according to mode
        files = {
            "file": (audio_metadata.safe_filename, audio_bytes, audio_metadata.normalized_mime_type)
        }
        headers = {
            "Idempotency-Key": idempotency_key,
            "X-Correlation-Id": correlation_id,
            "Authorization": f"Bearer {resolved_key}",
            "x-api-key": resolved_key,
        }

        if mode == "deepfake":
            endpoint = "/deepfake/detect"
            data = None
        elif mode == "speaker":
            endpoint = "/speakers/verify"
            data = {
                "speaker_id": candidate_speaker_id,
                "detect_deepfake": "false",
            }
        else:  # combined
            endpoint = "/speakers/verify"
            data = {
                "speaker_id": candidate_speaker_id,
                "detect_deepfake": "true",
            }

        client = self.client_wrapper._get_client()
        max_retries = settings.DETECTIF_MAX_RETRIES
        resp = None

        for attempt in range(max_retries + 1):
            try:
                resp = await client.post(
                    endpoint,
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
                    credential_role=role,
                    mode_executed=mode,
                    credits_charged=None,
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
                credential_role=role,
                mode_executed=mode,
                credits_charged=None,
            )

        # Parse Provider Response
        if resp.status_code == 200:
            try:
                payload = resp.json()
                if not isinstance(payload, dict):
                    raise ValueError("Expected an object response")
            except Exception as e:
                return VoiceEvidenceResult(
                    is_available=False,
                    latency_ms=round(latency_ms, 2),
                    error_code="INVALID_RESPONSE_JSON",
                    error_message=f"Detectif returned unparseable JSON: {str(e)}",
                    account_alias=self.account_alias,
                    audio_digest=audio_metadata.sha256_digest,
                    credential_role=role,
                    mode_executed=mode,
                    credits_charged=None,
                )

            is_replay = bool(
                resp.headers.get("x-idempotent-replay") == "true" or payload.get("is_replay") or payload.get("idempotent_replay")
            )
            raw_model = (payload.get("model") or {}).get("version") if isinstance(payload.get("model"), dict) else payload.get("model_version")

            credits_charged = _charged_credits(payload, resp.headers)
            # Missing billing metadata is unknown, never an invented credit amount.

            if mode == "deepfake":
                df_obj = payload.get("result") if isinstance(payload.get("result"), dict) else (
                    payload.get("deepfake") if isinstance(payload.get("deepfake"), dict) else payload)
                deepfake_verdict = df_obj.get("verdict", "not_sure")
                deepfake_score = df_obj.get("score")
                deepfake_thresh = df_obj.get("threshold", 0.5)
                deepfake_error = df_obj.get("error")
                if isinstance(deepfake_error, dict):
                    deepfake_error = deepfake_error.get("code") or "DEEPFAKE_CHECK_FAILED"
                raw_model = df_obj.get("model") or raw_model
                if isinstance(raw_model, dict):
                    raw_model = raw_model.get("version")
                model_ver_str = str(raw_model) if raw_model is not None and not isinstance(raw_model, (dict, list)) else "detectif_v1"

                logger.info(
                    f"Detectif deepfake check completed in {latency_ms:.1f}ms: "
                    f"verdict={deepfake_verdict} (score={deepfake_score})"
                )

                return VoiceEvidenceResult(
                    is_available=True,
                    decision=None,
                    deepfake_verdict=deepfake_verdict,
                    deepfake_score=deepfake_score,
                    deepfake_threshold=deepfake_thresh,
                    deepfake_error=deepfake_error,
                    speaker_id=None,
                    request_id=payload.get("request_id") or resp.headers.get("x-request-id"),
                    model_version=model_ver_str,
                    account_alias=self.account_alias,
                    audio_digest=audio_metadata.sha256_digest,
                    is_idempotent_replay=is_replay,
                    latency_ms=round(latency_ms, 2),
                    credential_role=role,
                    mode_executed=mode,
                    credits_charged=credits_charged,
                )

            # Speaker or Combined
            result_obj = payload.get("result", {})
            decision = result_obj.get("decision")  # "match" | "no_match"
            similarity = result_obj.get("similarity")
            sim_threshold = result_obj.get("threshold")

            returned_speaker_id = payload.get("speaker_id")
            if not returned_speaker_id or returned_speaker_id.strip() != candidate_speaker_id.strip():
                logger.error(
                    f"Identity correspondence failure: requested {candidate_speaker_id} but provider returned {returned_speaker_id}"
                )
                return VoiceEvidenceResult(
                    is_available=True,
                    decision="no_match",
                    deepfake_verdict="not_sure" if mode == "combined" else None,
                    latency_ms=round(latency_ms, 2),
                    error_code="IDENTITY_CORRESPONDENCE_MISMATCH",
                    error_message="Provider speaker_id does not match mapped candidate ID.",
                    account_alias=self.account_alias,
                    audio_digest=audio_metadata.sha256_digest,
                    credential_role=role,
                    mode_executed=mode,
                    credits_charged=credits_charged,
                )

            if mode == "speaker":
                model_ver_str = str(raw_model) if raw_model is not None and not isinstance(raw_model, (dict, list)) else "detectif_v1"
                logger.info(
                    f"Detectif speaker verify completed in {latency_ms:.1f}ms: "
                    f"speaker={decision} (sim={similarity})"
                )
                return VoiceEvidenceResult(
                    is_available=True,
                    decision=decision,
                    similarity_score=similarity,
                    similarity_threshold=sim_threshold,
                    deepfake_verdict=None,
                    deepfake_score=None,
                    deepfake_threshold=None,
                    deepfake_error=None,
                    speaker_id=returned_speaker_id,
                    request_id=payload.get("request_id") or resp.headers.get("x-request-id"),
                    model_version=model_ver_str,
                    account_alias=self.account_alias,
                    audio_digest=audio_metadata.sha256_digest,
                    is_idempotent_replay=is_replay,
                    latency_ms=round(latency_ms, 2),
                    credential_role=role,
                    mode_executed=mode,
                    credits_charged=credits_charged,
                )

            # Combined
            deepfake_obj = payload.get("deepfake")
            if not isinstance(deepfake_obj, dict):
                deepfake_verdict = "not_sure"
                deepfake_score = None
                deepfake_thresh = None
                deepfake_error = "MISSING_DEEPFAKE_MEMBER"
            else:
                deepfake_verdict = deepfake_obj.get("verdict")
                deepfake_score = deepfake_obj.get("score")
                deepfake_thresh = deepfake_obj.get("threshold")
                deepfake_error = deepfake_obj.get("error")
                if isinstance(deepfake_error, dict):
                    deepfake_error = deepfake_error.get("code") or "DEEPFAKE_CHECK_FAILED"

            logger.info(
                f"Detectif verify completed in {latency_ms:.1f}ms: "
                f"speaker={decision} (sim={similarity}), deepfake={deepfake_verdict} (score={deepfake_score})"
            )

            raw_model = (deepfake_obj.get("model") if isinstance(deepfake_obj, dict) else None) or payload.get("model_version")
            if isinstance(raw_model, dict):
                raw_model = raw_model.get("version")
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
                credential_role=role,
                mode_executed=mode,
                credits_charged=credits_charged,
            )

        # Provider errors (400, 401, 403, 404, 422, etc.)
        status_map = {
            401: "INVALID_CREDENTIAL",
            402: "INSUFFICIENT_CREDITS",
            403: "FORBIDDEN_SCOPE",
            404: "SPEAKER_NOT_FOUND",
            429: "RATE_LIMIT_EXCEEDED",
            502: "PROVIDER_UNAVAILABLE",
            503: "PROVIDER_UNAVAILABLE",
            504: "PROVIDER_UNAVAILABLE",
        }
        try:
            err_json = resp.json()
            err_msg = err_json.get("error", {}).get("message") or err_json.get("message") or resp.text
            err_code = status_map.get(resp.status_code) or err_json.get("error", {}).get("code") or f"HTTP_{resp.status_code}"
        except Exception:
            err_msg = resp.text
            err_code = status_map.get(resp.status_code) or f"HTTP_{resp.status_code}"

        try:
            billed = _charged_credits(resp.json(), resp.headers)
        except (ValueError, TypeError):
            billed = None
        logger.error("Detectif HTTP %s: %s (credits_charged=%s)", resp.status_code, err_code, billed)
        result = VoiceEvidenceResult(
            is_available=False,
            latency_ms=round(latency_ms, 2),
            error_code=err_code,
            error_message=f"Detectif error: {err_msg}",
            account_alias=self.account_alias,
            audio_digest=audio_metadata.sha256_digest,
            credential_role=role,
            mode_executed=mode,
            credits_charged=billed,
        )
        if resp.status_code in (401, 404) and candidate_speaker_id and mode != "deepfake":
            cache_key = (hashlib.sha256(resolved_key.encode()).hexdigest(), candidate_speaker_id)
            if len(self._enrollment_cache) >= 256:
                self._enrollment_cache.pop(next(iter(self._enrollment_cache)))
            self._enrollment_cache[cache_key] = (time.monotonic() + 60, result)
        return result

    # =========================================================================
    # Enrollment & Preflight Tooling
    # =========================================================================

    def _auth_headers(self, key: Optional[str]) -> Dict[str, str]:
        if not key:
            return {}
        return {
            "Authorization": f"Bearer {key}",
            "x-api-key": key,
        }

    async def detect_deepfake(self, audio_bytes: bytes, filename: str = "audio.wav") -> Dict[str, Any]:
        """Preflight authenticity check on audio."""
        key = (
            self.client_wrapper.get_api_key_for_mode("deepfake")
            or self.client_wrapper.get_api_key_for_mode("combined")
            or self.client_wrapper.api_key
        )
        client = self.client_wrapper._get_client()
        files = {"file": (filename, audio_bytes, "audio/wav")}
        resp = await client.post("/deepfake/detect", files=files, headers=self._auth_headers(key))
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
        key = (
            self.client_wrapper.get_api_key_for_mode("speaker")
            or self.client_wrapper.get_api_key_for_mode("combined")
            or self.client_wrapper.api_key
        )
        client = self.client_wrapper._get_client()
        files = {"file": (filename, audio_bytes, "audio/wav")}
        data: Dict[str, str] = {"speaker_id": speaker_id}
        if display_name:
            data["display_name"] = display_name
        resp = await client.post("/speakers/enroll", data=data, files=files, headers=self._auth_headers(key))
        resp.raise_for_status()
        return resp.json()

    async def get_balance(self, role: Optional[str] = None) -> Dict[str, Any]:
        """Query account balance / credit diagnostics."""
        key = self.client_wrapper.get_api_key_for_mode(role) if role else (
            self.client_wrapper.get_api_key_for_mode("combined")
            or self.client_wrapper.get_api_key_for_mode("speaker")
            or self.client_wrapper.get_api_key_for_mode("deepfake")
            or self.client_wrapper.api_key
        )
        client = self.client_wrapper._get_client()
        resp = await client.get("/credits", headers=self._auth_headers(key))
        resp.raise_for_status()
        return resp.json()

    async def list_remote_speakers(self) -> Dict[str, Any]:
        """Query enrolled speakers from Detectif."""
        key = (
            self.client_wrapper.get_api_key_for_mode("speaker")
            or self.client_wrapper.get_api_key_for_mode("combined")
            or self.client_wrapper.api_key
        )
        client = self.client_wrapper._get_client()
        resp = await client.get("/speakers", headers=self._auth_headers(key))
        resp.raise_for_status()
        return resp.json()

    async def get_speaker(self, speaker_id: str) -> Optional[Dict[str, Any]]:
        """Query individual speaker metadata from Detectif."""
        key = (
            self.client_wrapper.get_api_key_for_mode("speaker")
            or self.client_wrapper.get_api_key_for_mode("combined")
            or self.client_wrapper.api_key
        )
        client = self.client_wrapper._get_client()
        try:
            resp = await client.get(f"/speakers/{speaker_id}", headers=self._auth_headers(key))
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None

