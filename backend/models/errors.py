"""
IntentLock — Safe Error Models
Standardized error structures preventing leakage of internal tracebacks,
secrets, or sensitive employee records.
"""

from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class SafeErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error classification code")
    message: str = Field(..., description="Safe human-readable explanation")
    retryable: bool = Field(False, description="Whether the exact same client request can be retried immediately")


class SafeErrorResponse(BaseModel):
    api_version: str = Field("1", description="API version discriminator")
    request_id: str = Field(..., description="Server-generated request correlation identifier")
    error: SafeErrorDetail
