import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import authenticate_request as get_current_user
from app.models.auth import AuthenticatedUser
from app.services.cache import get_revenue_summary
from app.services.reservations import PropertyNotFoundError, list_properties

router = APIRouter()
logger = logging.getLogger(__name__)


def require_tenant(user: AuthenticatedUser) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return user.tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    response: Response,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[dict]:
    response.headers["Cache-Control"] = "private, no-store"
    tenant_id = require_tenant(current_user)
    try:
        return await list_properties(tenant_id)
    except (SQLAlchemyError, OSError):
        logger.exception("Property query failed")
        raise HTTPException(status_code=503, detail="Property data is temporarily unavailable")


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    response: Response,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    year: Annotated[int | None, Query(ge=1, le=9998)] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    tenant_id = require_tenant(current_user)
    if month is not None and year is None:
        raise HTTPException(status_code=422, detail="A month requires a year")
    try:
        data = await get_revenue_summary(property_id, tenant_id, month=month, year=year)
    except PropertyNotFoundError:
        raise HTTPException(status_code=404, detail="Property not found")
    except (SQLAlchemyError, OSError, ValueError):
        logger.exception("Revenue query failed")
        raise HTTPException(status_code=503, detail="Revenue data is temporarily unavailable")

    return {
        "property_id": data["property_id"],
        "total_revenue": data["total"],
        "currency": data["currency"],
        "totals_by_currency": data["totals_by_currency"],
        "reservations_count": data["count"],
        "month": data["month"],
        "year": data["year"],
        "timezone": data["timezone"],
    }
