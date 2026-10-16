#!/usr/bin/env python3
"""
IntentLock — Employee Knowledge Base Builder
One-time extraction, normalization, and validation of rich employee/company profiles from DOCX documents.
Generates:
  - backend/data/all_employees.json (Canonical runtime dataset)
  - backend/data/source/*.json (Category-specific files for development)
"""

import os
import re
import json
import logging
from typing import Dict, Any, List, Optional
import docx
import dateutil.parser

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("build_employee_knowledge_base")

WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PROFILES_DIR = os.path.join(WORKSPACE_DIR, "data", "employee_profiles")
BACKEND_DATA_DIR = os.path.join(WORKSPACE_DIR, "backend", "data")
BACKEND_SOURCE_DIR = os.path.join(BACKEND_DATA_DIR, "source")

def split_items(text: Optional[str], delimiters: List[str] = [";", "\n"]) -> List[str]:
    """Split a string by delimiters and clean up whitespace."""
    if not text:
        return []
    pattern = "|".join(map(re.escape, delimiters))
    raw = re.split(pattern, text)
    cleaned = []
    for item in raw:
        item = item.strip()
        # Remove leading bullet points or numbers like "1. ", "- ", etc.
        item = re.sub(r"^(?:[\d]+\.|\-|\*|•)\s*", "", item).strip()
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned

