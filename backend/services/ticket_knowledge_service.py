"""
IntentLock — Ticket Knowledge Service
In-memory, completely local ticket retrieval and scoping service.
Loads all_tickets.json ONCE at startup and maintains normalized indexes.
"""

import os
import json
import re
import logging
from typing import Dict, Any, List, Optional, Set

from backend.core.config import settings
from backend.services.ticket_action_store import TicketActionStore

logger = logging.getLogger("ticket_knowledge_service")


class TicketKnowledgeService:
    _instance: Optional["TicketKnowledgeService"] = None

    def __init__(self, data_path: Optional[str] = None):
        if data_path:
            self.data_path = data_path
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.data_path = os.path.join(base_dir, "data", "all_tickets.json")

        self.is_loaded: bool = False
        if data_path is None:
            if settings.STORAGE_BACKEND == "postgres":
                from backend.adapters.postgres_ticket_action_store import PostgresTicketActionStore
                self.store = PostgresTicketActionStore.get_instance()
            else:
                self.store = TicketActionStore(seed_path=self.data_path)
        else:
            self.store = None
        self._raw_tickets: List[Dict[str, Any]] = []

        # Normalized in-memory indexes
        self.tickets_by_id: Dict[str, Dict[str, Any]] = {}
        self.tickets_by_assignee: Dict[str, List[Dict[str, Any]]] = {}
        self.tickets_by_requester: Dict[str, List[Dict[str, Any]]] = {}
        self.tickets_by_creator: Dict[str, List[Dict[str, Any]]] = {}
        self.tickets_by_status: Dict[str, List[Dict[str, Any]]] = {}
        self.tickets_by_priority: Dict[str, List[Dict[str, Any]]] = {}
        self.tickets_by_category: Dict[str, List[Dict[str, Any]]] = {}
        self.tickets_by_project: Dict[str, List[Dict[str, Any]]] = {}
        self.tickets_by_approver: Dict[str, List[Dict[str, Any]]] = {}
        self.tickets_by_escalated_to: Dict[str, List[Dict[str, Any]]] = {}

        self.load_data()

    @classmethod
    def get_instance(cls, data_path: Optional[str] = None) -> "TicketKnowledgeService":
        if cls._instance is None:
            cls._instance = cls(data_path=data_path)
        return cls._instance

    @staticmethod
    def _normalize(val: Optional[str]) -> str:
        return val.strip().lower() if val else ""

    def load_data(self) -> None:
        if self.is_loaded:
            logger.info("TicketKnowledgeService is already loaded into memory.")
            return

        if not os.path.exists(self.data_path):
            logger.warning(f"Tickets dataset not found at {self.data_path}.")
            self._raw_tickets = []
            self.is_loaded = True
            return

        logger.info(f"Loading canonical ticket dataset from {self.data_path}...")
        self._cached_revision = 1
        if settings.STORAGE_BACKEND == "postgres":
            from backend.adapters.postgres_employee_repository import PostgresEmployeeRepository
            repo = PostgresEmployeeRepository.get_instance()
            try:
                self._raw_tickets = self.store.list_tickets() if self.store else []
                self._cached_revision = repo.get_ticket_revision()
            except Exception as exc:
                if os.getenv("INTENTLOCK_OFFLINE_TESTS") == "1":
                    logger.warning(f"Failed to query tickets from store in test mode ({exc}). Using local dataset.")
                    with open(self.data_path, "r", encoding="utf-8") as f:
                        self._raw_tickets = json.load(f)
                else:
                    logger.error(f"Postgres ticket repository unavailable: {exc}")
                    raise RuntimeError("Database unavailable: failed to query tickets from PostgreSQL store.") from exc
        else:
            if self.store:
                self._raw_tickets = self.store.list_tickets()
            else:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    self._raw_tickets = json.load(f)

        self._build_indexes()
        self.is_loaded = True
        logger.info(f"Successfully loaded and indexed {len(self._raw_tickets)} tickets.")

    def refresh_from_store(self) -> None:
        if self.store:
            self._raw_tickets = self.store.list_tickets()
            self._build_indexes()

    def refresh_if_stale(self) -> None:
        """Checks ticket revision and reloads indexes if another process or transaction mutated records."""
        if settings.STORAGE_BACKEND == "postgres":
            from backend.adapters.postgres_employee_repository import PostgresEmployeeRepository
            repo = PostgresEmployeeRepository.get_instance()
            try:
                rev = repo.get_ticket_revision()
                if rev != getattr(self, "_cached_revision", 1):
                    if self.store:
                        self._raw_tickets = self.store.list_tickets()
                        self._build_indexes()
                        self._cached_revision = rev
                        logger.info("Ticket cache invalidated and reloaded to revision %s.", rev)
            except Exception as exc:
                logger.warning("Ticket revision check failed: %s", exc)
        else:
            self.refresh_from_store()

    def _build_indexes(self) -> None:
        self.tickets_by_id.clear()
        self.tickets_by_assignee.clear()
        self.tickets_by_requester.clear()
        self.tickets_by_creator.clear()
        self.tickets_by_status.clear()
        self.tickets_by_priority.clear()
        self.tickets_by_category.clear()
        self.tickets_by_project.clear()
        self.tickets_by_approver.clear()
        self.tickets_by_escalated_to.clear()

        for t in self._raw_tickets:
            tid = t["ticket_id"].strip().upper()
            self.tickets_by_id[tid] = t

            asn = t.get("assignee_id")
            if asn:
                self.tickets_by_assignee.setdefault(asn.strip().upper(), []).append(t)

            req = t.get("requester_id")
            if req:
                self.tickets_by_requester.setdefault(req.strip().upper(), []).append(t)

            crb = t.get("created_by")
            if crb:
                self.tickets_by_creator.setdefault(crb.strip().upper(), []).append(t)

            st = self._normalize(t.get("status"))
            if st:
                self.tickets_by_status.setdefault(st, []).append(t)

            pr = self._normalize(t.get("priority"))
            if pr:
                self.tickets_by_priority.setdefault(pr, []).append(t)

            cat = self._normalize(t.get("category"))
            if cat:
                self.tickets_by_category.setdefault(cat, []).append(t)

            proj = self._normalize(t.get("project"))
            if proj:
                self.tickets_by_project.setdefault(proj, []).append(t)

            app_id = t.get("approval", {}).get("approver_id")
            if app_id:
                self.tickets_by_approver.setdefault(app_id.strip().upper(), []).append(t)

            esc_to = t.get("escalation", {}).get("escalated_to")
            if esc_to:
                self.tickets_by_escalated_to.setdefault(esc_to.strip().upper(), []).append(t)

    def list_all_tickets(self) -> List[Dict[str, Any]]:
        self.refresh_from_store()
        return list(self._raw_tickets)

    def get_ticket_by_id(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        self.refresh_from_store()
        norm_id = ticket_id.strip().upper()
        return self.tickets_by_id.get(norm_id)

    def get_scoped_tickets_for_actor(
        self,
        actor_id: str,
        direct_report_ids: Optional[List[str]] = None,
        is_executive: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves tickets authorized for the actor based on role and scope.
        - Regular employee: self tickets (assignee, requester, creator).
        - Manager: self + direct reports + tickets where manager is approver or escalation target.
        - Executive: technology-wide tickets + executive approvals/escalations + self.
        """
        self.refresh_from_store()
        norm_actor = actor_id.strip().upper()
        reports = {r.strip().upper() for r in (direct_report_ids or [])}

        seen_tids = set()
        scoped_tickets = []

        for t in self._raw_tickets:
            tid = t["ticket_id"]
            asn = (t.get("assignee_id") or "").strip().upper()
            req = (t.get("requester_id") or "").strip().upper()
            crb = (t.get("created_by") or "").strip().upper()
            app = (t.get("approval", {}).get("approver_id") or "").strip().upper()
            esc = (t.get("escalation", {}).get("escalated_to") or "").strip().upper()

            # Self involvement
            is_self = norm_actor in (asn, req, crb, app, esc)

            # Manager oversight of direct reports
            is_report = bool(reports and (asn in reports or req in reports or crb in reports))

            # The CTO's explicit technology domain is narrower than the company.
            # A title or executive flag alone never grants a blanket ticket read.
            is_technology_scope = (
                is_executive
                and norm_actor == "EMP-4002"
                and t.get("department") == "Executive Management / Technology"
            )
            if (is_self or is_report or is_technology_scope) and tid not in seen_tids:
                seen_tids.add(tid)
                scoped_tickets.append(t)

        return scoped_tickets

    def filter_tickets_for_query(
        self,
        tickets: List[Dict[str, Any]],
        query_text: str,
    ) -> List[Dict[str, Any]]:
        """
        Filters a list of pre-scoped tickets down to the most relevant subset matching
        natural-language criteria (status, priority, project, category, SLA, etc.).
        """
        q = query_text.lower()

        # 1. Exact ticket ID search
        tid_match = re.search(r"\b(TKT[-_]?\d{4}[-_]?\d{3}|TKT[-_]?\d{4})\b", q, re.IGNORECASE)
        if tid_match:
            raw_tid = tid_match.group(1).upper().replace("_", "-")
            found = self.get_ticket_by_id(raw_tid)
            if found and any(t["ticket_id"] == found["ticket_id"] for t in tickets):
                return [found]
            elif found:
                # Target exists but is outside actor scope
                return []
            else:
                return []

        filtered = list(tickets)

        # 2. Status filtering
        if re.search(r"\b(unresolved|not resolved|active)\b", q):
            filtered = [t for t in filtered if t.get("status") not in ("Resolved", "Closed")]
        elif re.search(r"\b(not closed|unclosed)\b", q):
            filtered = [t for t in filtered if t.get("status") != "Closed"]
        elif re.search(r"\bin[ -]?progress\b", q):
            filtered = [t for t in filtered if t.get("status") == "In Progress"]
        elif re.search(r"\bblocked\b", q):
            filtered = [t for t in filtered if t.get("status") == "Blocked"]
        elif re.search(r"\bpending\b", q):
            filtered = [t for t in filtered if t.get("status") == "Pending" or t.get("approval", {}).get("status") == "Pending"]
        elif re.search(r"\bclosed\b", q):
            filtered = [t for t in filtered if t.get("status") == "Closed"]
        elif re.search(r"\bresolved\b", q):
            filtered = [t for t in filtered if t.get("status") in ("Resolved", "Closed")]
        elif re.search(r"\bopen\b", q):
            filtered = [t for t in filtered if t.get("status") == "Open"]

        # 3. Priority filtering
        if re.search(r"\b(critical|highest|sev-1|s1|urgent)\b", q):
            filtered = [t for t in filtered if t.get("priority") == "Critical"]
        elif re.search(r"\bhigh\b", q):
            filtered = [t for t in filtered if t.get("priority") == "High"]
        elif re.search(r"\b(medium|normal)\b", q):
            filtered = [t for t in filtered if t.get("priority") == "Medium"]
        elif re.search(r"\blow\b", q):
            filtered = [t for t in filtered if t.get("priority") == "Low"]

        # 4. SLA filtering
        if "sla" in q or "breach" in q or "at risk" in q:
            if "at risk" in q:
                filtered = [t for t in filtered if t.get("sla", {}).get("resolution_status") == "At Risk"]
            elif "breach" in q:
                filtered = [t for t in filtered if t.get("sla", {}).get("resolution_status") == "Breached"]
            else:
                filtered = [t for t in filtered if t.get("sla", {}).get("resolution_status") in ("At Risk", "Breached")]

        # 5. Approval filtering
        if "approval" in q or "pending approval" in q or "approve" in q:
            filtered = [t for t in filtered if t.get("approval", {}).get("required") or t.get("approval", {}).get("status") == "Pending"]

        # 6. Escalation filtering
        if "escalat" in q:
            filtered = [t for t in filtered if t.get("escalation", {}).get("is_escalated")]

        # 7. Category / Keyword filtering
        if "auth" in q or "authentication" in q or "token" in q or "session" in q:
            filtered = [t for t in filtered if "auth" in t.get("category", "").lower() or any("auth" in tag for tag in t.get("tags", [])) or "auth" in t.get("title", "").lower()]
        elif "database" in q or "sql" in q or "query" in q:
            filtered = [t for t in filtered if "data" in t.get("category", "").lower() or "db" in t.get("category", "").lower() or "query" in t.get("title", "").lower()]
        elif "deployment" in q or "ci/cd" in q or "pipeline" in q or "deploy" in q or "rollback" in q:
            filtered = [t for t in filtered if "ci" in t.get("category", "").lower() or "deploy" in t.get("title", "").lower() or "rollback" in t.get("title", "").lower()]
        elif "access" in q and "request" in q:
            filtered = [t for t in filtered if t.get("ticket_type") == "Access Request"]

        # 8. Project filtering
        if "support portal" in q or "customer portal" in q:
            filtered = [t for t in filtered if "customer" in t.get("project", "").lower() or "support" in t.get("project", "").lower()]
        elif "analytics" in q or "dashboard" in q:
            filtered = [t for t in filtered if "analytics" in t.get("project", "").lower()]
        elif "intentlock" in q or "kiosk" in q:
            filtered = [t for t in filtered if "intentlock" in t.get("project", "").lower()]

        # 9. Cross-user story threads
        if "story 1" in q or ("incident" in q and "auth" in q):
            story1_ids = {"TKT-2026-001", "TKT-2026-014", "TKT-2026-034"}
            story_matches = [t for t in filtered if t["ticket_id"] in story1_ids]
            if story_matches:
                return story_matches

        return filtered

    @staticmethod
    def map_ticket_to_frontend_record(t: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps a canonical backend ticket into the frontend TicketRecord contract.
        Matches frontend/src/types/payloads.ts TicketRecord schema:
        - ticket_id: str
        - title: str
        - description: str
        - priority: 'URGENT' | 'HIGH' | 'NORMAL' | 'LOW'
        - status: 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'CLOSED'
        - assigned_to: str
        - owner_id: str
        - category: str
        - created_at: str
        - updated_at: str
        - events: TicketEvent[]
        """
        # Normalize priority to frontend enum
        pr_raw = (t.get("priority") or "Medium").upper()
        if pr_raw == "CRITICAL":
            front_priority = "URGENT"
        elif pr_raw == "HIGH":
            front_priority = "HIGH"
        elif pr_raw in ("MEDIUM", "NORMAL"):
            front_priority = "NORMAL"
        else:
            front_priority = "LOW"

        # Normalize status to frontend enum
        st_raw = (t.get("status") or "Open").upper()
        if st_raw == "OPEN":
            front_status = "OPEN"
        elif st_raw == "PENDING":
            front_status = "PENDING"
        elif st_raw == "BLOCKED":
            front_status = "BLOCKED"
        elif st_raw in ("IN PROGRESS", "IN_PROGRESS"):
            front_status = "IN_PROGRESS"
        elif st_raw == "RESOLVED":
            front_status = "RESOLVED"
        elif st_raw == "CLOSED":
            front_status = "CLOSED"
        else:
            front_status = "OPEN"

        # Map events from activity_history
        events = []
        for act in t.get("activity_history", []):
            events.append({
                "timestamp": act.get("timestamp", ""),
                "type": act.get("type", "STATUS_CHANGED"),
                "actor": act.get("actor", "system"),
                "description": act.get("description", ""),
                "old_value": act.get("old_value"),
                "new_value": act.get("new_value"),
            })

        return {
            "ticket_id": t["ticket_id"],
            "title": t.get("title", ""),
            "description": t.get("description", ""),
            "priority": front_priority,
            "status": front_status,
            "assigned_to": t.get("assignee_id") or "Unassigned",
            "owner_id": t.get("requester_id") or t.get("created_by") or "Unknown",
            "category": t.get("category", "General"),
            "created_at": t.get("created_at"),
            "updated_at": t.get("updated_at"),
            "events": events,
            # Pass rich backend metadata in extra fields for detailed view
            "backend_metadata": {
                "raw_status": t.get("status"),
                "raw_priority": t.get("priority"),
                "severity": t.get("severity"),
                "ticket_type": t.get("ticket_type"),
                "project": t.get("project"),
                "sla": t.get("sla"),
                "escalation": t.get("escalation"),
                "approval": t.get("approval"),
                "resolution": t.get("resolution"),
                "comments": t.get("comments"),
            }
        }
