"""Real PostgreSQL regressions; all inserted test rows are rolled back."""
import os
import unittest
from datetime import datetime, timezone, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.services.reservations import calculate_total_revenue, PropertyNotFoundError


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL to the seeded PostgreSQL database")
class RevenueDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        self.connection = await self.engine.connect()
        self.transaction = await self.connection.begin()
        self.session = AsyncSession(bind=self.connection)

    async def asyncTearDown(self):
        await self.session.close()
        await self.transaction.rollback()
        await self.connection.close()
        await self.engine.dispose()

    async def summary(self, property_id="prop-001", tenant_id="tenant-a", month=3, year=2024):
        return await calculate_total_revenue(property_id, tenant_id, month, year, self.session)

    async def test_seeded_march_is_2250_and_four_reservations(self):
        data = await self.summary()
        self.assertEqual(data["total"], "2250.00")
        self.assertEqual(data["count"], 4)
        self.assertEqual((await self.summary(month=2))["total"], "0.00")
        self.assertEqual((await self.summary(month=None))["total"], "2250.00")

    async def test_same_id_other_tenant_has_no_reservations(self):
        data = await self.summary(tenant_id="tenant-b")
        self.assertEqual(data["total"], "0.00")
        self.assertEqual(data["count"], 0)

    async def test_other_tenants_property_is_not_found(self):
        with self.assertRaises(PropertyNotFoundError):
            await self.summary("prop-002", "tenant-b")

    async def test_database_session_timezone_does_not_change_report(self):
        await self.session.execute(text("SET LOCAL TIME ZONE 'Pacific/Honolulu'"))
        self.assertEqual((await self.summary())["total"], "2250.00")

    async def test_half_open_boundaries_precision_and_currencies(self):
        for zone, start, end in [
            ("Europe/Paris", datetime(2024, 2, 29, 23, tzinfo=timezone.utc), datetime(2024, 3, 31, 22, tzinfo=timezone.utc)),
            ("America/New_York", datetime(2024, 3, 1, 5, tzinfo=timezone.utc), datetime(2024, 4, 1, 4, tzinfo=timezone.utc)),
        ]:
            property_id = "regression-" + zone
            await self.session.execute(text("""
                INSERT INTO properties(id, tenant_id, name, timezone)
                VALUES (:id, 'tenant-a', 'Regression fixture', :zone)
            """), {"id": property_id, "zone": zone})
            for index, (instant, amount, currency) in enumerate([
                (start - timedelta(microseconds=1), "900", "USD"),
                (start, "333.333", "USD"),
                (start + timedelta(days=1), "333.333", "USD"),
                (end - timedelta(microseconds=1), "333.334", "USD"),
                (end, "900", "USD"),
                (start, "2.675", "EUR"),
            ]):
                await self.session.execute(text("""
                    INSERT INTO reservations(id, property_id, tenant_id, check_in_date, check_out_date, total_amount, currency)
                    VALUES (:id, :property, 'tenant-a', :instant, :checkout, CAST(:amount AS NUMERIC), :currency)
                """), {"id": f"{property_id}-{index}", "property": property_id, "instant": instant,
                        "checkout": instant + timedelta(days=1), "amount": amount, "currency": currency})
            data = await self.summary(property_id)
            self.assertEqual(data["totals_by_currency"], {"EUR": "2.68", "USD": "1000.00"})
            self.assertIsNone(data["total"])
            self.assertEqual(data["count"], 4)


if __name__ == "__main__":
    unittest.main()
