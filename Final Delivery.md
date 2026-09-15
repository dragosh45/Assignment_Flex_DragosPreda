# Final Delivery — Property Revenue Dashboard

## What this guide is for

Record a **6–8 minute Loom screen recording** of the existing app, the relevant code, and the checks below. The assignment asks you to explain the debugging and demonstrate the result. Running the app locally is enough; deployment is not requested.

Read this once and rehearse the steps before recording. Use the suggested words as a guide, and explain them in your own words. Describe results you have actually run and observed.

## Verified results

The original backend and the fixed backend were run separately with the supplied client credentials. The sample database was left intact.

| Check | Original backend | Fixed backend |
| --- | --- | --- |
| Sunset, prop-001, March 2024 | 1000.0 / 3 bookings | 2250.00 / 4 bookings |
| Ocean, prop-001, March 2024 | 1000.0 / 3 bookings | 0.00 / 0 bookings |
| Sunset, prop-001, February 2024 | 1000.0 / 3 bookings | 0.00 / 0 bookings |
| Ocean requests Sunset-only prop-002 | No ownership validation | HTTP 404 |
| Cache isolation regression on original code | Fails: tenant-a returned to tenant-b | Passes |
| Automated tests, including real PostgreSQL | — | 23 passed, none skipped |

Recorded evidence: [original API](docs/evidence/api-before.txt), [fixed API](docs/evidence/api-after.txt), [original cache failure](docs/evidence/cache-before.txt), and [test results](docs/evidence/tests.txt).

The rounding cases use controlled regression fixtures. They are not claimed to be visible in every seeded dashboard total.

## Preparation

1. Open this repository in your editor.
2. Start the existing stack: `docker compose up --build -d`.
3. Open `http://localhost:3000` and `http://localhost:8000/docs`.
4. Open a second browser profile or private window for the second client.
5. Keep the following files ready in editor tabs:
   - `backend/app/services/cache.py`
   - `backend/app/core/database_pool.py`
   - `backend/app/services/reservations.py`
   - `backend/app/api/v1/dashboard.py`
   - `frontend/src/components/RevenueSummary.tsx`
   - `database/seed.sql`
6. Run the verification commands below before recording. Do not spend recording time installing dependencies or waiting for builds.

### Client logins

| Client | Email | Password |
| --- | --- | --- |
| Sunset Properties | sunset@propertyflow.com | client_a_2024 |
| Ocean Rentals | ocean@propertyflow.com | client_b_2024 |

### Showing the original code without reverting

The original commit is `d1835ec`. The local tag `assignment-baseline` points to it.

Use your editor's Git comparison view, or these terminal commands:

```bash
git diff d1835ec HEAD -- backend/app/services/cache.py
git diff d1835ec HEAD -- backend/app/core/database_pool.py
git diff d1835ec HEAD -- backend/app/services/reservations.py
git diff d1835ec HEAD -- backend/app/api/v1/dashboard.py frontend/src/components/RevenueSummary.tsx
```

The left/deleted side is the original code; the right/added side is the fix. **Keep the fixed app running while you show the comparison.** You do not need to reset branches or remove your fixes.

## Recording plan and suggested words

### 0:00–0:30 — Introduction

**Show:** the dashboard and the assignment title.

**Say:**

> “This is the property revenue dashboard debugging assignment. The reported problems were incorrect March revenue, one client seeing another client's figures, and small rounding differences. I'll show the relevant code paths, explain what went wrong, and demonstrate the fixes using both supplied client accounts.”

### 0:30–2:10 — Bug 1: revenue cache shared between clients

**Show:** `database/seed.sql`. Both clients have a property called `prop-001`, but these are different properties. Sunset's is Beach House Alpha; Ocean's is Mountain Lodge Beta.

**Say:**

> “I traced the dashboard request into the revenue cache. The important detail is that a property ID is only unique within its client. The sample data deliberately gives both clients the same property ID.”

**Show:** the original `cache.py` line:

```python
cache_key = f"revenue:{property_id}"
```

**Say:**

> “The cache key only contained the property ID. If Sunset requested this property first, its answer was saved under the same key Ocean would use. A cache hit returned that answer immediately, so even a tenant-filtered database query couldn't protect the response. The query was never reached.”

