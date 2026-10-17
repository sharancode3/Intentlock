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


def normalize_readback(value: str) -> str:
    val = value.lower().strip()
    val = re.sub(r"[,!?;:\"'`\(\)\[\]{}]+", " ", val)
    # Remove periods only when they are not decimal points between digits
    val = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", val)
    # Normalize hyphens
    val = re.sub(r"\s+-\s+", " -", val)
    return re.sub(r"\s+", " ", val).strip()


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
    def build_typed_proposal(
        operation: str,
        ticket_id: Optional[str],
        field: Optional[str] = None,
        value: Optional[str] = None,
        utterance: Optional[str] = None,
    ) -> Dict[str, str]:
        if operation == "update_contact":
            phone_val = value or utterance or ""
            phone_match = re.search(r"(\+?[0-9\s\-\(\)\.]{3,30})", phone_val)
            if not phone_match:
                raise ActionError("Please provide a valid contact number (e.g. +91 98765 43210).")
            clean_phone = phone_match.group(1).strip()
            clean_phone = re.sub(r"\s+", " ", clean_phone)
            digits = re.sub(r"[^\d]", "", clean_phone)
            if len(digits) < 7 or len(digits) > 15:
                raise ActionError("Phone number must contain between 7 and 15 digits.")
            return {"field": "phone", "value": clean_phone}

        if operation == "create_ticket":
            if value and len(value.strip()) >= 6:
                return {"title": value.strip()[:160]}
            if utterance:
                return TicketActionStore.parse_proposal(operation, utterance, ticket_id)
            raise ActionError("Please say 'create a ticket titled' followed by a specific title.")

        text_source = utterance or value or ""

        if not ticket_id:
            raise ActionError("Please include the exact ticket ID for this change.")

        if operation == "comment_ticket":
            if value and not re.search(r"\b(comment|add|post|leave)\b", value, re.I):
                v = value.strip()[:500]
                if v:
                    return {"comment": v}
            if text_source:
                return TicketActionStore.parse_proposal(operation, text_source, ticket_id)
            raise ActionError("Please include the exact comment after the ticket ID.")

        if operation == "update_ticket":
            if field and value and not re.search(r"\b(change|update|set|mark)\b", value, re.I):
                f_norm = field.lower().strip()
                v_norm = value.strip().rstrip(".")
                options = {
                    "priority": ("Critical", "High", "Medium", "Low"),
                    "status": ("Open", "In Progress", "Pending", "Blocked", "Resolved", "Closed"),
                }
                if f_norm in options:
                    if f_norm == "priority" and v_norm.lower() in ("urgent", "highest", "sev-1", "s1"):
                        v_norm = "Critical"
                    elif f_norm == "priority" and v_norm.lower() == "normal":
                        v_norm = "Medium"
                    else:
                        v_norm = next((candidate for candidate in options[f_norm] if candidate.lower() == v_norm.lower()), "")
                    if v_norm:
                        return {"field": f_norm, "value": v_norm}
                elif 6 <= len(v_norm) <= 500:
                    return {"field": f_norm, "value": v_norm}

            if text_source:
                return TicketActionStore.parse_proposal(operation, text_source, ticket_id)
            raise ActionError("Please name the ticket field and its exact new value.")

        raise ActionError("This ticket action is unsupported.")

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
            match = re.search(r"\bcomment\s+(?:on|to)\s+(?:TKT[-_ ]?\d{4}[-_ ]?\d{3}|this ticket|it)\s*(?::|saying|that)\s*(.+)$", text, re.I)
            if not match:
                match = re.search(r"\b(?:add|post|leave)\s+(?:a\s+)?comment\s*(?::|saying|that)\s*(.+)$", text, re.I)
            if not match:
                match = re.search(r"\bcomment\s*:\s*(.+)$", text, re.I)
            if not match or not match.group(1).strip():
                raise ActionError("Please include the exact comment after the ticket ID.")
            return {"comment": match.group(1).strip()[:500]}
        if operation == "update_ticket":
            match = re.search(r"\b(priority|status|description)\s+(?:to|as)\s+(.+)$", text, re.I)
            if not match:
                mark_match = re.search(r"\bmark\s+(?:it|this ticket)?\s*(?:as)?\s+(resolved|closed|in progress|open|blocked)\b", text, re.I)
                if mark_match:
                    field = "status"
                    val_str = mark_match.group(1).strip()
                    val_map = {"resolved": "Resolved", "closed": "Closed", "in progress": "In Progress", "open": "Open", "blocked": "Blocked"}
                    return {"field": field, "value": val_map.get(val_str.lower(), val_str.title())}
                raise ActionError("Please name the ticket field and its exact new value.")
            field, value = match.group(1).lower(), match.group(2).strip().rstrip(".")
            options = {"priority": ("Critical", "High", "Medium", "Low"),
                       "status": ("Open", "In Progress", "Pending", "Blocked", "Resolved", "Closed")}
            if field in options:
                if field == "priority" and value.lower() in ("urgent", "highest", "sev-1", "s1"):
                    value = "Critical"
                elif field == "priority" and value.lower() == "normal":
                    value = "Medium"
                else:
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
            if operation == "update_contact":
                target = actor_id
                from backend.services.employee_knowledge_service import EmployeeKnowledgeService
                emp = EmployeeKnowledgeService.get_instance().get_employee_by_id(actor_id)
                if not emp:
                    raise ActionError("Employee record not found.")
                pol = emp.get("permissions", {}).get("profile_modification", {})
                if pol.get("effect") != "ALLOW":
                    raise ActionError("Policy denies profile modification for this employee.")
                version = emp.get("version", 1)
                description = f"phone to {params['value']}"
                readback = f"I confirm update contact for {target}: {description}"
            elif operation == "create_ticket":
                prefix = f"TKT-{now.year}-"
                committed = [int(row[0][len(prefix):]) for row in conn.execute(
                    "SELECT ticket_id FROM tickets WHERE ticket_id LIKE ?", (prefix + "%",))
                    if row[0][len(prefix):].isdigit()]
                pending = [int(row[0][len(prefix):]) for row in conn.execute(
                    "SELECT ticket_id FROM action_drafts WHERE status='PENDING' AND ticket_id LIKE ?", (prefix + "%",))
                    if row[0][len(prefix):].isdigit()]
                all_ids = committed + pending
                target = f"{prefix}{max(all_ids, default=0) + 1:03d}"
                version = 0
                description = params.get("title", "")
                readback = f"I confirm create ticket for {target}: {description}"
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
                description = params.get("comment") or f"{params.get('field')} to {params.get('value')}"
                readback = f"I confirm {operation.replace('_', ' ')} for {target}: {description}"
            draft_id = f"draft_{uuid.uuid4().hex}"
            expires = (now + timedelta(seconds=90)).isoformat()
            manifest = {
                "actor": actor_id,
                "session": session_id,
                "operation": operation,
                "ticket": target,
                "params": params,
                "version": version,
                "expires_at": expires,
                "readback": readback,
            }
            payload_hash = hashlib.sha256(canonical(manifest).encode()).hexdigest()
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
            if normalize_readback(spoken) != normalize_readback(row["readback"]):
                raise ActionError("The spoken confirmation did not match the exact readback. No change was made.")
            if row["status"] == "COMMITTED" and row["receipt"]:
                return json.loads(row["receipt"])
            exp_dt = datetime.fromisoformat(row["expires_at"])
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if row["status"] != "PENDING" or exp_dt <= now:
                raise ActionError("The pending action was cancelled or expired.")
            if row["proposal_digest"] and row["proposal_digest"] == evidence_digest:
                raise ActionError("Please record a new spoken confirmation for this exact action.")
            params = json.loads(row["parameters"])
            operation = row["operation"]
            target = row["ticket_id"]
            expected_version = row["expected_version"]

            # Recompute and verify the canonical manifest hash including expiry and readback
            expected_manifest = {
                "actor": row["actor_id"],
                "session": row["session_id"],
                "operation": operation,
                "ticket": target,
                "params": params,
                "version": expected_version,
                "expires_at": row["expires_at"],
                "readback": row["readback"],
            }
            recomputed_hash = hashlib.sha256(canonical(expected_manifest).encode()).hexdigest()
            if recomputed_hash != row["payload_hash"]:
                raise ActionError("The action proposal manifest integrity verification failed. Parameters or metadata have been modified.")

            # Planned executor boundary: Validate and record authorization grant BEFORE mutation
            grant_id = secrets.token_urlsafe(24)
            grant_expires = (now + timedelta(seconds=30)).isoformat()
            conn.execute("""INSERT INTO action_grants
                (grant_id, draft_id, actor_id, payload_hash, evidence_digest, expected_version, expires_at, consumed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
                (grant_id, row["draft_id"], actor_id, row["payload_hash"], evidence_digest,
                 expected_version, grant_expires))

            old_value = None
            if operation == "update_contact":
                from backend.services.employee_knowledge_service import EmployeeKnowledgeService
                emp = EmployeeKnowledgeService.get_instance().get_employee_by_id(actor_id)
                if not emp:
                    raise ActionError("Employee record not found.")
                pol = emp.get("permissions", {}).get("profile_modification", {})
                if pol.get("effect") != "ALLOW":
                    raise ActionError("Policy denies profile modification for this employee.")
                new_version = expected_version + 1
                new_value = params["value"]
            elif operation == "create_ticket":
                new_ticket = {
                    "ticket_id": target, "title": params["title"], "description": params["title"],
                    "ticket_type": "Service Request", "category": "General", "status": "Open", "priority": "Medium",
                    "requester_id": actor_id, "assignee_id": None, "created_by": actor_id,
                    "department": "", "project": "", "created_at": now.isoformat(), "updated_at": now.isoformat(),
                    "comments": [], "activity_history": [],
                }
                new_version = 1
                new_value = params["title"]
                try:
                    conn.execute("INSERT INTO tickets VALUES(?,?,?)", (target, new_version, canonical(new_ticket)))
                except sqlite3.IntegrityError:
                    raise ActionError(f"Ticket {target} already exists or conflicted during commit. Please make a fresh proposal.")
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

            # Mark grant consumed upon successful mutation commit
            conn.execute("UPDATE action_grants SET consumed_at = ? WHERE grant_id = ?", (now.isoformat(), grant_id))

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
