"""Exercise the running app with the assignment credentials; never print tokens."""
import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--record-only", action="store_true", help="Print original behavior without asserting fixes")
    args = parser.parse_args()

    def request(path, token=None, body=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = Request(args.base_url + path, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(req, timeout=30) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    tokens = {}
    for name, email, password in [
        ("Sunset", "sunset@propertyflow.com", "client_a_2024"),
        ("Ocean", "ocean@propertyflow.com", "client_b_2024"),
    ]:
        status, data = request("/api/v1/auth/login", body={"email": email, "password": password})
        if status != 200:
            raise SystemExit(f"{name} login failed: HTTP {status}")
        tokens[name] = data["access_token"]
        print(f"{name}: login successful ({data['user']['tenant_id']})")

    failures = []
    for name, month, expected, count in [
        ("Sunset", 3, "2250.00", 4), ("Ocean", 3, "0.00", 0),
        ("Sunset", 3, "2250.00", 4), ("Ocean", 3, "0.00", 0),
        ("Sunset", 2, "0.00", 0), ("Sunset", 3, "2250.00", 4),
    ]:
        status, data = request(f"/api/v1/dashboard/summary?property_id=prop-001&month={month}&year=2024", tokens[name])
        print(f"{name} | 2024-{month:02d} | HTTP {status} | total={data.get('total_revenue')!r} | bookings={data.get('reservations_count')}")
        if status != 200 or data.get("total_revenue") != expected or data.get("reservations_count") != count:
            failures.append(f"{name} month {month}: expected {expected} / {count} bookings")

    if args.record_only:
        print("Original behavior recorded; no assertions requested.")
        return

    for name, expected_ids in [("Sunset", ["prop-001", "prop-002", "prop-003"]),
                               ("Ocean", ["prop-001", "prop-004", "prop-005"])]:
        status, data = request("/api/v1/dashboard/properties", tokens[name])
        ids = [p["id"] for p in data] if status == 200 else []
        print(f"{name} property list: {ids}")
        if ids != expected_ids:
            failures.append(f"{name}: incorrect property list")

    for label, path, token, expected_status in [
        ("Other tenant's property", "/api/v1/dashboard/summary?property_id=prop-002", tokens["Ocean"], 404),
        ("No login", "/api/v1/dashboard/summary?property_id=prop-001", None, 401),
        ("Invalid month", "/api/v1/dashboard/summary?property_id=prop-001&month=13&year=2024", tokens["Sunset"], 422),
        ("Month without year", "/api/v1/dashboard/summary?property_id=prop-001&month=3", tokens["Sunset"], 422),
    ]:
        status, _ = request(path, token)
        print(f"{label}: HTTP {status} (expected {expected_status})")
        if status != expected_status:
            failures.append(label)

    status, _ = request("/api/v1/auth/login", body={"email": "sunset@propertyflow.com", "password": "wrong"})
    if status != 401:
        failures.append("Wrong password was not rejected with 401")
    if failures:
        raise SystemExit("FAILED:\n" + "\n".join(failures))
    print("PASS: both client accounts, repeat requests, month filtering, property isolation, and validation.")


if __name__ == "__main__":
    main()