def parse_date(date_str: Optional[str]) -> Optional[str]:
    """Parse various date formats into YYYY-MM-DD or standard ISO string."""
    if not date_str:
        return None
    date_str = date_str.strip()
    try:
        dt = dateutil.parser.parse(date_str, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        m = re.search(r"\b(20\d\d)\b", date_str)
        if m:
            return f"{m.group(1)}-01-01"
        return date_str

def parse_experience_years(exp_str: Optional[str]) -> float:
    """Extract numeric experience in years."""
    if not exp_str:
        return 0.0
    m = re.search(r"([\d\.]+)\s*(?:years|year)?", str(exp_str), re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return 0.0
    return 0.0

def parse_project_list(proj_text: Optional[str]) -> List[Dict[str, Any]]:
    """Parse project strings with roles and percentage allocations."""
    projects = []
    if not proj_text:
        return projects
    raw_items = split_items(proj_text, [";", "\n"])
    for item in raw_items:
        alloc = None
        m_alloc = re.search(r"\((\d+)%\s*allocation\)", item, re.IGNORECASE)
        if m_alloc:
            alloc = int(m_alloc.group(1))
            item = re.sub(r"\s*\(\d+%\s*allocation\)", "", item).strip()
        
        name = item
        role = "Contributor"
        if " - " in item:
            parts = item.split(" - ", 1)
            name = parts[0].strip()
            role = parts[1].strip()
        elif ":" in item:
            parts = item.split(":", 1)
            name = parts[0].strip()
            role = parts[1].strip()

        proj_obj: Dict[str, Any] = {
            "name": name,
            "role": role,
            "status": "Active"
        }
        if alloc is not None:
            proj_obj["allocation_percent"] = alloc
        projects.append(proj_obj)
    return projects

def parse_career_history(text: Optional[str]) -> List[Dict[str, Any]]:
    """Parse career entries into structured history objects."""
    history = []
    if not text:
        return history
    items = split_items(text, [";", "\n"])
    for item in items:
        # e.g., "Graduate Software Intern, DemoTech Solutions, Jan 2025-Jun 2025: built CRUD APIs..."
        m_dates = re.search(r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|20\d\d)[^:]*?)\b(?::|\s*-)", item, re.IGNORECASE)
        dates = m_dates.group(1).strip() if m_dates else None
        
        # Check for organization and role
        org = "Internal"
        role = "Professional"
        resp: List[str] = []

        if ":" in item:
            header, detail = item.split(":", 1)
            resp = [d.strip() for d in detail.split(",") if d.strip()]
            header_parts = [p.strip() for p in header.split(",")]
            if len(header_parts) >= 2:
                role = header_parts[0]
                org = header_parts[1]
            elif len(header_parts) == 1:
                role = header_parts[0]
        else:
            parts = [p.strip() for p in item.split("-")]
            if len(parts) >= 2:
                org = parts[0]
                role = parts[1]
            else:
                role = item

        start_date = None
        end_date = None
        if dates:
            if "-" in dates:
                dparts = dates.split("-", 1)
                start_date = dparts[0].strip()
                end_date = dparts[1].strip()
            else:
                start_date = dates

        history.append({
            "organization": org,
            "role": role,
            "start_date": start_date,
            "end_date": end_date,
            "responsibilities": resp
        })
    return history

def parse_manager_info(manager_str: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Extract manager ID and manager Name from strings like 'Priya Sharma (EMP-2001)' or 'CEO / Board'."""
    if not manager_str:
        return None, None
    manager_str = manager_str.strip()
    
    # Check for (EMP-XXXX) or (EXE-XXXX) or (RND-XXXX)
    m = re.search(r"([A-Za-z\s\.\,\-\']+)\s*\((EMP-\d+|EXE-\d+|RND-\d+)\)", manager_str)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    
    # Check for direct ID mention
    m_id = re.search(r"\b(EMP-\d+|EXE-\d+|RND-\d+)\b", manager_str)
    if m_id:
        return m_id.group(1).strip(), manager_str.replace(m_id.group(1), "").strip(" ()")
    
    # Special organizational mappings
    if "Board of Directors" in manager_str or manager_str == "Board":
        return None, "Board of Directors"
    if "CEO" in manager_str:
        return "EXE-0001", "Ishaan Mehta"
    if "Dr. Aditi Narayan" in manager_str:
        return "RND-5001", "Dr. Aditi Narayan"
    if "Head of R&D / CTO Office" in manager_str or "CTO Office" in manager_str:
        return "EMP-4002", "Arvind Rao"
    if "Director of Information Security" in manager_str:
        return "EMP-3005", "Maya Krishnan"
    if "Vikram Malhotra" in manager_str:
        return "EMP-3001", "Vikram Malhotra"
    if "Karan Bhatia" in manager_str:
        return "EMP-3002", "Karan Bhatia"
    if "Ananya Iyer" in manager_str:
        return "EMP-4001", "Ananya Iyer"

    return None, manager_str

def parse_permissions_structure(
    level: str,
    raw_permissions: Dict[str, Any]
) -> Dict[str, Any]:
    """Normalize raw permission strings into structured effects and scopes."""
    perms: Dict[str, Any] = {}
    
    # Leave approval
    leave_auth = raw_permissions.get("Leave Authority") or raw_permissions.get("Can Approve") or ""
    if "direct reports" in leave_auth.lower() or level in ["L2", "L3"]:
        perms["leave_approval"] = {"effect": "ALLOW", "scope": "DIRECT_REPORTS"}
    elif level in ["L4", "L5", "L6"]:
        perms["leave_approval"] = {"effect": "ALLOW", "scope": "DEPARTMENT"}
    else:
        perms["leave_approval"] = {"effect": "REQUIRE_APPROVAL", "scope": "SELF"}

    # Budget authority
    budget_auth = raw_permissions.get("Budget / Resource Responsibility") or raw_permissions.get("Budget Responsibility") or raw_permissions.get("Budget Authority") or raw_permissions.get("Financial Authority") or ""
    if budget_auth:
        scope = "SELF"
        if "enterprise" in budget_auth.lower() or level in ["L5", "L6"]:
            scope = "ENTERPRISE"
        elif "department" in budget_auth.lower() or level == "L4":
            scope = "DEPARTMENT"
        elif "team" in budget_auth.lower() or level in ["L2", "L3"]:
            scope = "TEAM"
        perms["budget_authority"] = {
            "effect": "ALLOW",
            "scope": scope,
            "description": budget_auth
        }
    else:
        perms["budget_authority"] = {"effect": "DENY", "scope": "SELF"}

    # Hiring authority
    hiring_auth = raw_permissions.get("Hiring Authority") or raw_permissions.get("Executive Hiring Authority") or raw_permissions.get("Senior Technical Hiring") or ""
    if hiring_auth:
        scope = "ENTERPRISE" if level in ["L5", "L6"] else ("DEPARTMENT" if level == "L4" else "TEAM")
        perms["hiring_authority"] = {
            "effect": "ALLOW",
            "scope": scope,
            "description": hiring_auth
        }
    else:
        perms["hiring_authority"] = {"effect": "DENY", "scope": "SELF"}

    # Promotion authority
    promo_auth = raw_permissions.get("Promotion Authority") or raw_permissions.get("Promotion / Transfer Authority") or ""
    if promo_auth:
        scope = "ENTERPRISE" if level in ["L5", "L6"] else ("DEPARTMENT" if level == "L4" else "TEAM")
        perms["promotion_authority"] = {
            "effect": "ALLOW" if level in ["L4", "L5", "L6"] else "RECOMMEND_ONLY",
            "scope": scope,
            "description": promo_auth
        }
    else:
        perms["promotion_authority"] = {"effect": "DENY", "scope": "SELF"}

    # Termination authority
    term_auth = raw_permissions.get("Termination Authority") or ""
    if term_auth:
        perms["termination_authority"] = {
            "effect": "ALLOW" if level in ["L4", "L5", "L6"] else "REQUIRE_APPROVAL",
            "scope": "DEPARTMENT" if level == "L4" else "ENTERPRISE",
            "description": term_auth
        }
    else:
        perms["termination_authority"] = {"effect": "DENY", "scope": "SELF"}

    # Project authority
    proj_auth = raw_permissions.get("Project Authority") or raw_permissions.get("Project / Portfolio Authority") or ""
    if proj_auth:
        perms["project_authority"] = {
            "effect": "ALLOW",
            "scope": "DEPARTMENT" if level == "L4" else ("ENTERPRISE" if level in ["L5", "L6"] else "TEAM"),
            "description": proj_auth
        }
    else:
        perms["project_authority"] = {"effect": "ALLOW", "scope": "ASSIGNED_PROJECTS"}

    # Profile modification
    perms["profile_modification"] = {
        "effect": "ALLOW",
        "scope": "SELF_CONTACT_ONLY",
        "requires_verification": True
    }

    return perms

def read_docx_tables(filepath: str) -> List[List[Dict[str, str]]]:
    """Read all tables from a DOCX file and return rows as dictionaries."""
    doc = docx.Document(filepath)
    tables_data = []
    for t in doc.tables:
        if not t.rows:
            continue
        headers = [c.text.strip().replace("\n", " ") for c in t.rows[0].cells]
        rows = []
        for r in t.rows[1:]:
            row_dict = {}
            for h, c in zip(headers, r.cells):
                cell_text = c.text.strip().replace("\n", " ")
                if h:
                    row_dict[h] = cell_text
            rows.append(row_dict)
        tables_data.append(rows)
    return tables_data

def extract_level_string(lvl_str: Optional[str]) -> str:
    """Normalize level string to L1, L2, L3, L4, L5, L6, or RND."""
    if not lvl_str:
        return "L1"
    lvl_str = lvl_str.strip().upper()
    m = re.search(r"\b(L[1-6])\b", lvl_str)
    if m:
        return m.group(1)
    if "CHIEF EXECUTIVE" in lvl_str or "L6" in lvl_str:
        return "L6"
    if "EXECUTIVE" in lvl_str or "L5" in lvl_str:
        return "L5"
    if "DIRECTOR" in lvl_str or "L4" in lvl_str:
        return "L4"
    if "MANAGER" in lvl_str or "L3" in lvl_str:
        return "L3"
    if "TEAM LEAD" in lvl_str or "LEAD" in lvl_str or "L2" in lvl_str:
        return "L2"
    if "R&D" in lvl_str or "RESEARCH" in lvl_str:
        return "R&D"
    return "L1"

def parse_docx_file(filename: str, category_name: str) -> List[Dict[str, Any]]:
    """Parse a single profile DOCX document and return a list of raw employee profile objects."""
    fpath = os.path.join(DATA_PROFILES_DIR, filename)
    tables = read_docx_tables(fpath)
    if not tables:
        return []

    t0_rows = tables[0]
    t1_rows = tables[1] if len(tables) > 1 else []
    t2_rows = tables[2] if len(tables) > 2 else []
    t3_rows = tables[3] if len(tables) > 3 else []
    t4_rows = tables[4] if len(tables) > 4 else []

    employees = []

    for i, t0 in enumerate(t0_rows):
        emp_id = t0.get("Employee ID") or t0.get("Executive ID") or f"EMP-{i+1:04d}"
        full_name = t0.get("Full Name", "").strip()
        preferred_name = t0.get("Preferred Name") or full_name.split()[0] if full_name else ""
        work_email = t0.get("Work Email", "").strip()
        designation = t0.get("Role / Designation") or t0.get("Function / Portfolio") or "Employee"
        department = t0.get("Department", "General")
        sub_dept = (
            t0.get("Sub-Department / Function")
            or t0.get("Team")
            or t0.get("Function / Portfolio")
            or t0.get("Executive Portfolio")
            or t0.get("Executive Function")
            or t0.get("Research Unit")
            or None
        )
        raw_level = t0.get("Company Level") or t0.get("R&D Role Level") or category_name
        org_level = extract_level_string(raw_level)
        research_level = t0.get("R&D Role Level") if "RnD" in filename or "RND" in emp_id else None

        emp_type = t0.get("Employment Type", "Full-Time")
        status = t0.get("Employment Status", "Active")
        location = t0.get("Work Location") or t0.get("Primary Location") or "Bengaluru"
        work_mode = t0.get("Work Mode", "Hybrid")
        date_joining = parse_date(t0.get("Date of Joining") or t0.get("Date of Appointment"))

        raw_mgr = t0.get("Reporting Manager") or t0.get("Reports To") or t0.get("Reporting Director")
        manager_id, manager_name = parse_manager_info(raw_mgr)

        total_exp_str = t0.get("Total Professional Experience") or t0.get("Years of Professional Experience")
        total_exp = parse_experience_years(total_exp_str)

        # Education
        education = []
        highest_qual = t0.get("Highest Qualification")
        institution = t0.get("Institution")
        grad_year = t0.get("Graduation Year")
        other_edu = t0.get("Other Education")

        if highest_qual:
            education.append({
                "degree": highest_qual,
                "institution": institution or "Accredited University",
                "graduation_year": grad_year or "Prior to joining",
                "details": other_edu or None
            })
        if other_edu and not highest_qual:
            education.append({
                "degree": other_edu,
                "institution": "University",
                "graduation_year": None,
                "details": other_edu
            })

        # Table 1: Experience, Skills, Projects
        t1 = t1_rows[i] if i < len(t1_rows) else {}
        prof_summary = t1.get("Professional Summary", "")
        
        # Skills
        tech_skills = split_items(
            t1.get("Core Skills")
            or t1.get("Technical Skills")
            or t1.get("Technical / Domain Skills")
            or t1.get("Technical / Domain Expertise")
            or t1.get("Core Expertise")
            or t1.get("Earlier Career Responsibilities")
            or ""
        )
        mgmt_skills = split_items(
            t1.get("Leadership Skills")
            or t1.get("Managerial Skills")
            or t1.get("Strategic Skills")
            or t1.get("Strategic Expertise")
            or t1.get("Current Enterprise Priorities")
            or t1.get("Current Technology Priorities")
            or ""
        )
        research_skills = split_items(
            t1.get("Research Skills")
            or t0.get("Primary Research Specialization")
            or t0.get("Secondary Research Areas")
            or ""
        )
        tool_skills = split_items(t1.get("Tools / Platforms") or "")

        skills = {
            "technical": tech_skills,
            "management": mgmt_skills,
            "research": research_skills,
            "tools": tool_skills
        }

        # Projects
        curr_proj_str = t1.get("Current Projects") or t1.get("Current Programs / Projects") or t1.get("Current Research Projects") or t1.get("Current Strategic Programs") or t1.get("Current Enterprise Programs") or t1.get("Current Technology Priorities") or t1.get("Current Enterprise Priorities") or ""
        past_proj_str = t1.get("Previous Project History") or t1.get("Major Past Projects") or t1.get("Previous Research Projects") or t1.get("Major Past Programs") or ""
        
        current_projects = parse_project_list(curr_proj_str)
        previous_projects = parse_project_list(past_proj_str)
        for p in previous_projects:
            p["status"] = "Completed"

        projects = {
            "current": current_projects,
            "previous": previous_projects
        }

        # Career history
        career_str = t1.get("Previous Work / Internship History") or t1.get("Career History") or t1.get("Career Progression") or t1.get("Previous Organizations") or ""
        career_history = parse_career_history(career_str)

        # Responsibilities & Achievements
        responsibilities = split_items(
            t1.get("Current Responsibilities")
            or t1.get("Current Project Responsibilities")
            or t1.get("Leadership Responsibilities")
            or t1.get("Current Manager Responsibilities")
            or t1.get("Current Strategic Responsibilities")
            or t1.get("Current Executive Responsibilities")
            or t1.get("Research Responsibilities")
            or ""
        )
        achievements = split_items(
            t1.get("Achievements")
            or t1.get("Achievements / Contributions")
            or t1.get("Notable Work Experience")
            or ""
        )

        # Table 2: Permissions, Authorities, Scopes
        t2 = t2_rows[i] if i < len(t2_rows) else {}
        permissions = parse_permissions_structure(org_level, t2)

        # Table 3: Voice Authority, Rules, Restrictions
        t3 = t3_rows[i] if i < len(t3_rows) else {}
        t4 = t4_rows[i] if i < len(t4_rows) else {}

        # Merge voice details from whichever table contains them
        voice_source = t2 if "Can Modify by Voice" in t2 else (t3 if "Can Modify by Voice" in t3 else {})
        allowed_cmds_str = t3.get("Example Allowed Voice Commands") or t4.get("Example Allowed Voice Commands") or ""
        denied_cmds_str = t3.get("Example Denied Voice Commands") or t4.get("Example Denied Voice Commands") or ""
        high_risk_str = t2.get("High-Risk Voice Actions") or t3.get("High-Risk Actions") or t3.get("High-Risk Voice Actions") or t4.get("High-Risk Actions") or t4.get("High-Risk Voice Actions") or t4.get("High-Risk R&D Actions") or ""
        sec_policy = t2.get("Voice Security Policy") or t3.get("Security / Authorization Rule") or t4.get("Security / Authorization Rule") or t4.get("IntentLock Security Rule") or "Verified voice establishes identity evidence; permissions enforced independently."

        voice_authority = {
            "can_modify_by_voice": split_items(voice_source.get("Can Modify by Voice") or voice_source.get("Can Modify Own Profile by Voice") or ""),
            "can_approve_by_voice": split_items(voice_source.get("Can Approve by Voice") or voice_source.get("Can Approve") or ""),
            "can_recommend_by_voice": split_items(voice_source.get("Can Recommend by Voice") or voice_source.get("Can Recommend") or ""),
            "requires_approval": split_items(t2.get("Requires Approval") or t2.get("Requires Manager Approval") or t2.get("Requires Director / HR Approval") or t3.get("Requires Executive / HR / Finance Approval") or t3.get("Requires Board / CEO / Finance / Legal Approval") or ""),
            "allowed_commands": split_items(allowed_cmds_str),
            "denied_commands": split_items(denied_cmds_str),
            "high_risk_actions": split_items(high_risk_str),
            "security_policy": sec_policy
        }

        # Explicit Security Scope & Restrictions (Mandatory Architectural Invariant)
        cannot_view = split_items(t2.get("Cannot View") or t3.get("Cannot View") or t4.get("Cannot View") or "")
        cannot_perform = split_items(t2.get("Cannot Modify / Perform") or t3.get("Cannot Perform") or t4.get("Cannot Perform") or "")
        
        security_scope = {
            "can_change_own_authority": False,
            "can_grant_self_admin": False,
            "can_disable_intentlock": False,
            "can_delete_audit_history": False,
            "can_bypass_speaker_verification": False,
            "can_execute_arbitrary_commands": False,
            "can_reveal_private_keys": False,
            "cannot_view": cannot_view,
            "cannot_perform": cannot_perform,
            "resource_scope": t2.get("Resource Scope") or t2.get("Data Access Scope") or t2.get("Department Data Visibility") or t2.get("Enterprise Data Visibility") or "Assigned scope",
            "self_elevation_restrictions": t2.get("Self-Elevation Restrictions") or t3.get("Self-Elevation Rule") or t3.get("Self-Elevation Restriction") or t4.get("Self-Elevation Restriction") or "Strictly prohibited"
        }

        # R&D Section
        research = None
        if "RnD" in filename or org_level == "R&D" or "RND" in emp_id:
            research = {
                "specialization": t0.get("Primary Research Specialization", "Applied Artificial Intelligence"),
                "secondary_areas": split_items(t0.get("Secondary Research Areas") or ""),
                "research_experience_years": parse_experience_years(t0.get("Research Experience")),
                "publications": split_items(t2.get("Publications / Research Outputs") or ""),
                "patents": split_items(t2.get("Patent / Invention Activity") or ""),
                "prototypes": split_items(t2.get("Prototype History") or ""),
                "datasets": split_items(t2.get("Datasets Used") or ""),
                "models": split_items(t2.get("Models / Systems Used") or ""),
                "compute_access": t2.get("Research Compute Access", "Assigned Cluster"),
                "source_code_access": t2.get("Source Code Access Scope", "R&D Repositories"),
                "ip_scope": t2.get("IP / Confidentiality Scope", "Strictly Protected"),
                "model_release_rule": t4.get("Model Release Rule", "Requires AI Governance Approval"),
                "dataset_release_rule": t4.get("Dataset Release Rule", "Cannot export or publish restricted datasets")
            }

        # Executive Authority Section
        executive_authority = None
        if org_level in ["L5", "L6"] or "CEO" in filename or "CTO" in filename:
            executive_authority = {
                "board_relationship": t0.get("Board Relationship", "Direct reporting or regular executive liaison"),
                "financial_authority": t2.get("Financial Authority") or t2.get("Capital Allocation Authority") or "Delegated executive authority",
                "budget_authority": t2.get("Budget Planning Authority") or t2.get("Budget Authority") or t2.get("Technology Budget Authority") or "Operating budget ownership",
                "headcount_authority": t2.get("Headcount Authority", "Executive approval required"),
                "signing_authority": t2.get("Contract / Signing Authority") or t2.get("Vendor / Contract Authority") or "Standard executive authority",
                "ma_authority": t2.get("M&A Authority", "Board reserved"),
                "crisis_authority": t3.get("Crisis Authority") or t3.get("Incident / Emergency Authority") or "Executive crisis team lead",
                "risk_ownership": t3.get("Risk Ownership") or t3.get("Technology Risk Ownership") or "Enterprise operational risk owner",
                "technology_authority": t1.get("Architecture Authority") or t1.get("Technology Strategy Responsibility") or None
            }

        # Recent Activity History
        recent_activity = split_items(
            t3.get("Recent Demo Activity History")
            or t3.get("Recent Activity History")
            or t3.get("Recent Manager Activity")
            or t4.get("Recent Director Activity")
            or t4.get("Recent Executive Activity")
            or t4.get("Recent R&D Activity")
            or ""
        )

        # Provenance
        provenance = {
            "source_document": filename,
            "source_type": "DOCX",
            "import_version": "1.0",
            "category": category_name
        }

        emp_record = {
            "employee_id": emp_id,
            "identity": {
                "full_name": full_name,
                "preferred_name": preferred_name,
                "work_email": work_email
            },
            "employment": {
                "designation": designation,
                "department": department,
                "sub_department": sub_dept,
                "organizational_level": org_level,
                "research_level": research_level,
                "employment_type": emp_type,
                "status": status,
                "location": location,
                "work_mode": work_mode,
                "date_of_joining": date_joining
            },
            "reporting": {
                "manager_id": manager_id,
                "manager_name": manager_name,
                "direct_report_ids": []
            },
            "experience": {
                "total_years": total_exp,
                "professional_summary": prof_summary,
                "career_history": career_history
            },
            "education": education,
            "skills": skills,
            "projects": projects,
            "responsibilities": responsibilities,
            "achievements": achievements,
            "permissions": permissions,
            "security_scope": security_scope,
            "voice_authority": voice_authority,
            "research": research,
            "executive_authority": executive_authority,
            "recent_activity": recent_activity,
            "provenance": provenance
        }

        employees.append(emp_record)

    return employees

def merge_cto_records(cto_record: Dict[str, Any], l5_cto_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge the CTO specific record with the L5 Executive Administrator record
    for EMP-4002 (Arvind Rao) to form a single, comprehensive canonical profile.
    """
    merged = json.loads(json.dumps(cto_record))  # deep copy CTO profile as base

    # Incorporate any additional programs or details from L5
    l5_skills = l5_cto_record.get("skills", {})
    for k in ["technical", "management", "research", "tools"]:
        for s in l5_skills.get(k, []):
            if s not in merged["skills"][k]:
                merged["skills"][k].append(s)

    l5_current_projs = l5_cto_record.get("projects", {}).get("current", [])
    for p in l5_current_projs:
        if not any(cp["name"] == p["name"] for cp in merged["projects"]["current"]):
            merged["projects"]["current"].append(p)

    # Executive authority enrichment
    if l5_cto_record.get("executive_authority"):
        for k, v in l5_cto_record["executive_authority"].items():
            if v and (not merged.get("executive_authority") or not merged["executive_authority"].get(k)):
                if not merged.get("executive_authority"):
                    merged["executive_authority"] = {}
                merged["executive_authority"][k] = v

    # Ensure organizational level reflects executive leadership
    merged["employment"]["organizational_level"] = "L5"
    merged["employment"]["designation"] = "Chief Technology Officer (CTO)"
    merged["provenance"]["merged_from"] = [
        "IntentLock_CTO_Detailed_Profile.docx",
        "IntentLock_L5_Executive_Administrator_Detailed_Profiles.docx"
    ]
    return merged

def build_knowledge_base():
    """Main extraction, normalization, and validation orchestrator."""
    os.makedirs(BACKEND_DATA_DIR, exist_ok=True)
    os.makedirs(BACKEND_SOURCE_DIR, exist_ok=True)

    file_configs = [
        ("IntentLock_CEO_Detailed_Profile.docx", "ceo", "ceo.json"),
        ("IntentLock_CTO_Detailed_Profile.docx", "cto", "cto.json"),
        ("IntentLock_L1_Employee_Detailed_Profiles.docx", "employees", "employees.json"),
        ("IntentLock_L2_Team_Lead_Detailed_Profiles.docx", "team_leads", "team_leads.json"),
        ("IntentLock_L3_Manager_Detailed_Profiles.docx", "managers", "managers.json"),
        ("IntentLock_L4_Director_Senior_Manager_Detailed_Profiles.docx", "directors", "directors.json"),
        ("IntentLock_L5_Executive_Administrator_Detailed_Profiles.docx", "executive_administrators", "executive_administrators.json"),
        ("IntentLock_RnD_Team_Detailed_Profiles.docx", "rnd_team", "rnd_team.json"),
    ]

    category_records: Dict[str, List[Dict[str, Any]]] = {}
    all_employees_dict: Dict[str, Dict[str, Any]] = {}
    cto_standalone_record: Optional[Dict[str, Any]] = None

    for fname, cat_name, out_json in file_configs:
        records = parse_docx_file(fname, cat_name)
        category_records[cat_name] = records
        
        # Save individual source category JSON file
        cat_path = os.path.join(BACKEND_SOURCE_DIR, out_json)
        with open(cat_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)

        for rec in records:
            eid = rec["employee_id"]
            if eid == "EMP-4002" and cat_name == "cto":
                cto_standalone_record = rec
            elif eid == "EMP-4002" and cat_name == "executive_administrators":
                # Will merge after loop
                pass
            else:
                all_employees_dict[eid] = rec

    # Handle EMP-4002 CTO Merge
    l5_cto_rec = next((r for r in category_records.get("executive_administrators", []) if r["employee_id"] == "EMP-4002"), None)
    if cto_standalone_record and l5_cto_rec:
        canonical_cto = merge_cto_records(cto_standalone_record, l5_cto_rec)
        all_employees_dict["EMP-4002"] = canonical_cto
    elif cto_standalone_record:
        all_employees_dict["EMP-4002"] = cto_standalone_record
    elif l5_cto_rec:
        all_employees_dict["EMP-4002"] = l5_cto_rec

    # Build bidirectional direct reports
    for eid, emp in all_employees_dict.items():
        mgr_id = emp["reporting"]["manager_id"]
        if mgr_id and mgr_id in all_employees_dict:
            mgr_reports = all_employees_dict[mgr_id]["reporting"]["direct_report_ids"]
            if eid not in mgr_reports:
                mgr_reports.append(eid)

    all_employees_list = sorted(list(all_employees_dict.values()), key=lambda x: x["employee_id"])

    # Perform thorough validations
    val_unique_ids = len(set(e["employee_id"] for e in all_employees_list)) == len(all_employees_list)
    val_unique_emails = len(set(e["identity"]["work_email"] for e in all_employees_list)) == len(all_employees_list)
    
    # Manager validation & circular check
    val_managers = True
    val_no_circular = True
    for emp in all_employees_list:
        mgr_id = emp["reporting"]["manager_id"]
        if mgr_id and mgr_id not in all_employees_dict:
            # Only CEO is permitted to have no internal manager ID (reports to Board)
            if emp["employee_id"] != "EXE-0001":
                val_managers = False
        
        # Check circular
        curr_id = emp["employee_id"]
        visited = {curr_id}
        step_mgr = mgr_id
        while step_mgr and step_mgr in all_employees_dict:
            if step_mgr in visited:
                val_no_circular = False
                break
            visited.add(step_mgr)
            step_mgr = all_employees_dict[step_mgr]["reporting"]["manager_id"]

    val_schema = True
    for emp in all_employees_list:
        if not emp.get("employee_id") or not emp.get("identity") or not emp.get("employment") or not emp.get("skills"):
            val_schema = False
            break

    # Save canonical runtime dataset
    canonical_path = os.path.join(BACKEND_DATA_DIR, "all_employees.json")
    with open(canonical_path, "w", encoding="utf-8") as f:
        json.dump(all_employees_list, f, indent=2, ensure_ascii=False)

    # Print official validation summary
    total_count = len(all_employees_list)
    print("\nIntentLock Employee Knowledge Validation\n")
    print(f"Employees processed: {total_count}\n")
    print(f"Unique IDs: {'PASS' if val_unique_ids else 'FAIL'}")
    print(f"Reporting relationships: {'PASS' if val_no_circular else 'FAIL'}")
    print(f"Manager references: {'PASS' if val_managers else 'FAIL'}")
    print(f"Duplicate employees: {'NONE' if val_unique_ids else 'DUPLICATES FOUND'}")
    print(f"Duplicate emails: {'NONE' if val_unique_emails else 'DUPLICATES FOUND'}")
    print(f"Schema validation: {'PASS' if val_schema else 'FAIL'}\n")
    print("Knowledge base generated successfully.\n")

if __name__ == "__main__":
    build_knowledge_base()
