"""
IntentLock — Canonical Employee Pydantic Models
Strongly-typed schemas matching the canonical employee knowledge structure.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class EmployeeIdentity(BaseModel):
    full_name: str
    preferred_name: str
    work_email: str

class EmploymentDetails(BaseModel):
    designation: str
    department: str
    sub_department: Optional[str] = None
    organizational_level: str
    research_level: Optional[str] = None
    employment_type: str = "Full-Time"
    status: str = "Active"
    location: str = "Bengaluru"
    work_mode: str = "Hybrid"
    date_of_joining: Optional[str] = None

class ReportingStructure(BaseModel):
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    direct_report_ids: List[str] = Field(default_factory=list)

class CareerHistoryItem(BaseModel):
    organization: str
    role: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    responsibilities: List[str] = Field(default_factory=list)

class ExperienceProfile(BaseModel):
    total_years: float = 0.0
    professional_summary: str = ""
    career_history: List[CareerHistoryItem] = Field(default_factory=list)

class EducationItem(BaseModel):
    degree: str
    institution: str
    graduation_year: Optional[str] = None
    details: Optional[str] = None

class EmployeeSkills(BaseModel):
    technical: List[str] = Field(default_factory=list)
    management: List[str] = Field(default_factory=list)
    research: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)

class ProjectItem(BaseModel):
    name: str
    role: str
    allocation_percent: Optional[int] = None
    status: str = "Active"
    responsibilities: List[str] = Field(default_factory=list)

class EmployeeProjects(BaseModel):
    current: List[ProjectItem] = Field(default_factory=list)
    previous: List[ProjectItem] = Field(default_factory=list)

class PermissionRule(BaseModel):
    effect: str = "DENY"  # ALLOW, DENY, RECOMMEND_ONLY, REQUIRE_APPROVAL, REQUIRE_STEP_UP
    scope: str = "SELF"   # SELF, DIRECT_REPORTS, TEAM, DEPARTMENT, BUSINESS_UNIT, ENTERPRISE, SPECIFIC_RESOURCE
    description: Optional[str] = None
    requires_verification: bool = False

class SecurityScope(BaseModel):
    can_change_own_authority: bool = False
    can_grant_self_admin: bool = False
    can_disable_intentlock: bool = False
    can_delete_audit_history: bool = False
    can_bypass_speaker_verification: bool = False
    can_execute_arbitrary_commands: bool = False
    can_reveal_private_keys: bool = False
    cannot_view: List[str] = Field(default_factory=list)
    cannot_perform: List[str] = Field(default_factory=list)
    resource_scope: str = "Assigned scope"
    self_elevation_restrictions: str = "Strictly prohibited"

class VoiceAuthority(BaseModel):
    can_modify_by_voice: List[str] = Field(default_factory=list)
    can_approve_by_voice: List[str] = Field(default_factory=list)
    can_recommend_by_voice: List[str] = Field(default_factory=list)
    requires_approval: List[str] = Field(default_factory=list)
    allowed_commands: List[str] = Field(default_factory=list)
    denied_commands: List[str] = Field(default_factory=list)
    high_risk_actions: List[str] = Field(default_factory=list)
    security_policy: str = "Verified voice establishes identity evidence; permissions enforced independently."

class ResearchProfile(BaseModel):
    specialization: str
    secondary_areas: List[str] = Field(default_factory=list)
    research_experience_years: float = 0.0
    publications: List[str] = Field(default_factory=list)
    patents: List[str] = Field(default_factory=list)
    prototypes: List[str] = Field(default_factory=list)
    datasets: List[str] = Field(default_factory=list)
    models: List[str] = Field(default_factory=list)
    compute_access: str = "Assigned Cluster"
    source_code_access: str = "R&D Repositories"
    ip_scope: str = "Strictly Protected"
    model_release_rule: str = "Requires AI Governance Approval"
    dataset_release_rule: str = "Cannot export or publish restricted datasets"

class ExecutiveAuthority(BaseModel):
    board_relationship: str
    financial_authority: str
    budget_authority: str
    headcount_authority: str
    signing_authority: str
    ma_authority: str
    crisis_authority: str
    risk_ownership: str
    technology_authority: Optional[str] = None

class DataProvenance(BaseModel):
    source_document: str
    source_type: str = "DOCX"
    import_version: str = "1.0"
    category: Optional[str] = None
    merged_from: Optional[List[str]] = None

class EmployeeRecord(BaseModel):
    employee_id: str
    identity: EmployeeIdentity
    employment: EmploymentDetails
    reporting: ReportingStructure
    experience: ExperienceProfile
    education: List[EducationItem] = Field(default_factory=list)
    skills: EmployeeSkills
    projects: EmployeeProjects
    responsibilities: List[str] = Field(default_factory=list)
    achievements: List[str] = Field(default_factory=list)
    permissions: Dict[str, Any] = Field(default_factory=dict)
    security_scope: SecurityScope
    voice_authority: VoiceAuthority
    research: Optional[ResearchProfile] = None
    executive_authority: Optional[ExecutiveAuthority] = None
    recent_activity: List[str] = Field(default_factory=list)
    provenance: DataProvenance
