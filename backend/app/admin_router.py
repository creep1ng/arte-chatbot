"""Admin panel router for FastAPI backend.

Groups all admin endpoints under the /admin prefix.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.admin_auth import verify_admin_key

admin_router = APIRouter(prefix="/admin")


@admin_router.get("/health")
async def admin_health(
    _admin_key: Annotated[str, Depends(verify_admin_key)],
) -> dict[str, str]:
    """Health check endpoint for the admin panel service.

    Returns:
        Static JSON payload indicating the admin service is healthy.
    """
    return {
        "status": "healthy",
        "service": "arte-chatbot-admin",
    }
