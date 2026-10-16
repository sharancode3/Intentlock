"""
IntentLock — Knowledge & Health API Request and Response Models
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class KnowledgeQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language question about company policies or employees")
    actor_id: Optional[str] = Field(None, description="Untrusted caller ID claim (verified on backend)")
    actor_role: Optional[str] = Field(None, description="Untrusted caller role claim (verified on backend)")
    is_authenticated: bool = Field(False, description="Untrusted caller auth claim (verified on backend)")


class EmployeeSummaryItem(BaseModel):
    employee_id: str
    full_name: str
    designation: str
    department: str
    organizational_level: str


class KnowledgeQueryResponse(BaseModel):
    query: str
    answer: str
    matched_employees: List[EmployeeSummaryItem] = Field(default_factory=list)
    source_references: List[str] = Field(default_factory=list)
    filters_extracted: Optional[Dict[str, Any]] = Field(default=None, description="Internal filter debug output (sanitized in production)")
    context_used: Optional[str] = Field(default=None, description="Raw context debug output (sanitized in production)")
    grounded: bool = True
    model_used: str


class HealthResponse(BaseModel):
    status: str
    project: str
    version: str
    indexed_employees_count: int
    ollama_model: str
    ollama_reachable: bool
    data_source: str
    voice_pipeline_ready: bool = False


class LivenessResponse(BaseModel):
    status: str = "live"
    project: str
    version: str
    timestamp: str


class ReadinessResponse(BaseModel):
    status: str
    project: str
    components: Dict[str, str]
    reason: Optional[str] = None
