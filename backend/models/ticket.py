"""
IntentLock — Canonical Ticket Pydantic Models
Strongly-typed schemas matching the canonical ticket knowledge structure and frontend contracts.
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

TicketStatusType = Literal["Open", "In Progress", "Pending", "Blocked", "Resolved", "Closed"]
TicketPriorityType = Literal["Low", "Medium", "High", "Critical"]
TicketSeverityType = Literal["S1", "S2", "S3", "S4"]
ApprovalStatusType = Literal["Not Required", "Pending", "Approved", "Rejected"]
SlaStatusType = Literal["Within SLA", "At Risk", "Breached", "Met"]

class SlaInfo(BaseModel):
    response_target_hours: float = 2.0
    resolution_target_hours: float = 48.0
    response_met: bool = True
    resolution_status: SlaStatusType = "Within SLA"

class EscalationInfo(BaseModel):
    is_escalated: bool = False
    escalated_to: Optional[str] = None
    escalation_level: Optional[str] = None
    escalated_at: Optional[str] = None
    reason: Optional[str] = None

class ApprovalInfo(BaseModel):
    required: bool = False
    status: ApprovalStatusType = "Not Required"
    approver_id: Optional[str] = None
    approved_at: Optional[str] = None
    reason: Optional[str] = None

class TicketCommentItem(BaseModel):
    comment_id: str
    author_id: str
    author_name: Optional[str] = None
    created_at: str
    comment: str

class TicketActivityItem(BaseModel):
    timestamp: str
    type: str
    actor: str
    description: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None

class ResolutionInfo(BaseModel):
    summary: Optional[str] = None
    root_cause: Optional[str] = None
    resolution_action: Optional[str] = None
    resolved_by: Optional[str] = None

class CanonicalTicketRecord(BaseModel):
    ticket_id: str
    title: str
    description: str
    ticket_type: str = "Bug"
    category: str = "General"
    subcategory: Optional[str] = None
    status: TicketStatusType = "Open"
    priority: TicketPriorityType = "Medium"
    severity: TicketSeverityType = "S3"
    requester_id: str
    assignee_id: Optional[str] = None
    created_by: str
    owner_team: str = "Engineering"
    department: str = "Engineering"
    project: str = "Customer Support Portal"
    created_at: str
    updated_at: str
    due_date: Optional[str] = None
    resolved_at: Optional[str] = None
    closed_at: Optional[str] = None
    sla: SlaInfo = Field(default_factory=SlaInfo)
    affected_systems: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    escalation: EscalationInfo = Field(default_factory=EscalationInfo)
    approval: ApprovalInfo = Field(default_factory=ApprovalInfo)
    comments: List[TicketCommentItem] = Field(default_factory=list)
    activity_history: List[TicketActivityItem] = Field(default_factory=list)
    resolution: ResolutionInfo = Field(default_factory=ResolutionInfo)
