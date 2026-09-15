from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.database_pool import db_pool


class PropertyNotFoundError(ValueError):
    pass


def period_bounds(year: int, month: int | None, timezone_name: str):
    """Convert the property's local calendar boundaries to a half-open UTC range."""
    zone = ZoneInfo(timezone_name)
    start = datetime(year, month or 1, 1, tzinfo=zone)
    if month is None or month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=zone)
    else:
        end = datetime(year, month + 1, 1, tzinfo=zone)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def format_amount(amount: Decimal) -> str:
    # Keep all stored precision during aggregation; round the final report once.
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def list_properties(tenant_id: str):
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(
            text("SELECT id, name, timezone FROM properties WHERE tenant_id = :tenant_id ORDER BY id"),
            {"tenant_id": tenant_id},
        )
        return [dict(row) for row in result.mappings()]


async def calculate_total_revenue(
    property_id: str, tenant_id: str, month: int | None = None,
    year: int | None = None, db_session=None,
) -> dict:
    if not tenant_id:
        raise ValueError("Tenant is required")
    if month is not None and year is None:
        raise ValueError("A month requires a year")

    if db_session is None:
        await db_pool.initialize()
        async with db_pool.get_session() as session:
            return await calculate_total_revenue(property_id, tenant_id, month, year, session)

    params = {"property_id": property_id, "tenant_id": tenant_id}
    property_result = await db_session.execute(text("""
        SELECT timezone FROM properties
        WHERE id = :property_id AND tenant_id = :tenant_id
    """), params)
    property_timezone = property_result.scalar_one_or_none()
    if property_timezone is None:
        raise PropertyNotFoundError("Property not found")

    period_filter = ""
    if year is not None:
        params["start"], params["end"] = period_bounds(year, month, property_timezone)
        period_filter = "AND check_in_date >= :start AND check_in_date < :end"

    result = await db_session.execute(text(f"""
        SELECT currency, SUM(total_amount) AS total, COUNT(*) AS count
        FROM reservations
        WHERE property_id = :property_id AND tenant_id = :tenant_id
        {period_filter}
        GROUP BY currency ORDER BY currency
    """), params)
    rows = list(result.mappings())
    # No exchange rates are supplied: keep unlike currencies separate.
    totals = {row["currency"]: format_amount(row["total"]) for row in rows}
    if None in totals:
        raise ValueError("Reservation currency is missing")
    currency = next(iter(totals)) if len(totals) == 1 else None
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": totals[currency] if currency else ("0.00" if not totals else None),
        "currency": currency,
        "totals_by_currency": totals,
        "count": sum(row["count"] for row in rows),
        "month": month,
        "year": year,
        "timezone": property_timezone,
    }


async def calculate_monthly_revenue(
    property_id: str, month: int, year: int, tenant_id: str,
    db_session=None, currency: str = "USD",
) -> Decimal:
    """Monthly revenue in one currency, using the same query as the dashboard."""
    summary = await calculate_total_revenue(property_id, tenant_id, month, year, db_session)
    return Decimal(summary["totals_by_currency"].get(currency, "0.00"))
