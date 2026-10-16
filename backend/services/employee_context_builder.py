"""
IntentLock — Employee Context Builder
Transforms retrieved structured employee records into compact, tightly bounded LLM context.
Selects context fields based on question intent to minimize token usage, latency, and hallucination.
"""

from typing import Dict, Any, List, Optional

class EmployeeContextBuilder:

    @classmethod
    def build_context(
        cls,
        records: List[Dict[str, Any]],
        intent: Optional[str] = None,
        query: Optional[str] = None
    ) -> str:
        """
        Build a compact text prompt context from 1 to 5 relevant records.
        """
        if not records:
            return "No matching employee records found in the IntentLock knowledge base."

        # Cap at top 5 records to maintain compact context
        selected_records = records[:5]
        context_blocks = []

        q_lower = query.lower() if query else ""

        for emp in selected_records:
            block = cls._build_single_employee_context(emp, intent, q_lower)
            context_blocks.append(block)

        return "\n\n---\n\n".join(context_blocks)

    @classmethod
    def _build_single_employee_context(
        cls,
        emp: Dict[str, Any],
        intent: Optional[str],
        query: str
    ) -> str:
        ident = emp.get("identity", {})
        empl = emp.get("employment", {})
        rep = emp.get("reporting", {})
        exp = emp.get("experience", {})
        skills = emp.get("skills", {})
        projs = emp.get("projects", {})
        research = emp.get("research")
        exec_auth = emp.get("executive_authority")

        lines = [
            "EMPLOYEE RECORD",
            f"Employee ID: {emp.get('employee_id')}",
            f"Name: {ident.get('full_name')} (Preferred: {ident.get('preferred_name')})",
            f"Role: {empl.get('designation')}",
            f"Department: {empl.get('department')}" + (f" ({empl.get('sub_department')})" if empl.get('sub_department') else ""),
            f"Level: {empl.get('organizational_level')}",
            f"Location: {empl.get('location')} ({empl.get('work_mode')})",
        ]

        if rep.get("manager_name"):
            lines.append(f"Manager: {rep.get('manager_name')} ({rep.get('manager_id') or 'N/A'})")

        # Determine focus based on query / intent
        is_project_query = any(w in query for w in ["project", "working on", "assigned to", "allocation"])
        is_skill_query = any(w in query for w in ["skill", "know", "experience with", "technolog", "python", "fastapi", "react"])
        is_career_query = any(w in query for w in ["career", "previous", "intern", "where did", "work history", "history", "studied", "college", "education"])
        is_reporting_query = any(w in query for w in ["manager", "reports to", "report", "who under", "hierarchy", "team lead", "supervis"])
        is_research_query = any(w in query for w in ["research", "publication", "patent", "model", "speaker verification", "deepfake", "r&d"])
        is_exec_query = any(w in query for w in ["authority", "ceo", "cto", "board", "budget", "financial", "signing", "headcount", "crisis"])

        # If general overview (none specific triggered)
        is_general = not (is_project_query or is_skill_query or is_career_query or is_reporting_query or is_research_query or is_exec_query)

        # 1. Direct reports
        if is_reporting_query or is_general:
            direct_reports = rep.get("direct_report_ids", [])
            if direct_reports:
                lines.append(f"Direct Reports ({len(direct_reports)}): {', '.join(direct_reports)}")

        # 2. Skills
        if is_skill_query or is_general:
            tech = skills.get("technical", [])
            mgmt = skills.get("management", [])
            res = skills.get("research", [])
            tools = skills.get("tools", [])
            all_s = tech + tools + mgmt + res
            if all_s:
                lines.append("Skills:")
                if tech:
                    lines.append(f"  Technical: {', '.join(tech[:10])}")
                if tools:
                    lines.append(f"  Tools/Platforms: {', '.join(tools[:6])}")
                if mgmt:
                    lines.append(f"  Management: {', '.join(mgmt[:6])}")
                if res:
                    lines.append(f"  Research: {', '.join(res[:6])}")

        # 3. Projects
        if is_project_query or is_general:
            curr = projs.get("current", [])
            prev = projs.get("previous", [])
            if curr:
                lines.append("Current Projects:")
                for p in curr:
                    alloc = f" ({p.get('allocation_percent')}%)" if p.get('allocation_percent') is not None else ""
                    lines.append(f"  - {p['name']}: {p.get('role', 'Contributor')}{alloc}")
            if prev and (is_project_query or is_career_query):
                lines.append("Previous Projects:")
                for p in prev[:3]:
                    lines.append(f"  - {p['name']}: {p.get('role', 'Contributor')}")

        # 4. Career History & Education
        if is_career_query or is_general:
            summary = exp.get("professional_summary")
            if summary:
                lines.append(f"Professional Summary: {summary}")
            career = exp.get("career_history", [])
            if career:
                lines.append("Career History:")
                for c in career[:4]:
                    dates = f" ({c.get('start_date')} - {c.get('end_date')})" if c.get('start_date') else ""
                    lines.append(f"  - {c.get('role')} at {c.get('organization')}{dates}")
            edu = emp.get("education", [])
            if edu:
                lines.append("Education:")
                for e in edu:
                    year = f" ({e.get('graduation_year')})" if e.get('graduation_year') else ""
                    lines.append(f"  - {e.get('degree')} from {e.get('institution')}{year}")

        # 5. R&D Details
        if (is_research_query or is_general) and research:
            lines.append("Research Profile:")
            lines.append(f"  Specialization: {research.get('specialization')}")
            if research.get("publications"):
                lines.append(f"  Publications: {', '.join(research.get('publications')[:3])}")
            if research.get("patents"):
                lines.append(f"  Patents: {', '.join(research.get('patents')[:2])}")
            if research.get("prototypes"):
                lines.append(f"  Prototypes: {', '.join(research.get('prototypes')[:2])}")

        # 6. Executive Authority Details
        if (is_exec_query or is_general) and exec_auth:
            lines.append("Executive Authority:")
            if exec_auth.get("board_relationship"):
                lines.append(f"  Board Relationship: {exec_auth.get('board_relationship')}")
            if exec_auth.get("financial_authority"):
                lines.append(f"  Financial Authority: {exec_auth.get('financial_authority')}")
            if exec_auth.get("technology_authority"):
                lines.append(f"  Technology Authority: {exec_auth.get('technology_authority')}")
            if exec_auth.get("headcount_authority"):
                lines.append(f"  Headcount Authority: {exec_auth.get('headcount_authority')}")
            if exec_auth.get("signing_authority"):
                lines.append(f"  Signing Authority: {exec_auth.get('signing_authority')}")

        return "\n".join(lines)
