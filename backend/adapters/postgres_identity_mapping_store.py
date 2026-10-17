"""
IntentLock — Postgres Identity Mapping & Session Store
Authoritative PostgreSQL implementation of speaker mappings, short-lived opaque sessions,
and turn delivery idempotency cache in Supabase.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.adapters.identity_mapping_store import SpeakerMappingRecord, VoiceSessionRecord
from backend.adapters.postgres_client import PostgresClient, sanitize_db_error
from backend.core.config import settings

logger = logging.getLogger("intentlock.postgres_identity_store")


class PostgresIdentityMappingStore:
    _instance: Optional["PostgresIdentityMappingStore"] = None

    def __init__(self, client: Optional[PostgresClient] = None):
        self.client = client or PostgresClient.get_instance()

    @classmethod
    def get_instance(cls, client: Optional[PostgresClient] = None) -> "PostgresIdentityMappingStore":
        if cls._instance is None:
            cls._instance = cls(client=client)
        return cls._instance

    # =========================================================================
    # Speaker Mappings
    # =========================================================================

    async def get_mapping_by_employee_id_async(self, employee_id: str) -> Optional[SpeakerMappingRecord]:
        if not employee_id:
            return None
        async with self.client.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM speaker_mappings WHERE employee_id = $1", employee_id.strip().upper()
            )
            if not row:
                return None
            return SpeakerMappingRecord(
                employee_id=row["employee_id"],
                account_alias=row["account_alias"],
                provider_speaker_id=row["provider_speaker_id"],
                display_name=row["display_name"],
                enrollment_status=row["enrollment_status"],
                sample_count=row["sample_count"],
                created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
                updated_at=row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row["updated_at"]),
            )

    def get_mapping_by_employee_id(self, employee_id: str) -> Optional[SpeakerMappingRecord]:
        return self.client.run(self.get_mapping_by_employee_id_async(employee_id))

    async def get_mapping_by_speaker_id_async(self, provider_speaker_id: str) -> Optional[SpeakerMappingRecord]:
        if not provider_speaker_id:
            return None
        async with self.client.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM speaker_mappings WHERE provider_speaker_id = $1", provider_speaker_id.strip()
            )
            if not row:
                return None
            return SpeakerMappingRecord(
                employee_id=row["employee_id"],
                account_alias=row["account_alias"],
                provider_speaker_id=row["provider_speaker_id"],
                display_name=row["display_name"],
                enrollment_status=row["enrollment_status"],
                sample_count=row["sample_count"],
                created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
                updated_at=row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row["updated_at"]),
            )

    def get_mapping_by_speaker_id(self, provider_speaker_id: str) -> Optional[SpeakerMappingRecord]:
        return self.client.run(self.get_mapping_by_speaker_id_async(provider_speaker_id))

    async def upsert_mapping_async(
        self,
        employee_id: str,
        provider_speaker_id: str,
        account_alias: str = "primary_account",
        display_name: Optional[str] = None,
        enrollment_status: str = "PENDING",
        sample_count: int = 0,
    ) -> SpeakerMappingRecord:
        now = datetime.now(timezone.utc)
        eid = employee_id.strip().upper()
        async with self.client.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO speaker_mappings (
                    employee_id, account_alias, provider_speaker_id, display_name,
                    enrollment_status, sample_count, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $7)
                ON CONFLICT (employee_id) DO UPDATE SET
                    account_alias = EXCLUDED.account_alias,
                    provider_speaker_id = EXCLUDED.provider_speaker_id,
                    display_name = EXCLUDED.display_name,
                    enrollment_status = EXCLUDED.enrollment_status,
                    sample_count = EXCLUDED.sample_count,
                    updated_at = EXCLUDED.updated_at
                """,
                eid, account_alias, provider_speaker_id, display_name, enrollment_status, sample_count, now
            )
        rec = await self.get_mapping_by_employee_id_async(eid)
        assert rec is not None
        return rec

    def upsert_mapping(
        self,
        employee_id: str,
        provider_speaker_id: str,
        account_alias: str = "primary_account",
        display_name: Optional[str] = None,
        enrollment_status: str = "PENDING",
        sample_count: int = 0,
    ) -> SpeakerMappingRecord:
        return self.client.run(
            self.upsert_mapping_async(employee_id, provider_speaker_id, account_alias, display_name, enrollment_status, sample_count)
        )

    async def list_mappings_async(self) -> List[SpeakerMappingRecord]:
        async with self.client.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM speaker_mappings ORDER BY employee_id ASC")
            return [
                SpeakerMappingRecord(
                    employee_id=r["employee_id"],
                    account_alias=r["account_alias"],
                    provider_speaker_id=r["provider_speaker_id"],
                    display_name=r["display_name"],
                    enrollment_status=r["enrollment_status"],
                    sample_count=r["sample_count"],
                    created_at=r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
                    updated_at=r["updated_at"].isoformat() if hasattr(r["updated_at"], "isoformat") else str(r["updated_at"]),
                )
                for r in rows
            ]

    def list_mappings(self) -> List[SpeakerMappingRecord]:
        return self.client.run(self.list_mappings_async())

    async def update_enrollment_status_async(
        self, employee_id: str, status: str, sample_count: Optional[int] = None
    ) -> bool:
        if not employee_id:
            return False
        now = datetime.now(timezone.utc)
        eid = employee_id.strip().upper()
        async with self.client.acquire() as conn:
            if sample_count is not None:
                res = await conn.execute(
                    """
                    UPDATE speaker_mappings
                    SET enrollment_status = $1, sample_count = $2, updated_at = $3
                    WHERE employee_id = $4
                    """,
                    status, sample_count, now, eid
                )
            else:
                res = await conn.execute(
                    """
                    UPDATE speaker_mappings
                    SET enrollment_status = $1, updated_at = $2
                    WHERE employee_id = $3
                    """,
                    status, now, eid
                )
            return bool(res and int(res.split()[-1]) > 0)

    def update_enrollment_status(
        self, employee_id: str, status: str, sample_count: Optional[int] = None
    ) -> bool:
        return self.client.run(self.update_enrollment_status_async(employee_id, status, sample_count))

    # =========================================================================
    # Voice Sessions
    # =========================================================================

    async def cleanup_expired_sessions_async(self) -> int:
        now = datetime.now(timezone.utc)
        async with self.client.acquire() as conn:
            res = await conn.execute(
                "UPDATE voice_sessions SET is_revoked = TRUE WHERE expires_at < $1 AND is_revoked = FALSE",
                now,
            )
            return int(res.split()[-1]) if res else 0

    def cleanup_expired_sessions(self) -> int:
        return self.client.run(self.cleanup_expired_sessions_async())

    async def create_session_async(
        self,
        session_id: str,
        employee_id: str,
        full_name: str,
        role: str,
        department: str,
        team_id: Optional[str] = None,
        account_alias: str = "primary_account",
        ttl_seconds: Optional[int] = None,
    ) -> VoiceSessionRecord:
        now = datetime.now(timezone.utc)
        ttl = ttl_seconds if ttl_seconds is not None else settings.SESSION_TTL_SECONDS
        expires_at = now + timedelta(seconds=ttl)
        sid = session_id.strip() if session_id else f"sess_{uuid.uuid4().hex}"
        eid = employee_id.strip().upper()

        async with self.client.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT is_revoked FROM voice_sessions WHERE session_id = $1", sid
            )
            if existing and existing["is_revoked"]:
                raise ValueError(f"Cannot resurrect revoked session: {sid}")

            await conn.execute(
                """
                INSERT INTO voice_sessions (
                    session_id, employee_id, full_name, role, department,
                    team_id, account_alias, created_at, last_verified_at, expires_at, is_revoked
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8, $9, FALSE)
                ON CONFLICT (session_id) DO UPDATE SET
                    employee_id = EXCLUDED.employee_id,
                    full_name = EXCLUDED.full_name,
                    role = EXCLUDED.role,
                    department = EXCLUDED.department,
                    team_id = EXCLUDED.team_id,
                    account_alias = EXCLUDED.account_alias,
                    last_verified_at = EXCLUDED.last_verified_at,
                    expires_at = EXCLUDED.expires_at,
                    is_revoked = FALSE
                """,
                sid, eid, full_name, role, department, team_id, account_alias, now, expires_at
            )

        return VoiceSessionRecord(
            session_id=sid,
            employee_id=eid,
            full_name=full_name,
            role=role,
            department=department,
            team_id=team_id,
            account_alias=account_alias,
            created_at=now.isoformat(),
            last_verified_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            is_revoked=False,
        )

    def create_session(
        self,
        session_id: str,
        employee_id: str,
        full_name: str,
        role: str,
        department: str,
        team_id: Optional[str] = None,
        account_alias: str = "primary_account",
        ttl_seconds: Optional[int] = None,
    ) -> VoiceSessionRecord:
        return self.client.run(
            self.create_session_async(session_id, employee_id, full_name, role, department, team_id, account_alias, ttl_seconds)
        )

    async def get_session_async(self, session_id: str) -> Optional[VoiceSessionRecord]:
        if not session_id:
            return None
        async with self.client.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM voice_sessions WHERE session_id = $1", session_id.strip()
            )
            if not row:
                return None
            return VoiceSessionRecord(
                session_id=row["session_id"],
                employee_id=row["employee_id"],
                full_name=row["full_name"],
                role=row["role"],
                department=row["department"],
                team_id=row["team_id"],
                account_alias=row["account_alias"],
                created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
                last_verified_at=row["last_verified_at"].isoformat() if row["last_verified_at"] and hasattr(row["last_verified_at"], "isoformat") else str(row["last_verified_at"]) if row["last_verified_at"] else None,
                expires_at=row["expires_at"].isoformat() if hasattr(row["expires_at"], "isoformat") else str(row["expires_at"]),
                is_revoked=bool(row["is_revoked"]),
            )

    def get_session(self, session_id: str) -> Optional[VoiceSessionRecord]:
        return self.client.run(self.get_session_async(session_id))

    async def refresh_session_async(
        self, session_id: str, ttl_seconds: Optional[int] = None, verified: bool = True
    ) -> Optional[VoiceSessionRecord]:
        if not session_id:
            return None
        ttl = ttl_seconds if ttl_seconds is not None else settings.SESSION_TTL_SECONDS
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl)
        async with self.client.acquire() as conn:
            if verified:
                res = await conn.execute(
                    """
                    UPDATE voice_sessions
                    SET expires_at = $1, last_verified_at = $2
                    WHERE session_id = $3 AND is_revoked = FALSE AND expires_at > $2
                    """,
                    expires, now, session_id.strip()
                )
            else:
                res = await conn.execute(
                    """
                    UPDATE voice_sessions
                    SET expires_at = $1
                    WHERE session_id = $2 AND is_revoked = FALSE AND expires_at > $3
                    """,
                    expires, session_id.strip(), now
                )
            if res and int(res.split()[-1]) > 0:
                return await self.get_session_async(session_id.strip())
        return None

    def refresh_session(
        self, session_id: str, ttl_seconds: Optional[int] = None, verified: bool = True
    ) -> Optional[VoiceSessionRecord]:
        return self.client.run(self.refresh_session_async(session_id, ttl_seconds, verified))

    async def touch_session_verification_async(self, session_id: str) -> Optional[VoiceSessionRecord]:
        now = datetime.now(timezone.utc)
        async with self.client.acquire() as conn:
            await conn.execute(
                "UPDATE voice_sessions SET last_verified_at = $1 WHERE session_id = $2",
                now, session_id.strip()
            )
        return await self.get_session_async(session_id)

    def touch_session_verification(self, session_id: str) -> Optional[VoiceSessionRecord]:
        return self.client.run(self.touch_session_verification_async(session_id))

    async def revoke_session_async(self, session_id: str) -> bool:
        if not session_id:
            return False
        async with self.client.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT employee_id FROM voice_sessions WHERE session_id = $1", session_id.strip()
            )
            res = await conn.execute(
                "UPDATE voice_sessions SET is_revoked = TRUE WHERE session_id = $1", session_id.strip()
            )
            count = int(res.split()[-1]) if res else 0
            if row:
                eid = row["employee_id"]
                await conn.execute("DELETE FROM idempotency_records WHERE employee_id = $1", eid)
            return count > 0

    def revoke_session(self, session_id: str) -> bool:
        return self.client.run(self.revoke_session_async(session_id))

    # =========================================================================
    # Idempotency Cache & Purge API
    # =========================================================================

    async def cleanup_expired_records_async(self, cutoff_seconds: int = 120) -> int:
        """Purges idempotency records older than cutoff_seconds."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=cutoff_seconds)
        async with self.client.acquire() as conn:
            res = await conn.execute(
                "DELETE FROM idempotency_records WHERE created_at < $1", cutoff
            )
            return int(res.split()[-1]) if res else 0

    def cleanup_expired_records(self, cutoff_seconds: int = 120) -> int:
        return self.client.run(self.cleanup_expired_records_async(cutoff_seconds))

    def purge_expired_idempotency_records(self, ttl_seconds: int = 120) -> int:
        """Backward-compatible alias for cleanup_expired_records."""
        return self.cleanup_expired_records(cutoff_seconds=ttl_seconds)

    async def save_idempotency_record_async(
        self,
        operation_key: str,
        audio_digest: str,
        employee_id: str,
        response_dict: Dict[str, Any],
    ) -> None:
        """Durable record of turn response for replay protection and idempotency."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=120)
        eid = (employee_id or "").strip().upper()
        resp_json = json.dumps(response_dict)
        async with self.client.acquire() as conn:
            await conn.execute("DELETE FROM idempotency_records WHERE created_at < $1", cutoff)
            await conn.execute(
                """
                INSERT INTO idempotency_records (operation_key, audio_digest, employee_id, response_json, created_at)
                VALUES ($1, $2, $3, $4::jsonb, $5)
                ON CONFLICT (operation_key) DO UPDATE SET
                    audio_digest = EXCLUDED.audio_digest,
                    employee_id = EXCLUDED.employee_id,
                    response_json = EXCLUDED.response_json,
                    created_at = EXCLUDED.created_at
                """,
                operation_key, audio_digest, eid, resp_json, now
            )

    def save_idempotency_record(
        self,
        operation_key: str,
        audio_digest: str,
        employee_id: str,
        response_dict: Dict[str, Any],
    ) -> None:
        return self.client.run(
            self.save_idempotency_record_async(operation_key, audio_digest, employee_id, response_dict)
        )

    def record_idempotency_response(
        self,
        operation_key: str,
        audio_digest: str,
        employee_id: str,
        response_data: dict,
    ) -> None:
        """Backward-compatible alias for save_idempotency_record."""
        return self.save_idempotency_record(operation_key, audio_digest, employee_id, response_data)

    async def get_idempotency_entry_async(self, operation_key: str) -> Optional[Dict[str, Any]]:
        if not operation_key:
            return None
        async with self.client.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT operation_key, audio_digest, employee_id, response_json, created_at FROM idempotency_records WHERE operation_key = $1",
                operation_key.strip()
            )
            if not row:
                return None
            created = row["created_at"]
            if isinstance(created, str):
                created_dt = datetime.fromisoformat(created)
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
            else:
                created_dt = created
            if created_dt + timedelta(seconds=120) <= datetime.now(timezone.utc):
                return None
            doc = row["response_json"]
            if isinstance(doc, str):
                doc = json.loads(doc)
            return {
                "operation_key": row["operation_key"],
                "audio_digest": row["audio_digest"],
                "employee_id": row["employee_id"],
                "response": doc,
                "created_at": created_dt.isoformat(),
            }

    def get_idempotency_entry(self, operation_key: str) -> Optional[Dict[str, Any]]:
        return self.client.run(self.get_idempotency_entry_async(operation_key))

    async def get_idempotency_record_async(self, operation_key: str) -> Optional[Dict[str, Any]]:
        entry = await self.get_idempotency_entry_async(operation_key)
        return entry["response"] if entry else None

    def get_idempotency_record(self, operation_key: str) -> Optional[Dict[str, Any]]:
        return self.client.run(self.get_idempotency_record_async(operation_key))
