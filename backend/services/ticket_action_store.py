"""SQLite ticket state, bound drafts, single-use grants, and committed events."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from backend.core.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def canonical(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class ActionError(ValueError):
    pass


class TicketActionStore:
    """One canonical ticket store. JSON fixtures seed it only on first boot."""

    def __init__(self, db_path: Optional[str] = None, seed_path: Optional[str] = None):
        self.db_path = db_path or settings.APP_DB_PATH
        self.seed_path = seed_path or os.path.join(settings.BASE_DIR, "backend", "data", "all_tickets.json")
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id TEXT PRIMARY KEY, version INTEGER NOT NULL, document TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS action_drafts (
                    draft_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                    operation TEXT NOT NULL, ticket_id TEXT NOT NULL, parameters TEXT NOT NULL,
                    expected_version INTEGER NOT NULL, payload_hash TEXT NOT NULL,
                    readback TEXT NOT NULL, expires_at TEXT NOT NULL, status TEXT NOT NULL,
                    receipt TEXT, proposal_digest TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_drafts_session ON action_drafts(session_id, status);
                CREATE TABLE IF NOT EXISTS action_grants (
                    grant_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL UNIQUE,
                    actor_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL, expected_version INTEGER NOT NULL,
                    expires_at TEXT NOT NULL, consumed_at TEXT,
                    FOREIGN KEY(draft_id) REFERENCES action_drafts(draft_id)
                );
                CREATE TABLE IF NOT EXISTS action_events (
                    event_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL UNIQUE,
                    ticket_id TEXT NOT NULL, actor_id TEXT NOT NULL, operation TEXT NOT NULL,
                    old_value TEXT, new_value TEXT, version INTEGER NOT NULL,
                    committed_at TEXT NOT NULL
                );
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(action_drafts)")}
            if "proposal_digest" not in columns:
                conn.execute("ALTER TABLE action_drafts ADD COLUMN proposal_digest TEXT")
            count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
            if count == 0:
                with open(self.seed_path, encoding="utf-8") as stream:
                    rows = json.load(stream)
                conn.executemany("INSERT INTO tickets(ticket_id,version,document) VALUES(?,1,?)",
                                 [(row["ticket_id"], canonical(row)) for row in rows])

    def list_tickets(self) -> List[dict]:
        with self._connect() as conn:
            return [json.loads(row[0]) for row in conn.execute("SELECT document FROM tickets ORDER BY ticket_id")]

    def get_ticket(self, ticket_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT document FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
            return json.loads(row[0]) if row else None

    @staticmethod
    def can_write(actor_id: str, ticket: dict, direct_report_ids: List[str]) -> bool:
        involved = {ticket.get(field) for field in ("requester_id", "assignee_id", "created_by")}
        involved.add(ticket.get("approval", {}).get("approver_id"))
        involved.add(ticket.get("escalation", {}).get("escalated_to"))
        return actor_id in involved or bool(set(direct_report_ids) & involved)

    @staticmethod
    def parse_proposal(operation: str, utterance: str, ticket_id: Optional[str]) -> Dict[str, str]:
        text = utterance.strip()
        if operation == "create_ticket":
            match = re.search(r"\b(?:ticket|issue)\s+(?:titled|called|about)\s+(.+)$", text, re.I)
            if not match or len(match.group(1).strip()) < 6:
                raise ActionError("Please say 'create a ticket titled' followed by a specific title.")
            return {"title": match.group(1).strip()[:160]}
        if not ticket_id:
            raise ActionError("Please include the exact ticket ID for this change.")
        if operation == "comment_ticket":
            match = re.search(r"\bcomment\s+(?:on|to)\s+TKT[-_ ]?\d{4}[-_ ]?\d{3}\s*(?::|saying|that)\s*(.+)$", text, re.I)
            if not match or not match.group(1).strip():
                raise ActionError("Please include the exact comment after the ticket ID.")
            return {"comment": match.group(1).strip()[:500]}
        if operation == "update_ticket":
            match = re.search(r"\b(priority|status|description)\s+(?:to|as)\s+(.+)$", text, re.I)
            if not match:
                raise ActionError("Please name the ticket field and its exact new value.")
            field, value = match.group(1).lower(), match.group(2).strip().rstrip(".")
            options = {"priority": ("Critical", "High", "Medium", "Low"),
                       "status": ("Open", "In Progress", "Pending", "Blocked", "Resolved", "Closed")}
            if field in options:
                value = next((candidate for candidate in options[field] if candidate.lower() == value.lower()), "")
                if not value:
                    raise ActionError(f"Unsupported {field} value. Please use a listed ticket value.")
            elif len(value) < 6 or len(value) > 500:
                raise ActionError("A description must contain 6 to 500 characters.")
            return {"field": field, "value": value}
        raise ActionError("This ticket action is unsupported.")

    def propose(self, actor_id: str, session_id: str, operation: str, ticket_id: Optional[str],
                params: dict, direct_report_ids: List[str], proposal_digest: str) -> dict:
        now = utcnow()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE action_drafts SET status='CANCELLED' WHERE session_id=? AND status='PENDING'", (session_id,))
            if operation == "create_ticket":
                prefix = f"TKT-{now.year}-"
                existing = [int(row[0][len(prefix):]) for row in conn.execute(
                    "SELECT ticket_id FROM tickets WHERE ticket_id LIKE ?", (prefix + "%",))
                    if row[0][len(prefix):].isdigit()]
                target = f"{prefix}{max(existing, default=0) + 1:03d}"
                version = 0
            else:
                target = ticket_id or ""
                row = conn.execute("SELECT version, document FROM tickets WHERE ticket_id=?", (target,)).fetchone()
                if not row or not self.can_write(actor_id, json.loads(row["document"]), direct_report_ids):
                    raise ActionError("This ticket is unavailable for the requested change.")
                version = row["version"]
                ticket = json.loads(row["document"])
                if operation == "update_ticket" and params["field"] == "status":
                    if ticket.get("status") == "Closed" or params["value"] == ticket.get("status"):
                        raise ActionError("That ticket status transition is unavailable.")
            draft_id = f"draft_{uuid.uuid4().hex}"
            manifest = {"actor": actor_id, "session": session_id, "operation": operation,
                        "ticket": target, "params": params, "version": version}
            payload_hash = hashlib.sha256(canonical(manifest).encode()).hexdigest()
            description = params.get("title") or params.get("comment") or f"{params.get('field')} to {params.get('value')}"
            readback = f"I confirm {operation.replace('_', ' ')} for {target}: {description}"
            expires = (now + timedelta(seconds=90)).isoformat()
            conn.execute("""INSERT INTO action_drafts
                (draft_id,session_id,actor_id,operation,ticket_id,parameters,expected_version,
                 payload_hash,readback,expires_at,status,receipt,proposal_digest)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL,?)""",
                (draft_id, session_id, actor_id, operation, target, canonical(params), version,
                 payload_hash, readback, expires, "PENDING", proposal_digest))
        return {"draft_id": draft_id, "operation": operation, "ticket_id": target,
                "params": params, "readback": readback, "expires_at": expires}

    def active_draft(self, session_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM action_drafts WHERE session_id=? AND status='PENDING' ORDER BY rowid DESC LIMIT 1", (session_id,)).fetchone()
            return dict(row) if row else None

    def cancel(self, session_id: str) -> bool:
        with self._connect() as conn:
            return conn.execute("UPDATE action_drafts SET status='CANCELLED' WHERE session_id=? AND status='PENDING'", (session_id,)).rowcount > 0

    def confirm(self, actor_id: str, session_id: str, spoken: str, evidence_digest: str,
                direct_report_ids: List[str]) -> dict:
        if not evidence_digest:
            raise ActionError("Fresh voice evidence is required for confirmation.")
        now = utcnow()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM action_drafts WHERE session_id=? ORDER BY rowid DESC LIMIT 1", (session_id,)).fetchone()
            if not row or row["actor_id"] != actor_id:
                raise ActionError("There is no pending action for this verified actor.")
            normalize = lambda value: re.sub(r"[^a-z0-9]+", "", value.lower())
            if normalize(spoken) != normalize(row["readback"]):
                raise ActionError("The spoken confirmation did not match the exact readback. No change was made.")
            if row["status"] == "COMMITTED" and row["receipt"]:
                return json.loads(row["receipt"])
            if row["status"] != "PENDING" or datetime.fromisoformat(row["expires_at"]) <= now:
                raise ActionError("The pending action was cancelled or expired.")
            if row["proposal_digest"] and row["proposal_digest"] == evidence_digest:
                raise ActionError("Please record a new spoken confirmation for this exact action.")
            params = json.loads(row["parameters"])
            operation = row["operation"]
            target = row["ticket_id"]
            old_value = None
            if operation == "create_ticket":
                new_ticket = {
                    "ticket_id": target, "title": params["title"], "description": params["title"],
                    "ticket_type": "Service Request", "category": "General", "status": "Open", "priority": "Medium",
                    "requester_id": actor_id, "assignee_id": None, "created_by": actor_id,
                    "department": "", "project": "", "created_at": now.isoformat(), "updated_at": now.isoformat(),
                    "comments": [], "activity_history": [],
                }
                new_version = 1
                new_value = params["title"]
                conn.execute("INSERT INTO tickets VALUES(?,?,?)", (target, new_version, canonical(new_ticket)))
            else:
                ticket_row = conn.execute("SELECT version,document FROM tickets WHERE ticket_id=?", (target,)).fetchone()
                if not ticket_row or ticket_row["version"] != row["expected_version"]:
                    raise ActionError("The ticket changed since readback. Please review a new proposal.")
                ticket = json.loads(ticket_row["document"])
                if not self.can_write(actor_id, ticket, direct_report_ids):
                    raise ActionError("This ticket is no longer available for the requested change.")
                if operation == "update_ticket":
                    field = params["field"]
                    old_value = ticket.get(field)
                    new_value = params["value"]
                    if field == "status" and ticket.get("status") == "Closed":
                        raise ActionError("That status transition is unavailable.")
                    ticket[field] = new_value
                    event_type = f"{field.upper()}_CHANGED"
                elif operation == "comment_ticket":
                    new_value = params["comment"]
                    ticket.setdefault("comments", []).append({"comment_id": f"COM-{uuid.uuid4().hex[:10]}",
                        "author_id": actor_id, "created_at": now.isoformat(), "comment": new_value})
                    event_type = "COMMENT"
                else:
                    raise ActionError("Unsupported ticket operation.")
                ticket["updated_at"] = now.isoformat()
                ticket.setdefault("activity_history", []).append({"timestamp": now.isoformat(), "type": event_type,
                    "actor": actor_id, "description": f"{operation} by {actor_id}",
                    "old_value": old_value, "new_value": new_value})
                new_version = ticket_row["version"] + 1
                conn.execute("UPDATE tickets SET version=?,document=? WHERE ticket_id=? AND version=?",
                             (new_version, canonical(ticket), target, ticket_row["version"]))
            grant_id = secrets.token_urlsafe(24)
            conn.execute("INSERT INTO action_grants VALUES(?,?,?,?,?,?,?,?)",
                (grant_id, row["draft_id"], actor_id, row["payload_hash"], evidence_digest,
                 row["expected_version"], (now + timedelta(seconds=30)).isoformat(), now.isoformat()))
            event_id = f"evt_{uuid.uuid4().hex}"
            conn.execute("INSERT INTO action_events VALUES(?,?,?,?,?,?,?,?,?)",
                (event_id, row["draft_id"], target, actor_id, operation,
                 old_value, new_value, new_version, now.isoformat()))
            receipt = {"operation_id": row["draft_id"], "tx_id": row["draft_id"],
                       "event_id": event_id, "grant_hash_prefix": row["payload_hash"][:12], "actor": actor_id,
                       "action": operation, "resource_id": target, "old_value": old_value,
                       "new_value": new_value, "version": new_version,
                       "timestamp": now.isoformat(), "status": "COMMITTED", "storage": "SQLite"}
            conn.execute("UPDATE action_drafts SET status='COMMITTED',receipt=? WHERE draft_id=?",
                         (canonical(receipt), row["draft_id"]))
            return receipt
