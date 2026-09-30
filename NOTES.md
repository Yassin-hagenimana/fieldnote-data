# Engineering Notes

## Design

The model has users, sessions, requests, episodes, assignments, and status_history. Requests belong to a client. Assignments use a unique episode foreign key, which makes the one-request-at-a-time rule a database invariant as well as an API check. Status is stored on the request for fast reads; every transition is appended to status_history with the actor and timestamp.

The hardest choices were keeping the exercise runnable from a clean clone, making a messy import safe to repeat, and keeping authorization understandable. SQLite and numbered SQL migrations keep startup simple while allowing indexes and session expiry to evolve independently. `episode_id` uniqueness plus explicit skipped-row reporting makes imports idempotent. Role checks are dependencies on the API routes, with transition and ownership rules checked again inside each mutation.

## Deliberate simplifications

Password reset, audit-log browsing, and a full charting library are left out. The UI includes admin account management and an analytics summary, while list endpoints use bounded pagination and database indexes. Sessions are expiring bearer tokens stored in SQLite rather than short-lived JWTs with refresh tokens. With two more days I would add managed PostgreSQL, password reset, richer charts, and CI coverage.

## Something that went wrong

The seed export uses multiple timestamp formats. An initial ISO-only parser would have skipped valid rows such as `14/08/2026 09:15`. I caught this by reading the seed around its date-format variation, added explicit accepted formats, and kept invalid values as row-level skip reasons rather than silently coercing them.

## Security

Passwords are never stored as plain text: the seed step hashes them with PBKDF2-HMAC-SHA256 and a per-user random salt. All mutations require a session token and role checks run server-side. Pydantic validates request sizes/counts, SQL uses parameters, and import values are validated against known robots and enum values.

The two biggest risks are session theft and authorization regressions. This version has 12-hour session expiry, explicit logout, active-user checks, and server-side role enforcement. Production would use secure, HttpOnly, SameSite cookies, TLS, rate limiting, and centralized policy tests. A second concern is sensitive dataset metadata leaking through over-broad list endpoints, so client filtering is enforced at query level rather than only in the UI.

## Scale

At 10x users, SQLite write contention and database-backed sessions would be the first pressure points; PostgreSQL, connection pooling, and an external session/cache store would address them. At 100x episodes, import throughput and analytics aggregation would hurt first. Composite indexes and bounded pagination are in place; next steps would be bulk import batches, cursor pagination, and daily analytics rollups. The median and other analytics aggregations now execute in the database rather than loading raw duration rows into Python.


## 4.4 Choose ONE stretch item (optional)

**Real-time** was selected: operators see request status changes and new requests appear live without refreshing, using server-sent events (SSE).