**Show:** the fixed key, which includes the client, property, year, and month and starts with `revenue:v2:`.

**Say:**

> “The fix gives each client and reporting period a separate cache entry. The new prefix also avoids reusing old entries created by the buggy code. The client identity comes from authentication, and the database query checks both the client and the property.”

**Demonstrate:** select March 2024 and `prop-001` in each browser window. Refresh Sunset, then Ocean, then Sunset again. Sunset should show **USD 2,250.00 and 4 bookings**. Ocean should show **0.00 and 0 bookings** for Mountain Lodge Beta because its seeded property has no reservations.

**Additional fix to mention briefly:** the original property dropdown listed every client's properties. It now loads the signed-in client's property list from the backend. Ocean should see Mountain Lodge Beta, Lakeside Cottage, and Urban Loft Modern.

### 2:10–4:20 — Bug 2: March totals were not calculated correctly

**Show:** the original `database_pool.py` and the exception handler in `reservations.py`.

**Say:**

> “There was also a problem underneath the calculations. The connection code read old Supabase database settings, although Docker supplied DATABASE_URL. It used a synchronous connection-pool class with an async engine, and returned a coroutine where the caller expected a session context manager. The exception handler then returned hard-coded revenue figures. That made a database failure look like a successful financial report.”

**Show:** the fixed database URL, shared async pool, and the removed mock-results block.

**Say:**

> “The connection now uses the configured PostgreSQL database and a reusable async pool. A failed query produces an error response instead of made-up revenue.”

**Show:** the original monthly helper. It created dates without a time zone and returned a placeholder zero. The dashboard route did not accept a reporting period and called the all-time calculation.

**Say:**

> “The monthly helper wasn't actually executing a query, and the dashboard had no month filter. I connected the reporting period to the real calculation. The boundary dates must use the property's local time zone.”

**Show:** the `res-tz-1` row in `database/seed.sql` and the `period_bounds` function.

**Say:**

> “This booking checks in at February 29, 23:30 UTC. In Paris, that is March 1 at 00:30. It therefore belongs in March. I construct the start of March and the start of April in the property's time zone, convert both to UTC, and query from the first boundary inclusive to the second boundary exclusive. That also accounts for daylight saving time.”

**Demonstrate:** in Sunset's Beach House Alpha, March 2024 should show **USD 2,250.00 / 4 bookings**. February 2024 should show **0.00 / 0 bookings**. Switch back to March.

**Explain the arithmetic:**

```text
1,250.000 + 333.333 + 333.333 + 333.334 = 2,250.000
Report total after final rounding: USD 2,250.00
```

Be precise: the original live endpoint's hard-coded result and its unfinished monthly helper are separate problems. Do not claim that the original endpoint executed the commented-out monthly SQL.

### 4:20–5:40 — Bug 3: money passed through binary floating point

**Show:** the original endpoint's `float(...)` conversion and the original component's `Math.round(total * 100) / 100`.

**Say:**

> “PostgreSQL stores these amounts as exact numeric values, including fractional cents. The API converted the result to a binary floating-point number, and the frontend did the financial rounding. Binary floating point cannot represent every decimal amount exactly, which can change the result around a half-cent boundary.”

**Show:** this expression in the browser console:

```javascript
Math.round(1.005 * 100) / 100
```

It evaluates to **1**, rather than the **1.01** expected under half-up rounding.

**Show:** `format_amount` in `reservations.py`, the API's string amount, and the component's string formatting.

**Say:**

> “The fix keeps numeric and Decimal values through aggregation, rounds the final total once with an explicit half-up rule, and sends the amount as a decimal string. The frontend adds display separators without recalculating the money.”

**Show:** the precision regression tests, including `1.005 → 1.01`, `2.675 → 2.68`, and `333.333 + 333.333 + 333.334 → 1000.00`.

**Say:**

> “The sample fractional amounts must be added before rounding. Rounding each reservation separately would lose a cent in this example. I also keep different currencies in separate totals because the assignment doesn't supply exchange rates.”

Do not claim that every floating-point number produces a wrong result. The seeded sum of 1000 is exactly representable; the boundary tests demonstrate the separate rounding problem.

### 5:40–7:00 — Demonstrate the checks and close

**Show:** the verification script output and passing automated tests.

```bash
python3 scripts/verify_dashboard.py
```

