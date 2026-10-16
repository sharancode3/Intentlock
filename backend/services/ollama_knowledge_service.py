"""
IntentLock — Ollama Knowledge Service
Integrates local Ollama LLM with the EmployeeKnowledgeService.
Translates natural-language queries into structured retrieval, filters visibility,
builds compact context, and enforces the strict IntentLock Grounding Prompt.
Includes a deterministic local grounded synthesizer fallback if Ollama times out.
"""

import re
import json
import logging
from typing import Dict, Any, List, Optional
import httpx

from backend.core.config import settings
from backend.services.employee_knowledge_service import EmployeeKnowledgeService
from backend.services.employee_visibility_service import EmployeeVisibilityService
from backend.services.employee_context_builder import EmployeeContextBuilder

logger = logging.getLogger("ollama_knowledge_service")

GROUNDING_SYSTEM_PROMPT = """You are answering questions about the fictional IntentLock organization.

Use only the employee/company context supplied by the backend for factual employee information.

Do not invent employee details.

Do not invent employees.

Do not invent projects, skills, reporting relationships, permissions, authority, experience or activity.

If requested information is not available in the supplied context, clearly state that the information is unavailable.

Do not make authorization decisions.

Do not interpret employee seniority as automatic authorization.

The IntentLock Policy Engine determines authorization separately.

Never claim that an operation has executed unless the protected backend returns a confirmed execution result."""

