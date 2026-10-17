"""
IntentLock — Supabase Postgres Protected Ticket Action Store
Transactional PostgreSQL implementation of:
1. Atomic proposal drafting with SHA256 canonical manifest integrity hashes.
2. Exact-readback and single-use ActionGrant minting before mutation.
3. Protected execution boundary enforcing version concurrency and RLS scoping.
4. Committed action audit events and directory revision invalidation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.adapters.postgres_client import PostgresClient
from backend.services.ticket_action_store import (
    ActionError,
    canonical,
    normalize_readback,
    utcnow,
)

logger = logging.getLogger("intentlock.postgres_ticket_store")

TICKET_CREATE_LOCK_ID = 0x544B5431  # "TKT1" in hex


class PostgresTicketActionStore:
    _instance: Optional["PostgresTicketActionStore"] = None

    def __init__(self, client: Optional[PostgresClient] = None):
        self.client = client or PostgresClient.get_instance()

    @classmethod
    def get_instance(cls, client: Optional[PostgresClient] = None) -> "PostgresTicketActionStore":
        if cls._instance is None:
            cls._instance = cls(client=client)
        return cls._instance

    # =========================================================================
    # Ticket Retrieval
    # =========================================================================

    async def list_tickets_async(self) -> List[dict]:
        async with self.client.acquire() as conn:
            rows = await conn.fetch("SELECT document FROM tickets ORDER BY ticket_id ASC")
            res = []
            for r in rows:
                doc = r["document"]
                if isinstance(doc, str):
                    doc = json.loads(doc)
                res.append(doc)
            return res

    def list_tickets(self) -> List[dict]:
        return self.client.run(self.list_tickets_async())

    async def get_ticket_async(self, ticket_id: str) -> Optional[dict]:
        if not ticket_id:
            return None
        async with self.client.acquire() as conn:
            row = await conn.fetchrow("SELECT document FROM tickets WHERE ticket_id = $1", ticket_id.strip())
            if not row:
                return None
            doc = row["document"]
            return json.loads(doc) if isinstance(doc, str) else doc

    def get_ticket(self, ticket_id: str) -> Optional[dict]:
        return self.client.run(self.get_ticket_async(ticket_id))

    # =========================================================================
    # Write Authorization
    # =========================================================================

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
        # Protected contact update proposal
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
            raw_title = value or utterance or "New support ticket"
            clean_title = re.sub(r"^(please\s+)?(create\s+(a\s+)?ticket\s+(for\s+|about\s+|titled\s+)?|log\s+(a\s+)?ticket\s+)", "", raw_title, flags=re.I).strip()
            if not clean_title:
                clean_title = "Support request"
            return {"title": clean_title[:100]}

        if operation == "update_ticket":
            f = field or "status"
            v = value or ""
            if f == "status":
                v_lower = v.lower()
                status_map = {
                    "open": "Open", "reopen": "Open", "reopened": "Open",
                    "in progress": "In Progress", "progress": "In Progress",
                    "escalated": "Escalated", "escalate": "Escalated",
                    "resolved": "Resolved", "resolve": "Resolved",
                    "closed": "Closed", "close": "Closed",
                }
                v_clean = status_map.get(v_lower)
                if not v_clean:
                    for k, val in status_map.items():
                        if k in v_lower:
                            v_clean = val
                            break
                if not v_clean:
                    raise ActionError(f"Invalid status value: {v}. Valid statuses are: Open, In Progress, Escalated, Resolved, Closed.")
                return {"field": "status", "value": v_clean}
            elif f == "priority":
                p_lower = v.lower()
                p_map = {"low": "Low", "medium": "Medium", "high": "High", "critical": "Critical", "urgent": "Critical"}
                p_clean = p_map.get(p_lower)
                if not p_clean:
                    for k, val in p_map.items():
                        if k in p_lower:
                            p_clean = val
                            break
                if not p_clean:
                    raise ActionError(f"Invalid priority value: {v}. Valid priorities are: Low, Medium, High, Critical.")
                return {"field": "priority", "value": p_clean}
            elif f == "assignee":
                m = re.search(r"EMP-\d{4}", v, re.I)
                if not m:
                    raise ActionError("Assignee must be a valid employee ID (e.g., EMP-1002).")
                return {"field": "assignee_id", "value": m.group(0).upper()}
            else:
                return {"field": f, "value": v}

        if operation == "comment_ticket":
            comment_text = value or utterance or ""
            clean_comment = re.sub(r"^(please\s+)?(add\s+(a\s+)?comment(\s+saying|\s+to\s+ticket|\s+that)?|comment\s+)", "", comment_text, flags=re.I).strip()
            if not clean_comment:
                raise ActionError("Comment text cannot be empty.")
            return {"comment": clean_comment[:500]}

        raise ActionError(f"Unsupported action operation: {operation}")

    # =========================================================================
    # Proposal Drafting
    # =========================================================================

    async def propose_async(
        self,
        actor_id: str,
        session_id: str,
        operation: str,
        ticket_id: Optional[str],
        params: dict,
        direct_report_ids: List[str],
        proposal_digest: str,
    ) -> dict:
        now = utcnow()
        async with self.client.transaction(actor_id=actor_id) as conn:
            # Cancel any previous pending draft for this session
            await conn.execute(
                "UPDATE action_drafts SET status = 'CANCELLED' WHERE session_id = $1 AND status = 'PENDING'",
                session_id,
            )

            if operation == "update_contact":
                target = actor_id  # self-contact only
                emp_row = await conn.fetchrow(
                    "SELECT version, policy FROM employees WHERE employee_id = $1", target
                )
                if not emp_row:
                    raise ActionError("Employee record not found.")
                pol = emp_row["policy"]
                if isinstance(pol, str):
                    pol = json.loads(pol)
                if pol.get("profile_modification", {}).get("effect") != "ALLOW":
                    raise ActionError("Policy denies editing contact details for this employee.")
                version = emp_row["version"]
                description = f"phone to {params['value']}"
                readback = f"I confirm update contact for {target}: {description}"

            elif operation == "create_ticket":
                await conn.execute("SELECT pg_advisory_xact_lock($1)", TICKET_CREATE_LOCK_ID)
                prefix = f"TKT-{now.year}-"
                max_comm = await conn.fetchval(
                    "SELECT MAX(SUBSTRING(ticket_id FROM 10)::int) FROM tickets WHERE ticket_id LIKE $1",
                    prefix + "%",
                )
                max_pend = await conn.fetchval(
                    "SELECT MAX(SUBSTRING(ticket_id FROM 10)::int) FROM action_drafts WHERE status = 'PENDING' AND ticket_id LIKE $1",
                    prefix + "%",
                )
                highest = max(max_comm or 0, max_pend or 0)
                target = f"{prefix}{highest + 1:03d}"
                version = 0
                description = params.get("title", "")
                readback = f"I confirm create ticket for {target}: {description}"

            else:
                target = ticket_id or ""
                trow = await conn.fetchrow(
                    "SELECT version, document FROM tickets WHERE ticket_id = $1", target
                )
                if not trow:
                    raise ActionError("This ticket is unavailable for the requested change.")
                doc = trow["document"]
                if isinstance(doc, str):
                    doc = json.loads(doc)
                if not self.can_write(actor_id, doc, direct_report_ids):
                    raise ActionError("This ticket is unavailable for the requested change.")
                version = trow["version"]
                if operation == "update_ticket" and params.get("field") == "status":
                    if doc.get("status") == "Closed" or params.get("value") == doc.get("status"):
                        raise ActionError("That ticket status transition is unavailable.")
                description = params.get("comment") or f"{params.get('field')} to {params.get('value')}"
                readback = f"I confirm {operation.replace('_', ' ')} for {target}: {description}"

            draft_id = f"draft_{uuid.uuid4().hex}"
            now_dt = now.replace(microsecond=0)
            exp_dt = (now_dt + timedelta(seconds=90)).replace(microsecond=0)
            expires_str = exp_dt.isoformat()
            manifest = {
                "actor": actor_id,
                "session": session_id,
                "operation": operation,
                "ticket": target,
                "params": params,
                "version": version,
                "expires_at": expires_str,
                "readback": readback,
            }
            payload_hash = hashlib.sha256(canonical(manifest).encode()).hexdigest()

            await conn.execute(
                """
                INSERT INTO action_drafts (
                    draft_id, session_id, actor_id, operation, ticket_id,
                    parameters, expected_version, payload_hash, readback,
                    expires_at, status, receipt, proposal_digest
                ) VALUES (
                    $1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, 'PENDING', NULL, $11
                )
                """,
                draft_id,
                session_id,
                actor_id,
                operation,
                target,
                canonical(params),
                version,
                payload_hash,
                readback,
                exp_dt,
                proposal_digest,
            )

        return {
            "draft_id": draft_id,
            "operation": operation,
            "ticket_id": target,
            "params": params,
            "readback": readback,
            "expires_at": expires_str,
        }

    def propose(
        self,
        actor_id: str,
        session_id: str,
        operation: str,
        ticket_id: Optional[str],
        params: dict,
        direct_report_ids: List[str],
        proposal_digest: str,
    ) -> dict:
        return self.client.run(
            self.propose_async(actor_id, session_id, operation, ticket_id, params, direct_report_ids, proposal_digest)
        )

    # =========================================================================
    # Action Confirmation & Atomic Execution
    # =========================================================================

    async def confirm_async(
        self,
        actor_id: str,
        session_id: str,
        spoken: str,
        evidence_digest: str,
        direct_report_ids: List[str],
    ) -> dict:
        now = utcnow()
        async with self.client.transaction(actor_id=actor_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT draft_id, session_id, actor_id, operation, ticket_id,
                       parameters, expected_version, payload_hash, readback,
                       expires_at, status, receipt, proposal_digest
                FROM action_drafts
                WHERE session_id = $1
                ORDER BY expires_at DESC LIMIT 1
                """,
                session_id,
            )
            if not row or row["actor_id"] != actor_id:
                raise ActionError("There is no pending action for this verified actor.")

            if normalize_readback(spoken) != normalize_readback(row["readback"]):
                raise ActionError("The spoken confirmation did not match the exact readback. No change was made.")

            # Idempotent repeated confirmation
            if row["status"] == "COMMITTED" and row["receipt"]:
                receipt_data = row["receipt"]
                return json.loads(receipt_data) if isinstance(receipt_data, str) else receipt_data

            raw_exp = row["expires_at"]
            if isinstance(raw_exp, datetime):
                exp_dt = raw_exp if raw_exp.tzinfo else raw_exp.replace(tzinfo=timezone.utc)
                expires_str = exp_dt.isoformat()
            else:
                expires_str = str(raw_exp)
                exp_dt = datetime.fromisoformat(expires_str)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)

            if row["status"] != "PENDING" or exp_dt <= now:
                raise ActionError("The pending action was cancelled or expired.")

            if row["proposal_digest"] and row["proposal_digest"] == evidence_digest:
                raise ActionError("Please record a new spoken confirmation for this exact action.")

            params = row["parameters"]
            if isinstance(params, str):
                params = json.loads(params)
            operation = row["operation"]
            target = row["ticket_id"]
            expected_version = row["expected_version"]

            # Recompute and verify canonical manifest hash
            expected_manifest = {
                "actor": row["actor_id"],
                "session": row["session_id"],
                "operation": operation,
                "ticket": target,
                "params": params,
                "version": expected_version,
                "expires_at": expires_str,
                "readback": row["readback"],
            }
            recomputed_hash = hashlib.sha256(canonical(expected_manifest).encode()).hexdigest()
            if recomputed_hash != row["payload_hash"]:
                raise ActionError(
                    "The action proposal manifest integrity verification failed. Parameters or metadata have been modified."
                )

            # Planned executor boundary: Insert single-use authorization grant BEFORE mutation
            grant_id = secrets.token_urlsafe(24)
            grant_exp_dt = (now + timedelta(seconds=30)).replace(microsecond=0)
            await conn.execute(
                """
                INSERT INTO action_grants (
                    grant_id, draft_id, actor_id, payload_hash, evidence_digest,
                    expected_version, expires_at, consumed_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, NULL)
                """,
                grant_id,
                row["draft_id"],
                actor_id,
                row["payload_hash"],
                evidence_digest,
                expected_version,
                grant_exp_dt,
            )

            old_value = None
            new_value = None
            new_version = expected_version + 1

            if operation == "update_contact":
                # Protected employee self-contact edit
                emp_row = await conn.fetchrow(
                    "SELECT version, work_phone, policy FROM employees WHERE employee_id = $1 FOR UPDATE",
                    target,
                )
                if not emp_row or emp_row["version"] != expected_version:
                    raise ActionError("The employee record was modified since readback. Please make a fresh proposal.")

                pol = emp_row["policy"]
                if isinstance(pol, str):
                    pol = json.loads(pol)
                if pol.get("profile_modification", {}).get("effect") != "ALLOW":
                    raise ActionError("Policy denies editing contact details for this employee.")

                old_value = emp_row["work_phone"]
                new_value = params["value"]
                new_version = emp_row["version"] + 1

                await conn.execute(
                    """
                    UPDATE employees
                    SET work_phone = $1, version = $2, updated_at = NOW()
                    WHERE employee_id = $3 AND version = $4
                    """,
                    new_value,
                    new_version,
                    target,
                    emp_row["version"],
                )

                # Bump directory revision
                await conn.execute(
                    """
                    INSERT INTO directory_metadata (key, revision, updated_at)
                    VALUES ('directory_revision', 2, NOW())
                    ON CONFLICT (key) DO UPDATE
                    SET revision = directory_metadata.revision + 1, updated_at = NOW()
                    """
                )

            elif operation == "create_ticket":
                new_version = 1
                new_value = params["title"]
                new_ticket = {
                    "ticket_id": target,
                    "title": params["title"],
                    "description": params["title"],
                    "ticket_type": "Service Request",
                    "category": "General",
                    "status": "Open",
                    "priority": "Medium",
                    "requester_id": actor_id,
                    "assignee_id": None,
                    "created_by": actor_id,
                    "department": "",
                    "project": "",
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "comments": [],
                    "activity_history": [],
                }
                await conn.execute(
                    """
                    INSERT INTO tickets (
                        ticket_id, version, title, description, ticket_type, category,
                        status, priority, requester_id, assignee_id, created_by,
                        department, project, document, created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, NOW(), NOW()
                    )
                    """,
                    target,
                    new_version,
                    new_ticket["title"],
                    new_ticket["description"],
                    new_ticket["ticket_type"],
                    new_ticket["category"],
                    new_ticket["status"],
                    new_ticket["priority"],
                    new_ticket["requester_id"],
                    new_ticket["assignee_id"],
                    new_ticket["created_by"],
                    new_ticket["department"],
                    new_ticket["project"],
                    canonical(new_ticket),
                )

            else:
                trow = await conn.fetchrow(
                    "SELECT version, document FROM tickets WHERE ticket_id = $1 FOR UPDATE",
                    target,
                )
                if not trow or trow["version"] != expected_version:
                    raise ActionError("The ticket changed since readback. Please review a new proposal.")
                ticket = trow["document"]
                if isinstance(ticket, str):
                    ticket = json.loads(ticket)
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
                    ticket.setdefault("comments", []).append({
                        "comment_id": f"COM-{uuid.uuid4().hex[:10]}",
                        "author_id": actor_id,
                        "created_at": now.isoformat(),
                        "comment": new_value,
                    })
                    event_type = "COMMENT"
                else:
                    raise ActionError("Unsupported ticket operation.")

                ticket["updated_at"] = now.isoformat()
                ticket.setdefault("activity_history", []).append({
                    "timestamp": now.isoformat(),
                    "type": event_type,
                    "actor": actor_id,
                    "description": f"{operation} by {actor_id}",
                    "old_value": old_value,
                    "new_value": new_value,
                })
                new_version = trow["version"] + 1

                await conn.execute(
                    """
                    UPDATE tickets
                    SET version = $1, document = $2::jsonb, status = $3, priority = $4, updated_at = NOW()
                    WHERE ticket_id = $5 AND version = $6
                    """,
                    new_version,
                    canonical(ticket),
                    ticket.get("status", "Open"),
                    ticket.get("priority", "Medium"),
                    target,
                    trow["version"],
                )

            # Bump ticket revision in directory_metadata for cross-worker cache invalidation
            await conn.execute(
                """
                INSERT INTO directory_metadata (key, revision, updated_at)
                VALUES ('ticket_revision', 2, NOW())
                ON CONFLICT (key) DO UPDATE
                SET revision = directory_metadata.revision + 1, updated_at = NOW()
                """
            )

            # Consume grant atomically
            await conn.execute(
                "UPDATE action_grants SET consumed_at = NOW() WHERE grant_id = $1", grant_id
            )

            # Record committed action audit event
            event_id = f"evt_{uuid.uuid4().hex}"
            await conn.execute(
                """
                INSERT INTO action_events (
                    event_id, draft_id, ticket_id, actor_id, operation,
                    old_value, new_value, version, committed_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                """,
                event_id,
                row["draft_id"],
                target,
                actor_id,
                operation,
                str(old_value) if old_value is not None else None,
                str(new_value) if new_value is not None else None,
                new_version,
            )

            receipt = {
                "operation_id": row["draft_id"],
                "tx_id": row["draft_id"],
                "event_id": event_id,
                "grant_hash_prefix": row["payload_hash"][:12],
                "actor": actor_id,
                "action": operation,
                "resource_id": target,
                "old_value": old_value,
                "new_value": new_value,
                "version": new_version,
                "timestamp": now.isoformat(),
                "status": "COMMITTED",
                "storage": "Postgres",
            }

            await conn.execute(
                "UPDATE action_drafts SET status = 'COMMITTED', receipt = $1::jsonb WHERE draft_id = $2",
                canonical(receipt),
                row["draft_id"],
            )

            return receipt

    def confirm(
        self,
        actor_id: str,
        session_id: str,
        spoken: str,
        evidence_digest: str,
        direct_report_ids: List[str],
    ) -> dict:
        return self.client.run(
            self.confirm_async(actor_id, session_id, spoken, evidence_digest, direct_report_ids)
        )

    async def cancel_pending_for_session_async(self, session_id: str) -> int:
        async with self.client.acquire() as conn:
            res = await conn.execute(
                "UPDATE action_drafts SET status = 'CANCELLED' WHERE session_id = $1 AND status = 'PENDING'",
                session_id,
            )
            return int(res.split()[-1]) if res else 0

    def cancel_pending_for_session(self, session_id: str) -> int:
        return self.client.run(self.cancel_pending_for_session_async(session_id))

    async def get_draft_async(self, draft_id: str) -> Optional[dict]:
        async with self.client.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM action_drafts WHERE draft_id = $1", draft_id)
            if not row:
                return None
            params = row["parameters"]
            if isinstance(params, str):
                params = json.loads(params)
            receipt = row["receipt"]
            if isinstance(receipt, str):
                receipt = json.loads(receipt)
            return {
                "draft_id": row["draft_id"],
                "session_id": row["session_id"],
                "actor_id": row["actor_id"],
                "operation": row["operation"],
                "ticket_id": row["ticket_id"],
                "parameters": params,
                "expected_version": row["expected_version"],
                "payload_hash": row["payload_hash"],
                "readback": row["readback"],
                "expires_at": row["expires_at"].isoformat() if hasattr(row["expires_at"], "isoformat") else str(row["expires_at"]),
                "status": row["status"],
                "receipt": receipt,
                "proposal_digest": row["proposal_digest"],
            }

    def get_draft(self, draft_id: str) -> Optional[dict]:
        return self.client.run(self.get_draft_async(draft_id))

    async def get_grant_async(self, grant_id: str) -> Optional[dict]:
        async with self.client.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM action_grants WHERE grant_id = $1", grant_id)
            if not row:
                return None
            return {
                "grant_id": row["grant_id"],
                "draft_id": row["draft_id"],
                "actor_id": row["actor_id"],
                "payload_hash": row["payload_hash"],
                "evidence_digest": row["evidence_digest"],
                "expected_version": row["expected_version"],
                "expires_at": row["expires_at"].isoformat() if hasattr(row["expires_at"], "isoformat") else str(row["expires_at"]),
                "consumed_at": row["consumed_at"].isoformat() if row["consumed_at"] and hasattr(row["consumed_at"], "isoformat") else str(row["consumed_at"]) if row["consumed_at"] else None,
            }

    def get_grant(self, grant_id: str) -> Optional[dict]:
        return self.client.run(self.get_grant_async(grant_id))
