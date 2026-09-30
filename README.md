# Fieldnote Dataset Request Desk

A small full-stack platform for turning robotics recording episodes into client datasets. The backend is Python/FastAPI with SQLite and the frontend is React/Vite.

## Run everything

Requirements: Docker and Docker Compose.

```bash
docker compose up --build
```

Then open http://localhost:5173. The API is at http://localhost:8000 and health is available at `/health`.

The first API start applies the numbered SQL migrations in `backend/migrations/` and seeds the accounts in `seed/users.json`. SQLite keeps the exercise self-contained; production would use PostgreSQL and separate session storage.

## Test

```bash
python3 -m pip install -r backend/requirements.txt
python3 -m pytest backend/tests -q
```

## Seed accounts

- `admin@example.com` / `admin123`
- `ops1@example.com` / `ops123`
- `ops2@example.com` / `ops123`
- `client-a@example.com` / `client123`
- `client-b@example.com` / `client123`

Clients only see their own requests and can accept/reject delivered requests. Operators see all requests, move operator-owned workflow states, assign episodes, and import CSV files. Admins can do all operator work plus create users, change roles, and activate/deactivate accounts from the administration view. Sessions expire after 12 hours and can be explicitly signed out.

## Import

The operator view accepts `seed/episodes.csv`. Import normalizes casing/whitespace, accepts the ISO and day-first date formats present in the export, rejects unknown robots, malformed rows, missing fields, invalid quality, and non-positive duration. `episode_id` is unique, so rerunning the same file is safe and returns imported/skipped counts with per-row reasons.

The analytics endpoint is `GET /analytics?start=2026-01-01&end=2027-01-01`. Its aggregations, grouping, database-side median, and top-five query are performed in SQLite, and the operator workspace displays a summary. Requests and episodes use bounded `limit`/`offset` pagination. At 5 million episodes, PostgreSQL plus indexes on `recorded_at`, `robot_id`, `quality`, and `task_name` would be the production choice; the next scale step would be cursor pagination and pre-aggregated daily rollups.

See [NOTES.md](NOTES.md) for design, security, scale, and omitted work.

## Deploy to Render

The selected stretch item is **Deployment**. The repository includes [render.yaml](render.yaml), which defines separate Docker web services for the API and React frontend. The API uses a 1 GB persistent disk mounted at `/data` so the SQLite database survives service restarts. This requires a Render plan that supports persistent disks.

1. Push the repository to GitHub or GitLab.
2. In Render, choose **New > Blueprint** and connect the repository.
3. Confirm the services from `render.yaml` and deploy.
4. After Render creates the API service, update the frontend `VITE_API_URL` environment variable to the actual API URL if the service name differs from `fieldnote-api`.

The seeded demo passwords are repository data for this exercise. For a real deployment, replace them, configure secrets in the Render dashboard rather than committing them, and move the database to managed PostgreSQL before scaling beyond a single persistent-disk instance. Render supplies HTTPS for both web services.
