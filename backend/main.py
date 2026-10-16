"""
IntentLock — FastAPI Backend Application
Central entrypoint providing the Employee Knowledge Service, Ollama retrieval,
and truthful company assistance endpoints.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
import httpx

from backend.core.config import settings
from backend.services.employee_knowledge_service import EmployeeKnowledgeService
from backend.services.employee_visibility_service import EmployeeVisibilityService
from backend.services.ollama_knowledge_service import OllamaKnowledgeService
from backend.models.knowledge import (
    KnowledgeQueryRequest,
    KnowledgeQueryResponse,
    HealthResponse,
    EmployeeSummaryItem,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("intentlock_backend")

# Global singleton service instances
knowledge_service: Optional[EmployeeKnowledgeService] = None
ollama_service: Optional[OllamaKnowledgeService] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global knowledge_service, ollama_service
    logger.info("Initializing IntentLock Employee Knowledge Base...")
    knowledge_service = EmployeeKnowledgeService.get_instance(data_path=settings.DATA_PATH)
    ollama_service = OllamaKnowledgeService(
        knowledge_service=knowledge_service,
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL,
        timeout=settings.OLLAMA_TIMEOUT_SECONDS,
    )
    logger.info(
        f"Backend startup complete. {len(knowledge_service.list_all_employees())} employees loaded in memory."
    )
    yield
    logger.info("Shutting down IntentLock backend.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="IntentLock Shared AI Assistance Workspace — Backend & Employee Knowledge Service",
    lifespan=lifespan,
)

# CORS configuration for frontend dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Health and Diagnostics Endpoints
# =============================================================================

@app.get(f"{settings.API_V1_PREFIX}/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """Verify backend health, dataset load status, and local Ollama reachability."""
    svc = EmployeeKnowledgeService.get_instance()
    total_emps = len(svc.list_all_employees())

    ollama_online = False
    try:
        with httpx.Client(timeout=1.0) as client:
            res = client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            ollama_online = res.status_code == 200
    except Exception:
        ollama_online = False

    return HealthResponse(
        status="HEALTHY",
        project=settings.PROJECT_NAME,
        version=settings.VERSION,
        indexed_employees_count=total_emps,
        ollama_model=settings.OLLAMA_MODEL,
        ollama_reachable=ollama_online,
        data_source=settings.DATA_PATH,
    )

# =============================================================================
# Knowledge Query Endpoint (Natural Language Question -> Grounded Answer)
# =============================================================================

@app.post(
    f"{settings.API_V1_PREFIX}/knowledge/query",
    response_model=KnowledgeQueryResponse,
    tags=["Knowledge"],
)
def query_employee_knowledge(req: KnowledgeQueryRequest):
    """
    Query employee/company knowledge using natural language.
    Retrieves strictly scoped records from the canonical in-memory dataset,
    filters visibility, and queries local Ollama with the strict grounding prompt.
    """
    svc = ollama_service or OllamaKnowledgeService()
    result = svc.answer_query(
        query=req.query,
        actor_id=req.actor_id,
        actor_role=req.actor_role,
        is_authenticated=req.is_authenticated,
    )

    summaries = [
        EmployeeSummaryItem(
            employee_id=m["employee_id"],
            full_name=m["full_name"],
            designation=m["designation"],
            department=m["department"],
            organizational_level=m["organizational_level"],
        )
        for m in result.get("matched_employees", [])
    ]

    return KnowledgeQueryResponse(
        query=req.query,
        answer=result["answer"],
        matched_employees=summaries,
        filters_extracted=result.get("filters_extracted", {}),
        context_used=result.get("context_used", ""),
        grounded=result.get("grounded", True),
        model_used=result.get("model_used", settings.OLLAMA_MODEL),
    )

# =============================================================================
# Direct Employee Directory Endpoints (Shared with Data-Rendering Frontend)
# =============================================================================

@app.get(f"{settings.API_V1_PREFIX}/employees", tags=["Employees"])
def list_employees(
    department: Optional[str] = Query(None, description="Filter by department"),
    role: Optional[str] = Query(None, description="Filter by designation/role keyword"),
    limit: int = Query(50, ge=1, le=100),
    actor_id: Optional[str] = Query(None, description="Caller employee ID"),
    actor_role: Optional[str] = Query(None, description="Caller role"),
    is_authenticated: bool = Query(False, description="Whether caller is authenticated"),
):
    """
    Retrieve all visible employee records for the directory table/cards.
    Ensures data rendering and Ollama share the identical canonical truth source.
    """
    svc = EmployeeKnowledgeService.get_instance()
    all_emps = svc.list_all_employees()

    filtered = []
    for emp in all_emps:
        if department and department.lower() not in emp["employment"]["department"].lower():
            continue
        if role and role.lower() not in emp["employment"]["designation"].lower():
            continue

        clean_emp = EmployeeVisibilityService.filter_employee(
            target=emp,
            actor_id=actor_id,
            actor_role=actor_role,
            is_authenticated=is_authenticated,
        )
        filtered.append(clean_emp)
        if len(filtered) >= limit:
            break

    return {
        "total": len(filtered),
        "employees": filtered,
    }

@app.get(f"{settings.API_V1_PREFIX}/employees/search", tags=["Employees"])
def search_employees(
    q: str = Query(..., min_length=1, description="Search term for name, skill, project, or department"),
    actor_id: Optional[str] = Query(None),
    actor_role: Optional[str] = Query(None),
    is_authenticated: bool = Query(False),
):
    """Search employees across identity, skills, projects, and departments."""
    svc = EmployeeKnowledgeService.get_instance()
    results = svc.search_employees(q)
    filtered = [
        EmployeeVisibilityService.filter_employee(
            target=e,
            actor_id=actor_id,
            actor_role=actor_role,
            is_authenticated=is_authenticated,
        )
        for e in results
    ]
    return {
        "query": q,
        "count": len(filtered),
        "results": filtered,
    }

@app.get(f"{settings.API_V1_PREFIX}/employees/{{employee_id}}", tags=["Employees"])
def get_employee(
    employee_id: str,
    actor_id: Optional[str] = Query(None),
    actor_role: Optional[str] = Query(None),
    is_authenticated: bool = Query(False),
):
    """Retrieve detailed profile for a specific employee ID."""
    svc = EmployeeKnowledgeService.get_instance()
    emp = svc.get_employee_by_id(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee {employee_id} not found.")

    clean_emp = EmployeeVisibilityService.filter_employee(
        target=emp,
        actor_id=actor_id,
        actor_role=actor_role,
        is_authenticated=is_authenticated,
    )
    return clean_emp

@app.get(f"{settings.API_V1_PREFIX}/employees/{{employee_id}}/reporting", tags=["Employees"])
def get_employee_reporting_tree(employee_id: str):
    """Retrieve the manager and direct reports for an employee."""
    svc = EmployeeKnowledgeService.get_instance()
    emp = svc.get_employee_by_id(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee {employee_id} not found.")

    manager = svc.get_manager(employee_id)
    direct_reports = svc.get_direct_reports(employee_id)
    chain = svc.get_reporting_chain(employee_id)

    return {
        "employee_id": employee_id,
        "full_name": emp["identity"]["full_name"],
        "manager": {
            "employee_id": manager["employee_id"],
            "full_name": manager["identity"]["full_name"],
            "designation": manager["employment"]["designation"],
        } if manager else None,
        "direct_reports": [
            {
                "employee_id": r["employee_id"],
                "full_name": r["identity"]["full_name"],
                "designation": r["employment"]["designation"],
            }
            for r in direct_reports
        ],
        "reporting_chain_upwards": [
            {
                "employee_id": c["employee_id"],
                "full_name": c["identity"]["full_name"],
                "designation": c["employment"]["designation"],
            }
            for c in chain
        ],
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
