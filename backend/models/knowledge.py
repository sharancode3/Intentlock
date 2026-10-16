"""
IntentLock — Knowledge API Request and Response Models
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class KnowledgeQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language question about company or employees")
    actor_id: Optional[str] = Field(None, description="Current authenticated employee ID, if any")
    actor_role: Optional[str] = Field(None, description="Role of the caller (employee, manager, executive)")
    is_authenticated: bool = Field(False, description="Whether caller has a verified active session")

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
    filters_extracted: Dict[str, Any] = Field(default_factory=dict)
    context_used: str = ""
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
