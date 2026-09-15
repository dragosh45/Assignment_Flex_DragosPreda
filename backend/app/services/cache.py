import json
import logging
import os

import redis.asyncio as redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


async def get_revenue_summary(property_id: str, tenant_id: str, month=None, year=None) -> dict:
    if not tenant_id:
        raise ValueError("Tenant is required")
    # Versioning also prevents serving stale, unscoped values after deployment.
    cache_key = "revenue:v2:" + json.dumps([tenant_id, property_id, year, month])
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            result = json.loads(cached)
            if result.get("tenant_id") == tenant_id and result.get("property_id") == property_id:
                return result
    except (RedisError, ValueError, AttributeError):
        logger.warning("Revenue cache unavailable; querying the database")

    from app.services.reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id, month=month, year=year)
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except RedisError:
        logger.warning("Revenue cache write failed")
    return result
