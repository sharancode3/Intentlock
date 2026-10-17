"""
IntentLock — Durable Identity Mapping & Session Store
Local SQLite store for mapping canonical employee IDs to Detectif speaker IDs,
tracking enrollment status, and managing short-lived opaque voice sessions.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from backend.core.config import settings

logger = logging.getLogger("intentlock.identity_store")


class SpeakerMappingRecord(BaseModel):
    employee_id: str
    account_alias: str
    provider_speaker_id: str
    display_name: Optional[str] = None
    enrollment_status: str = "PENDING"  # PENDING, ENROLLED, REJECTED
    sample_count: int = 0
    created_at: str
    updated_at: str


class VoiceSessionRecord(BaseModel):
    session_id: str
    employee_id: str
    full_name: str
    role: str
    department: str
    team_id: Optional[str] = None
    account_alias: str = "primary_account"
    created_at: str
    last_verified_at: Optional[str] = None
    expires_at: str
    is_revoked: bool = False

    @property
    def is_expired(self) -> bool:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) >= exp
        except Exception:
            return True

    @property
    def is_valid(self) -> bool:
        return (not self.is_revoked) and (not self.is_expired)

    @property
    def seconds_remaining(self) -> int:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            rem = (exp - datetime.now(timezone.utc)).total_seconds()
            return max(0, int(rem))
        except Exception:
            return 0


class IdentityMappingStore:
    _instance: Optional["IdentityMappingStore"] = None

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.MAPPING_DB_PATH
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> Any:
        if db_path is None and settings.STORAGE_BACKEND == "postgres":
            from backend.adapters.postgres_identity_mapping_store import PostgresIdentityMappingStore
            return PostgresIdentityMappingStore.get_instance()
        if cls._instance is None:
            cls._instance = cls(db_path=db_path)
        return cls._instance

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS speaker_mappings (
                    employee_id TEXT PRIMARY KEY,
                    account_alias TEXT NOT NULL,
                    provider_speaker_id TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    enrollment_status TEXT NOT NULL DEFAULT 'PENDING',
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS voice_sessions (
                    session_id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    department TEXT NOT NULL,
                    team_id TEXT,
                    account_alias TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_verified_at TEXT,
                    expires_at TEXT NOT NULL,
                    is_revoked INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (employee_id) REFERENCES speaker_mappings(employee_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS idempotency_records (
                    operation_key TEXT PRIMARY KEY,
                    audio_digest TEXT NOT NULL,
                    employee_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_expires ON voice_sessions(expires_at);
                CREATE INDEX IF NOT EXISTS idx_mappings_speaker ON speaker_mappings(provider_speaker_id);
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(voice_sessions)")}
            if "last_verified_at" not in columns:
                conn.execute("ALTER TABLE voice_sessions ADD COLUMN last_verified_at TEXT")
                conn.execute("UPDATE voice_sessions SET last_verified_at=created_at WHERE last_verified_at IS NULL")

    # =========================================================================
    # Speaker Mappings API
    # =========================================================================

    def upsert_mapping(
        self,
        employee_id: str,
        provider_speaker_id: str,
        account_alias: str = "primary_account",
        display_name: Optional[str] = None,
        enrollment_status: str = "PENDING",
        sample_count: int = 0,
    ) -> SpeakerMappingRecord:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO speaker_mappings (
                    employee_id, account_alias, provider_speaker_id, display_name,
                    enrollment_status, sample_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(employee_id) DO UPDATE SET
                    account_alias = excluded.account_alias,
                    provider_speaker_id = excluded.provider_speaker_id,
                    display_name = excluded.display_name,
                    enrollment_status = excluded.enrollment_status,
                    sample_count = excluded.sample_count,
                    updated_at = excluded.updated_at
                """,
                (
                    employee_id,
                    account_alias,
                    provider_speaker_id,
                    display_name,
                    enrollment_status,
                    sample_count,
                    now,
                    now,
                ),
            )
        return self.get_mapping_by_employee_id(employee_id)  # type: ignore

    def get_mapping_by_employee_id(self, employee_id: str) -> Optional[SpeakerMappingRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM speaker_mappings WHERE employee_id = ?",
                (employee_id,),
            ).fetchone()
            if row:
                return SpeakerMappingRecord(**dict(row))
        return None

    def get_mapping_by_speaker_id(self, provider_speaker_id: str) -> Optional[SpeakerMappingRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM speaker_mappings WHERE provider_speaker_id = ?",
                (provider_speaker_id,),
            ).fetchone()
            if row:
                return SpeakerMappingRecord(**dict(row))
        return None

    def list_mappings(self) -> List[SpeakerMappingRecord]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM speaker_mappings ORDER BY employee_id ASC").fetchall()
            return [SpeakerMappingRecord(**dict(r)) for r in rows]

    def update_enrollment_status(
        self,
        employee_id: str,
        status: str,
        sample_count: Optional[int] = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            if sample_count is not None:
                cur = conn.execute(
                    """
                    UPDATE speaker_mappings
                    SET enrollment_status = ?, sample_count = ?, updated_at = ?
                    WHERE employee_id = ?
                    """,
                    (status, sample_count, now, employee_id),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE speaker_mappings
                    SET enrollment_status = ?, updated_at = ?
                    WHERE employee_id = ?
                    """,
                    (status, now, employee_id),
                )
            return cur.rowcount > 0

    # =========================================================================
    # Voice Session API
    # =========================================================================

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
        ttl = ttl_seconds or settings.SESSION_TTL_SECONDS
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl)
        now_str = now.isoformat()
        exp_str = expires.isoformat()

        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT is_revoked FROM voice_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if existing and existing["is_revoked"]:
                raise ValueError(f"Cannot resurrect revoked session: {session_id}")

            conn.execute(
                """
                INSERT OR REPLACE INTO voice_sessions (
                    session_id, employee_id, full_name, role, department,
                    team_id, account_alias, created_at, last_verified_at, expires_at, is_revoked
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    session_id,
                    employee_id,
                    full_name,
                    role,
                    department,
                    team_id,
                    account_alias,
                    now_str,
                    now_str,
                    exp_str,
                ),
            )
        return VoiceSessionRecord(
            session_id=session_id,
            employee_id=employee_id,
            full_name=full_name,
            role=role,
            department=department,
            team_id=team_id,
            account_alias=account_alias,
            created_at=now_str,
            last_verified_at=now_str,
            expires_at=exp_str,
            is_revoked=False,
        )

    def get_session(self, session_id: str) -> Optional[VoiceSessionRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM voice_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row:
                return VoiceSessionRecord(
                    session_id=row["session_id"],
                    employee_id=row["employee_id"],
                    full_name=row["full_name"],
                    role=row["role"],
                    department=row["department"],
                    team_id=row["team_id"],
                    account_alias=row["account_alias"],
                    created_at=row["created_at"],
                    last_verified_at=row["last_verified_at"],
                    expires_at=row["expires_at"],
                    is_revoked=bool(row["is_revoked"]),
                )
        return None

    def refresh_session(self, session_id: str, ttl_seconds: Optional[int] = None, verified: bool = True) -> Optional[VoiceSessionRecord]:
        ttl = ttl_seconds or settings.SESSION_TTL_SECONDS
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(seconds=ttl)).isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE voice_sessions
                SET expires_at = ?, last_verified_at = CASE WHEN ? THEN ? ELSE last_verified_at END
                WHERE session_id = ? AND is_revoked = 0 AND expires_at > ?
                """,
                (expires, int(verified), now.isoformat(), session_id, now.isoformat()),
            )
            if cur.rowcount > 0:
                return self.get_session(session_id)
        return None

    def revoke_session(self, session_id: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT employee_id FROM voice_sessions WHERE session_id = ?", (session_id,)).fetchone()
            emp_id = row["employee_id"] if row else None
            cur = conn.execute(
                "UPDATE voice_sessions SET is_revoked = 1 WHERE session_id = ?",
                (session_id,),
            )
            now_dt = datetime.now(timezone.utc)
            cutoff = (now_dt - timedelta(seconds=120)).isoformat()
            conn.execute("DELETE FROM idempotency_records WHERE created_at < ?", (cutoff,))
            if emp_id:
                conn.execute("DELETE FROM idempotency_records WHERE employee_id = ?", (emp_id,))
            return cur.rowcount > 0

    def cleanup_expired_records(self, cutoff_seconds: int = 120) -> int:
        """Purges idempotency records older than cutoff_seconds."""
        now_dt = datetime.now(timezone.utc)
        cutoff = (now_dt - timedelta(seconds=cutoff_seconds)).isoformat()
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM idempotency_records WHERE created_at < ?", (cutoff,))
            return cur.rowcount

    # =========================================================================
    # Idempotency Cache API
    # =========================================================================

    def get_idempotency_entry(self, operation_key: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT audio_digest, employee_id, response_json, created_at FROM idempotency_records WHERE operation_key = ?",
                (operation_key,),
            ).fetchone()
            if row:
                try:
                    if datetime.fromisoformat(row["created_at"]) + timedelta(seconds=120) <= datetime.now(timezone.utc):
                        return None
                    return {"audio_digest": row["audio_digest"], "employee_id": row["employee_id"],
                            "response": json.loads(row["response_json"])}
                except Exception:
                    return None
        return None

    def get_idempotency_record(self, operation_key: str) -> Optional[Dict[str, Any]]:
        """Backward-compatible response lookup for existing callers."""
        entry = self.get_idempotency_entry(operation_key)
        return entry["response"] if entry else None

    def save_idempotency_record(
        self,
        operation_key: str,
        audio_digest: str,
        employee_id: str,
        response_dict: Dict[str, Any],
    ) -> None:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        cutoff = (now_dt - timedelta(seconds=120)).isoformat()
        with self._get_connection() as conn:
            conn.execute("DELETE FROM idempotency_records WHERE created_at < ?", (cutoff,))
            conn.execute(
                """
                INSERT OR REPLACE INTO idempotency_records (
                    operation_key, audio_digest, employee_id, response_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (operation_key, audio_digest, employee_id, json.dumps(response_dict), now),
            )
