import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import dashboard, login
from app.config import settings
from app.core.auth import clear_auth_cache


class DashboardAPITests(unittest.TestCase):
    def setUp(self):
        clear_auth_cache()
        app = FastAPI()
        app.include_router(login.router, prefix="/api/v1")
        app.include_router(dashboard.router, prefix="/api/v1")
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.url = "/api/v1/dashboard/summary?property_id=prop-001"

    def sign_in(self, email="sunset@propertyflow.com", password="client_a_2024"):
        response = self.client.post("/api/v1/auth/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200)
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    def token_headers(self, **claims):
        payload = {"id": "test-user", "email": "test@example.com", "aud": "authenticated",
                   "exp": datetime.now(timezone.utc) + timedelta(hours=1), **claims}
        return {"Authorization": "Bearer " + jwt.encode(payload, settings.secret_key, algorithm="HS256")}

    def summary(self):
        return {"property_id": "prop-001", "total": "2250.00", "currency": "USD",
                "totals_by_currency": {"USD": "2250.00"}, "count": 4,
                "month": 3, "year": 2024, "timezone": "Europe/Paris"}

    def test_both_provided_logins_supply_their_own_tenant(self):
        for email, password, tenant in [("sunset@propertyflow.com", "client_a_2024", "tenant-a"),
                                         ("ocean@propertyflow.com", "client_b_2024", "tenant-b")]:
            headers = self.sign_in(email, password)
            # Client-supplied tenant headers must not override authenticated identity.
            headers["X-Simulated-Tenant"] = "tenant-other"
            with patch.object(dashboard, "get_revenue_summary", return_value=self.summary()) as get:
                response = self.client.get(self.url + "&month=3&year=2024", headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["total_revenue"], "2250.00")
                self.assertEqual(response.headers["cache-control"], "private, no-store")
                get.assert_awaited_once_with("prop-001", tenant, month=3, year=2024)

    def test_missing_auth_and_wrong_password_are_rejected(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        for email in ["sunset@propertyflow.com", "ocean@propertyflow.com", "candidate@propertyflow.com"]:
            response = self.client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
            self.assertEqual(response.status_code, 401)

    def test_missing_tenant_does_not_fall_back_to_sunset(self):
        headers = self.token_headers()
        with patch.object(dashboard, "get_revenue_summary") as get:
            self.assertEqual(self.client.get(self.url, headers=headers).status_code, 403)
            get.assert_not_awaited()

    def test_user_metadata_cannot_override_server_tenant(self):
        headers = self.token_headers(app_metadata={"tenant_id": "tenant-b"}, user_metadata={"tenant_id": "tenant-a"})
        with patch.object(dashboard, "get_revenue_summary", return_value=self.summary()) as get:
            self.assertEqual(self.client.get(self.url, headers=headers).status_code, 200)
            get.assert_awaited_once_with("prop-001", "tenant-b", month=None, year=None)

    def test_forged_expired_and_static_tokens_are_rejected(self):
        expired = self.token_headers(email="candidate@propertyflow.com", exp=datetime.now(timezone.utc) - timedelta(seconds=5))
        valid = self.token_headers(email="candidate@propertyflow.com")["Authorization"]
        forged = valid.rsplit(".", 1)[0] + ".invalid"
        for headers in [expired, {"Authorization": forged}, {"Authorization": "Bearer mock-token-123"}]:
            self.assertEqual(self.client.get(self.url, headers=headers).status_code, 401)

    def test_bad_period_is_rejected(self):
        headers = self.sign_in()
        for suffix in ["&month=0&year=2024", "&month=13&year=2024", "&month=3", "&year=0", "&year=9999"]:
            self.assertEqual(self.client.get(self.url + suffix, headers=headers).status_code, 422)

    def test_database_outage_is_503_instead_of_fake_revenue(self):
        headers = self.sign_in()
        with patch.object(dashboard, "get_revenue_summary", side_effect=SQLAlchemyError("unavailable")):
            response = self.client.get(self.url, headers=headers)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("total_revenue", response.json())


if __name__ == "__main__":
    unittest.main()