class OllamaKnowledgeService:
    def __init__(
        self,
        knowledge_service: Optional[EmployeeKnowledgeService] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None
    ):
        self.knowledge_service = knowledge_service or EmployeeKnowledgeService.get_instance()
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout or settings.OLLAMA_TIMEOUT_SECONDS

    def interpret_and_retrieve(
        self,
        query: str,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        is_authenticated: bool = False
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Extract search intent/entities from user query using Python pattern matching
        and retrieve filtered relevant employee records.
        """
        q_clean = query.strip()
        q_lower = q_clean.lower()
        extracted_filters: Dict[str, Any] = {"raw_query": query}

        # 1. Check for specific roles (CEO, CTO)
        if re.search(r"\bcto\b|chief technology officer", q_lower):
            extracted_filters["role"] = "CTO"
            matched = self.knowledge_service.get_employees_by_role("Chief Technology Officer")
            if matched:
                return self._filter_records(matched, actor_id, actor_role, is_authenticated), extracted_filters

        if re.search(r"\bceo\b|chief executive officer", q_lower):
            extracted_filters["role"] = "CEO"
            matched = self.knowledge_service.get_employees_by_role("Chief Executive Officer")
            if matched:
                return self._filter_records(matched, actor_id, actor_role, is_authenticated), extracted_filters

        # 2. Check for "who reports to <Name>" or "under <Name>"
        m_reports = re.search(r"(?:who reports to|under|team of|reports for)\s+([A-Za-z\s]+?)(?:\?|\.|$|\s+has|\s+with)", q_clean, re.IGNORECASE)
        if m_reports:
            manager_name = m_reports.group(1).strip()
            manager = self.knowledge_service.find_employee_by_name(manager_name)
            if manager:
                extracted_filters["manager_id"] = manager["employee_id"]
                extracted_filters["manager_name"] = manager["identity"]["full_name"]
                direct_reports = self.knowledge_service.get_direct_reports(manager["employee_id"])
                
                # Check if there is an additional skill/experience filter (e.g. "backend development")
                m_filter = re.search(r"(?:with experience in|experience with|knows|skills in|experience relevant to)\s+([A-Za-z\s]+)", q_clean, re.IGNORECASE)
                if m_filter:
                    skill_kw = m_filter.group(1).strip().lower()
                    filtered_reports = []
                    for r in direct_reports:
                        tech_skills = [s.lower() for s in r.get("skills", {}).get("technical", [])]
                        if any(skill_kw in s or s in skill_kw for s in tech_skills):
                            filtered_reports.append(r)
                    if filtered_reports:
                        return self._filter_records(filtered_reports, actor_id, actor_role, is_authenticated), extracted_filters

                if direct_reports:
                    return self._filter_records(direct_reports, actor_id, actor_role, is_authenticated), extracted_filters

        # 3. Check for "manager of <Name>" or "<Name>'s manager"
        m_mgr = re.search(r"(?:who is\s+)?([A-Za-z\s]+?)(?:'s manager|'s lead|'s reporting manager)", q_clean, re.IGNORECASE)
        if not m_mgr:
            m_mgr = re.search(r"(?:manager of|manager for)\s+([A-Za-z\s]+)", q_clean, re.IGNORECASE)
        if m_mgr:
            emp_name = m_mgr.group(1).strip()
            target_emp = self.knowledge_service.find_employee_by_name(emp_name)
            if target_emp:
                mgr = self.knowledge_service.get_manager(target_emp["employee_id"])
                records = [mgr, target_emp] if mgr else [target_emp]
                extracted_filters["target_employee"] = target_emp["employee_id"]
                return self._filter_records(records, actor_id, actor_role, is_authenticated), extracted_filters

        # 4. Check for direct employee name in the query
        for name_key, emp in self.knowledge_service.employees_by_name.items():
            if len(name_key) > 3 and re.search(rf"\b{re.escape(name_key)}\b", q_lower):
                extracted_filters["employee_id"] = emp["employee_id"]
                extracted_filters["employee_name"] = emp["identity"]["full_name"]
                return self._filter_records([emp], actor_id, actor_role, is_authenticated), extracted_filters

        # 5. Check for department mentions
        for dept_key, emps in self.knowledge_service.employees_by_department.items():
            if dept_key in q_lower:
                extracted_filters["department"] = dept_key
                return self._filter_records(emps[:5], actor_id, actor_role, is_authenticated), extracted_filters

        # 6. Check for project mentions
        for proj_key, emps in self.knowledge_service.employees_by_project.items():
            if proj_key in q_lower:
                extracted_filters["project"] = proj_key
                return self._filter_records(emps[:5], actor_id, actor_role, is_authenticated), extracted_filters

        # 7. Check for skill / technology mentions
        for skill_key, emps in self.knowledge_service.employees_by_skill.items():
            if len(skill_key) > 3 and skill_key in q_lower:
                extracted_filters["skill"] = skill_key
                return self._filter_records(emps[:5], actor_id, actor_role, is_authenticated), extracted_filters

        # 8. Check for specific keywords: "voice security", "speaker verification", "ai security"
        if "voice security" in q_lower or "speaker verification" in q_lower or "r&d" in q_lower or "ai security" in q_lower:
            rnd_emps = self.knowledge_service.get_department_members("Research & Development")
            if rnd_emps:
                extracted_filters["topic"] = "R&D Security"
                return self._filter_records(rnd_emps[:5], actor_id, actor_role, is_authenticated), extracted_filters

        # 9. Free-text search fallback
        results = self.knowledge_service.search_employees(q_clean)
        return self._filter_records(results[:5], actor_id, actor_role, is_authenticated), extracted_filters

    def _filter_records(
        self,
        records: List[Dict[str, Any]],
        actor_id: Optional[str],
        actor_role: Optional[str],
        is_authenticated: bool
    ) -> List[Dict[str, Any]]:
        """Pass records through EmployeeVisibilityService."""
        filtered = []
        for r in records:
            if r:
                clean_r = EmployeeVisibilityService.filter_employee(
                    target=r,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    is_authenticated=is_authenticated
                )
                if clean_r:
                    filtered.append(clean_r)
        return filtered

    def answer_query(
        self,
        query: str,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        is_authenticated: bool = False
    ) -> Dict[str, Any]:
        """
        End-to-end query processing:
        1. Parse intent & retrieve 1-5 records
        2. Apply visibility filter
        3. Build compact context
        4. Query local Ollama model with grounding prompt
        5. Return structured answer with provenance
        """
        records, filters = self.interpret_and_retrieve(
            query=query,
            actor_id=actor_id,
            actor_role=actor_role,
            is_authenticated=is_authenticated
        )

        if not records:
            return {
                "answer": "I could not find any matching employee or organization records in the IntentLock knowledge base for your inquiry.",
                "matched_employees": [],
                "filters_extracted": filters,
                "context_used": "",
                "grounded": True,
                "model_used": "direct_knowledge_lookup"
            }

        compact_context = EmployeeContextBuilder.build_context(records, query=query)

        # Attempt Ollama inference
        ollama_response = self._call_ollama(query, compact_context)
        if ollama_response:
            answer_text = ollama_response
            model_used = self.model
        else:
            # Deterministic, grounded fallback answer synthesized directly from retrieved records
            answer_text = self._synthesize_grounded_fallback(query, records)
            model_used = "grounded_synthesizer_fallback"

        matched_summaries = [
            {
                "employee_id": r["employee_id"],
                "full_name": r["identity"]["full_name"],
                "designation": r["employment"]["designation"],
                "department": r["employment"]["department"],
                "organizational_level": r["employment"]["organizational_level"]
            }
            for r in records
        ]

        return {
            "answer": answer_text,
            "matched_employees": matched_summaries,
            "filters_extracted": filters,
            "context_used": compact_context,
            "grounded": True,
            "model_used": model_used
        }

    def _call_ollama(self, query: str, context: str) -> Optional[str]:
        """Call local Ollama with timeout protection."""
        prompt = f"""Supplied Employee/Company Context:
{context}

User Question:
{query}

Answer concisely based strictly on the context above:"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": GROUNDING_SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 256
            }
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code == 200:
                    resp_json = res.json()
                    response_text = resp_json.get("response", "").strip()
                    if response_text:
                        return response_text
        except Exception as e:
            logger.warning(f"Ollama call failed or timed out: {e}. Using grounded fallback synthesizer.")
            return None

        return None

    def _synthesize_grounded_fallback(
        self,
        query: str,
        records: List[Dict[str, Any]]
    ) -> str:
        """
        High-fidelity, deterministic synthesis directly from retrieved verified records.
        Ensures accurate, hallucination-free answers even when Ollama is busy.
        """
        q_lower = query.lower()

        # Single employee query
        if len(records) == 1:
            emp = records[0]
            name = emp["identity"]["full_name"]
            role = emp["employment"]["designation"]
            dept = emp["employment"]["department"]
            level = emp["employment"]["organizational_level"]

            # Projects question
            if any(w in q_lower for w in ["project", "working on", "assigned"]):
                curr = emp.get("projects", {}).get("current", [])
                if curr:
                    proj_strs = [f"{p['name']} ({p.get('role', 'Contributor')})" for p in curr]
                    return f"{name} is currently working on: {'; '.join(proj_strs)}."
                return f"{name} currently has no active assigned projects listed."

            # Skills question
            if any(w in q_lower for w in ["skill", "know", "technolog"]):
                tech = emp.get("skills", {}).get("technical", [])
                tools = emp.get("skills", {}).get("tools", [])
                all_s = tech + tools
                if all_s:
                    return f"{name} has skills in: {', '.join(all_s)}."
                return f"No specific technical skills are recorded for {name}."

            # Manager question
            if any(w in q_lower for w in ["manager", "reports to", "who is the manager"]):
                mgr_name = emp.get("reporting", {}).get("manager_name")
                mgr_id = emp.get("reporting", {}).get("manager_id")
                if mgr_name:
                    return f"{name}'s manager is {mgr_name}" + (f" ({mgr_id})" if mgr_id else "") + "."
                return f"{name} reports to the Board of Directors."

            # Career / previous work question
            if any(w in q_lower for w in ["previous", "career", "where did", "work before", "intern"]):
                hist = emp.get("experience", {}).get("career_history", [])
                if hist:
                    entries = [f"{h.get('role')} at {h.get('organization')}" for h in hist]
                    return f"Previously, {name} worked as: {'; '.join(entries)}."
                return f"No previous external career history is recorded for {name}."

            # Research question
            if any(w in q_lower for w in ["research", "publication", "patent"]) and emp.get("research"):
                r = emp["research"]
                spec = r.get("specialization")
                pubs = len(r.get("publications", []))
                return f"{name} specializes in {spec} with {pubs} research publications/outputs."

            # Executive authority question
            if any(w in q_lower for w in ["authority", "financial", "budget", "signing"]) and emp.get("executive_authority"):
                ea = emp["executive_authority"]
                details = []
                if ea.get("financial_authority"):
                    details.append(f"Financial Authority: {ea['financial_authority']}")
                if ea.get("technology_authority"):
                    details.append(f"Technology Authority: {ea['technology_authority']}")
                return f"{name} ({role}) holds the following executive authorities: {'; '.join(details)}."

            # General "Who is" question
            mgr_str = f", reporting to {emp['reporting']['manager_name']}" if emp.get("reporting", {}).get("manager_name") else ""
            summary = emp.get("experience", {}).get("professional_summary")
            base = f"{name} is a {role} in the {dept} department ({level}){mgr_str}."
            if summary:
                base += f" {summary}"
            return base

        # Multi-employee query (e.g. "Who reports to Priya?", "Who knows FastAPI?", "Who works in Engineering?")
        if any(w in q_lower for w in ["manager", "reports to", "who is the manager"]):
            # Check for the employee mentioned in query
            target_emp = None
            for emp in records:
                if emp["identity"]["full_name"].lower() in q_lower or emp["identity"]["preferred_name"].lower() in q_lower:
                    target_emp = emp
                    break
            if not target_emp:
                target_emp = records[0]

            mgr_name = target_emp.get("reporting", {}).get("manager_name")
            mgr_id = target_emp.get("reporting", {}).get("manager_id")
            if mgr_name:
                return f"{target_emp['identity']['full_name']}'s manager is {mgr_name}" + (f" ({mgr_id})" if mgr_id else "") + "."

        names_roles = [f"{e['identity']['full_name']} ({e['employment']['designation']})" for e in records]
        if any(w in q_lower for w in ["report", "under"]):
            return f"The following employees report directly: {', '.join(names_roles)}."
        if any(w in q_lower for w in ["know", "skill", "fastapi", "python"]):
            return f"Employees matching this skill: {', '.join(names_roles)}."
        return f"Matching employees found: {', '.join(names_roles)}."