This logs in with both supplied accounts, alternates requests for their shared property ID, checks February and March, checks each property list, and verifies unauthorized requests are rejected. Tokens are not printed.

Run the tests against the supplied PostgreSQL database:

```bash
docker compose exec -e TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/propertyflow backend python -m unittest discover -s tests -v
```

The database tests insert boundary and currency fixtures inside transactions and roll them back. They do not change the sample reservations used in your browser demonstration.

**Say:**

> “These checks cover both clients, repeated requests that exercise caching, the month boundary and daylight-saving changes, and fractional-cent rounding. They also check that a request for another client's property is rejected and that a database outage cannot turn into a fake revenue response. The application still uses its original frontend, backend, database, and cache. These changes repair the existing reporting path.”

## Quick answers to likely follow-up questions

**What is a tenant?** A client company. Here, Sunset is `tenant-a` and Ocean is `tenant-b`.

**Why wasn't filtering SQL by tenant enough?** A cache hit returned before SQL ran, so the cache needed tenant isolation too.

**Why include month and year in the cache key?** Different reports for the same property must not reuse one another's results.

**Why convert both boundaries separately?** Daylight saving can change the UTC offset within a month. Paris's March 2024 starts at 23:00 UTC the previous day and ends at 22:00 UTC on March 31.

**Why use an exclusive end?** A booking exactly at the start of April belongs in April, with no overlap or missing instant between reports.

**Why is Ocean's shared-ID property zero?** The seed creates the property but contains no reservations for it. Zero is correct for that fixture.

**Why strings for money in JSON?** JavaScript parses JSON numbers as binary floating point. A decimal string preserves the already-rounded financial amount exactly.

**What rounding policy did you choose?** Aggregate the stored precision first, then round the report to two decimal places using half-up. This is an explicit reporting assumption for the supplied amounts; no currency conversion is invented.

## Submission checklist

- [ ] Review the final diff and understand the explanations above.
- [ ] Run the app and verify both supplied client logins.
- [ ] Run the verification script and automated tests.
- [ ] Commit and push the solution to your own GitHub fork before the email deadline.
- [ ] Record the Loom walkthrough and check its viewing permissions.
- [ ] Submit the fork URL and Loom URL using the employer's requested channel.

The time limit starts when the email was sent, not when this repository was cloned. The actual email deadline and submission channel were not provided here.

## Additional fixes to know about

These are supporting corrections in the existing reporting and authentication code; keep the main video focused on the three reported problems.

- **Authentication:** unknown users previously defaulted to Sunset's tenant. The fallback accepted a static token or decoded token without verifying its signature; the legacy login path checked whether an account existed without checking its password. The corrected paths validate credentials and signed claims, reject a missing tenant, and respect token expiry when using the auth cache. The API tests cover wrong passwords, forged/expired/static tokens, missing tenants, and user-editable metadata trying to override the tenant.
- **Browser cache context:** the client cache ignored `app_metadata.tenant_id` and expected UUIDs, but the sample IDs are text such as `tenant-a`. It now reads the supplied tenant claims and accepts the database's text IDs for cache partitioning. The backend remains responsible for authorization.
- **Outdated requests:** the revenue component clears old data and ignores results after it unmounts or its selection changes. Switching users resets the dashboard's selections.
- **Display accuracy:** the fake hard-coded 12% trend indicator was removed. There is no data supporting that figure.
- **Frontend install:** the supplied lockfile needs legacy peer-dependency handling. The Docker build now installs the recorded versions with `npm ci --legacy-peer-deps --ignore-scripts`.

## Local development alternative

If the first Docker image downloads are slow, the same app can run directly while PostgreSQL and Redis stay in Docker:

```bash
docker compose up -d db redis
```

In a terminal at the repository root, after installing `backend/requirements.txt` into `.venv`:

```bash
cd backend
DEBUG=false DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/propertyflow REDIS_URL=redis://127.0.0.1:6380/0 ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
npm ci --legacy-peer-deps --ignore-scripts
npm run dev -- --host 127.0.0.1 --port 3000
```

Use one startup method at a time so two processes do not compete for the same ports.

For local tests from `backend/`:

```bash
DEBUG=false TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/propertyflow ../.venv/bin/python -m unittest discover -s tests -v
```
