import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import SQLAlchemyError

from app.services import cache, reservations
from app.core.database_pool import DatabasePool


class CalendarAndMoneyTests(unittest.TestCase):
    def test_paris_march_includes_utc_february_and_dst(self):
        start, end = reservations.period_bounds(2024, 3, "Europe/Paris")
        self.assertEqual(start, datetime(2024, 2, 29, 23, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2024, 3, 31, 22, tzinfo=timezone.utc))

    def test_new_york_march_boundaries_change_offset(self):
        start, end = reservations.period_bounds(2024, 3, "America/New_York")
        self.assertEqual(start, datetime(2024, 3, 1, 5, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2024, 4, 1, 4, tzinfo=timezone.utc))

    def test_december_and_annual_rollover(self):
        start, end = reservations.period_bounds(2024, 12, "Europe/Paris")
        self.assertEqual(start, datetime(2024, 11, 30, 23, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2024, 12, 31, 23, tzinfo=timezone.utc))
        start, end = reservations.period_bounds(2024, None, "Europe/Paris")
        self.assertEqual(start, datetime(2023, 12, 31, 23, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2024, 12, 31, 23, tzinfo=timezone.utc))

    def test_round_only_after_summing_subcent_amounts(self):
        total = sum(map(Decimal, ["333.333", "333.333", "333.334"]))
        self.assertEqual(reservations.format_amount(total), "1000.00")

    def test_half_cents_and_large_totals_remain_exact(self):
        for raw, expected in [("2.675", "2.68"), ("1.005", "1.01"), ("-1.005", "-1.01"),
                              ("90071992547409.915", "90071992547409.92")]:
            with self.subTest(raw=raw):
                self.assertEqual(reservations.format_amount(Decimal(raw)), expected)


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.values = {}
        self.redis = AsyncMock()
        self.redis.get.side_effect = lambda key: self.values.get(key)
        self.redis.setex.side_effect = lambda key, ttl, value: self.values.__setitem__(key, value)
        self.cache_patch = patch.object(cache, "redis_client", self.redis)
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)

    async def test_same_property_id_never_shares_revenue_between_tenants(self):
        async def calculate(property_id, tenant_id, **kwargs):
            return {"property_id": property_id, "tenant_id": tenant_id,
                    "total": "2250.00" if tenant_id == "tenant-a" else "0.00"}
        with patch.object(reservations, "calculate_total_revenue", side_effect=calculate) as calculate_mock:
            for first, second in [("tenant-a", "tenant-b"), ("tenant-b", "tenant-a")]:
                self.values.clear()
                a = await cache.get_revenue_summary("prop-001", first)
                b = await cache.get_revenue_summary("prop-001", second)
                self.assertEqual(a["tenant_id"], first)
                self.assertEqual(b["tenant_id"], second)
                self.assertNotEqual(a["total"], b["total"])
            await cache.get_revenue_summary("prop-001", second)
            self.assertEqual(calculate_mock.call_count, 4)

    async def test_periods_and_old_cache_entries_do_not_collide(self):
        self.values["revenue:prop-001"] = json.dumps({"tenant_id": "tenant-b", "total": "wrong"})
        async def calculate(property_id, tenant_id, **kwargs):
            return {"property_id": property_id, "tenant_id": tenant_id, **kwargs}
        with patch.object(reservations, "calculate_total_revenue", side_effect=calculate) as mocked:
            for month, year in [(None, None), (None, 2024), (2, 2024), (3, 2024), (3, 2025)]:
                result = await cache.get_revenue_summary("prop-001", "tenant-a", month, year)
                self.assertEqual((result["month"], result["year"]), (month, year))
            self.assertEqual(mocked.call_count, 5)

    async def test_cache_outage_uses_real_database_result(self):
        self.redis.get.side_effect = RedisConnectionError("offline")
        self.redis.setex.side_effect = RedisConnectionError("offline")
        with patch.object(reservations, "calculate_total_revenue", return_value={"total": "2250.00"}):
            result = await cache.get_revenue_summary("prop-001", "tenant-a")
            self.assertEqual(result["total"], "2250.00")

    async def test_failed_database_result_is_not_cached_or_fabricated(self):
        with patch.object(reservations, "calculate_total_revenue", side_effect=SQLAlchemyError("offline")):
            with self.assertRaises(SQLAlchemyError):
                await cache.get_revenue_summary("prop-001", "tenant-a")
        self.redis.setex.assert_not_awaited()

    async def test_missing_tenant_never_reads_cache(self):
        with self.assertRaises(ValueError):
            await cache.get_revenue_summary("prop-001", "")
        self.redis.get.assert_not_awaited()


class PoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_pool_uses_configured_database_and_reuses_engine(self):
        pool = DatabasePool()
        with patch("app.core.database_pool.settings") as settings, \
                patch("app.core.database_pool.create_async_engine") as create:
            settings.database_url = "postgresql://postgres:postgres@localhost:5433/propertyflow"
            await pool.initialize()
            await pool.initialize()
            self.assertEqual(create.call_count, 1)
            self.assertEqual(create.call_args.args[0].drivername, "postgresql+asyncpg")
            self.assertEqual(create.call_args.args[0].port, 5433)
            self.assertNotIn("poolclass", create.call_args.kwargs)
            self.assertTrue(hasattr(pool.get_session(), "__aenter__"))


if __name__ == "__main__":
    unittest.main()
