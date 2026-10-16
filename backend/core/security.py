"""
IntentLock — Gateway Security & Policy Facade
Enforces central HTTP route protection, rejects client-authored authority claims,
and implements fail-closed authorization boundaries for private employee data.
"""

from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


class AuthorizationPolicyFacade:
    """
    Backend-owned policy enforcement facade.
    Replaces client-asserted parameters and incomplete visibility heuristics
    with an authoritative server-side boundary.
    """

    @staticmethod
    def is_public_query(query: str) -> bool:
        """
        Determines whether a query requests only intentionally approved public facts
        (e.g., general company office policies).
        Dataset presence alone is NEVER considered public.
        """
        # For Stage 1, all employee records and private queries require verified authentication
        return False

    @staticmethod
    def reject_untrusted_client_claims(
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        is_authenticated: Optional[bool] = None,
    ) -> None:
        """
        Detects if an untrusted client attempted to author its own authority.
        Raises HTTP 403 Forbidden if client-asserted privilege elevation is attempted.
        """
        if is_authenticated is True or actor_role or (actor_id and actor_id.startswith("EXE-")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Client-authored authority claims (is_authenticated, actor_role, executive IDs) are strictly forbidden.",
            )


def require_verified_session(request: Request) -> Dict[str, Any]:
    """
    Central HTTP route guard for private employee and knowledge endpoints.
    In Stage 2, validates server-issued session tokens from IdentityMappingStore.
    Fails closed if the token is missing, expired, revoked, or invalid.
    """
    # Check for client-authored parameter forgery in query params
    query_params = request.query_params
    actor_id = query_params.get("actor_id")
    actor_role = query_params.get("actor_role")
    is_auth_str = query_params.get("is_authenticated", "").lower()
    is_auth = is_auth_str in ("true", "1", "yes")

    if is_auth or actor_role or (actor_id and actor_id.startswith("EXE-")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client-authored authority claims are rejected by the gateway.",
        )

    # Check for forbidden token in query parameters
    if "session_id" in query_params or "token" in query_params or "session_token" in query_params:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Security policy violation: session tokens must be provided in headers (X-Session-Token or Authorization: Bearer), never in URL query parameters.",
        )

    # Extract session token from Authorization: Bearer <token>, X-Session-Token, or X-Session-Id header
    auth_header = request.headers.get("Authorization", "")
    session_token = None
    if auth_header.startswith("Bearer "):
        session_token = auth_header[7:].strip()
    elif "X-Session-Token" in request.headers:
        session_token = request.headers.get("X-Session-Token", "").strip()
    elif "X-Session-Id" in request.headers:
        session_token = request.headers.get("X-Session-Id", "").strip()

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Unauthenticated access to private employee records is denied. Voice verification required via /api/v1/voice/turn.",
        )

    # Validate against durable SQLite session store
    from backend.adapters.identity_mapping_store import IdentityMappingStore

    store = IdentityMappingStore.get_instance()
    session = store.get_session(session_token)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unrecognized session token. Please authenticate via voice verification.",
        )

    if session.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been explicitly terminated. Please re-authenticate via voice verification.",
        )

    if session.is_expired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Re-authentication via voice verification is required.",
        )

    return {
        "session_id": session.session_id,
        "employee_id": session.employee_id,
        "full_name": session.full_name,
        "role": session.role,
        "department": session.department,
        "team_id": session.team_id,
        "seconds_remaining": session.seconds_remaining,
    }
