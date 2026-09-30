import asyncio
import csv
import hashlib
import hmac
import io
import json
import logging
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(__import__("os").environ.get("DATABASE_PATH", BASE_DIR / "data.db"))
SEED_DIR = BASE_DIR / "seed"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
KNOWN_ROBOTS = {"arm-01", "arm-02", "arm-03", "mobile-01", "humanoid-01"}
QUALITY = {"good", "usable", "bad"}
TRANSITIONS = {"submitted": {"in_progress"}, "in_progress": {"delivered"}, "delivered": {"accepted", "rejected"}, "rejected": {"in_progress"}, "accepted": set()}

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("dataset-request-desk")
app = FastAPI(title="Dataset Request Desk API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def db():
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    salt, digest = encoded.split("$")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000).hex()
    return hmac.compare_digest(actual, digest)


def migrate(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    current = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    current_version = current[0] if current else 0
    for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(migration_file.name.split("_", 1)[0])
        if version <= current_version:
            continue
        connection.executescript(migration_file.read_text())
        connection.execute("DELETE FROM schema_version")
        connection.execute("INSERT INTO schema_version(version) VALUES(?)", (version,))
        current_version = version
    connection.commit()


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def session_expiry():
    return (datetime.now(timezone.utc) + timedelta(hours=12)).replace(microsecond=0).isoformat()


def parse_recorded_at(value: str):
    for pattern in (None, "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.fromisoformat(value) if pattern is None else datetime.strptime(value, pattern)
        except ValueError:
            continue
    raise ValueError("invalid recorded_at")


def csv_text(row, key: str) -> str:
    value = row.get(key)
    return value.strip() if isinstance(value, str) else ""


def seed_users(connection):
    seed_file = SEED_DIR / "users.json"
    if not seed_file.exists():
        return
    for user in json.loads(seed_file.read_text()):
        connection.execute("INSERT OR IGNORE INTO users(email,password_hash,role,name,organisation,created_at) VALUES(?,?,?,?,?,?)", (user["email"], hash_password(user["password"]), user["role"], user["name"], user.get("organisation"), now()))
    connection.commit()


connection = db()
migrate(connection)
seed_users(connection)
connection.close()


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    logger.info(json.dumps({"method": request.method, "path": request.url.path, "status": response.status_code, "duration_ms": round((time.perf_counter() - started) * 1000, 2), "user_id": getattr(request.state, "user_id", None)}))
    return response


class LoginPayload(BaseModel):
    email: str
    password: str


class RequestPayload(BaseModel):
    task_name: str = Field(min_length=2, max_length=120)
    episodes_requested: int = Field(gt=0, le=100000)
    deadline: str
    notes: str = Field(default="", max_length=2000)


class StatusPayload(BaseModel):
    notes: str = Field(default="", max_length=2000)


class UserPayload(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: str
    name: str = Field(min_length=2, max_length=120)
    organisation: str | None = None


def current_user(request: Request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Authentication required")
    connection = db()
    row = connection.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND u.active=1 AND (s.expires_at IS NULL OR s.expires_at > ?)", (token, now())).fetchone()
    connection.close()
    if not row:
        raise HTTPException(401, "Invalid session")
    request.state.user_id = row["id"]
    return dict(row)


def require_roles(*roles):
    def dependency(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Insufficient permissions")
        return user
    return dependency


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/events")
async def events(request: Request, token: str = Query(""), last_event_id: str = Header("", alias="Last-Event-ID")):
    connection = db()
    user = connection.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND u.active=1 AND (s.expires_at IS NULL OR s.expires_at > ?)", (token.strip(), now())).fetchone()
    if not user:
        connection.close()
        raise HTTPException(401, "Invalid session")
    if last_event_id.strip():
        try:
            cursor = int(last_event_id)
        except ValueError:
            connection.close()
            raise HTTPException(400, "Invalid Last-Event-ID")
    else:
        cursor = connection.execute("SELECT coalesce(max(id), 0) FROM status_history").fetchone()[0]
    user_id = user["id"]
    role = user["role"]
    connection.close()

    async def stream():
        nonlocal cursor
        while not await request.is_disconnected():
            connection = db()
            query = "SELECT h.id, h.request_id, h.to_status, h.changed_at, r.task_name, r.client_id FROM status_history h JOIN requests r ON r.id=h.request_id WHERE h.id>?"
            params = [cursor]
            if role == "client":
                query += " AND r.client_id=?"
                params.append(user_id)
            rows = connection.execute(query + " ORDER BY h.id", params).fetchall()
            connection.close()
            for row in rows:
                cursor = row["id"]
                yield f"id: {cursor}\nevent: request_update\ndata: {json.dumps({k: row[k] for k in ('request_id', 'to_status', 'changed_at', 'task_name')})}\n\n"
            yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/auth/login")
def login(payload: LoginPayload, request: Request):
    connection = db()
    user = connection.execute("SELECT * FROM users WHERE lower(email)=lower(?) AND active=1", (payload.email.strip(),)).fetchone()
    if not user or not verify_password(payload.password, user["password_hash"]):
        connection.close()
        raise HTTPException(401, "Invalid email or password")
    token = secrets.token_urlsafe(32)
    connection.execute("INSERT INTO sessions(token,user_id,created_at,expires_at) VALUES(?,?,?,?)", (token, user["id"], now(), session_expiry()))
    connection.commit(); connection.close()
    request.state.user_id = user["id"]
    return {"token": token, "user": {k: user[k] for k in ("id", "email", "role", "name", "organisation")}}


@app.post("/auth/logout")
def logout(request: Request, user=Depends(current_user)):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    connection = db()
    connection.execute("DELETE FROM sessions WHERE token=?", (token,))
    connection.commit()
    connection.close()
    return {"status": "signed_out"}


def request_view(row, connection):
    item = dict(row)
    item["assigned_count"] = connection.execute("SELECT count(*) FROM assignments WHERE request_id=?", (row["id"],)).fetchone()[0]
    return item


@app.get("/me")
def me(user=Depends(current_user)):
    return {k: user[k] for k in ("id", "email", "role", "name", "organisation")}


@app.get("/users")
def list_users(user=Depends(require_roles("admin"))):
    connection = db()
    rows = connection.execute("SELECT id,email,role,name,organisation,active,created_at FROM users ORDER BY name").fetchall()
    connection.close()
    return [dict(row) for row in rows]


@app.post("/users", status_code=201)
def create_user(payload: UserPayload, user=Depends(require_roles("admin"))):
    if payload.role not in {"client", "operator", "admin"}:
        raise HTTPException(422, "Invalid role")
    connection = db()
    try:
        cursor = connection.execute("INSERT INTO users(email,password_hash,role,name,organisation,created_at) VALUES(?,?,?,?,?,?)", (payload.email.strip().lower(), hash_password(payload.password), payload.role, payload.name.strip(), payload.organisation, now()))
        connection.commit()
    except sqlite3.IntegrityError:
        connection.close()
        raise HTTPException(409, "Email already exists")
    row = connection.execute("SELECT id,email,role,name,organisation,active,created_at FROM users WHERE id=?", (cursor.lastrowid,)).fetchone()
    connection.close()
    return dict(row)


@app.patch("/users/{user_id}")
def update_user(user_id: int, role: str | None = None, active: bool | None = None, user=Depends(require_roles("admin"))):
    if role is not None and role not in {"client", "operator", "admin"}:
        raise HTTPException(422, "Invalid role")
    if user_id == user["id"] and active is False:
        raise HTTPException(409, "You cannot deactivate your own account")
    connection = db()
    target = connection.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
    if not target:
        connection.close(); raise HTTPException(404, "User not found")
    updates = []; values = []
    if role is not None: updates.append("role=?"); values.append(role)
    if active is not None: updates.append("active=?"); values.append(int(active))
    if updates:
        values.append(user_id); connection.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=?", values); connection.commit()
    row = connection.execute("SELECT id,email,role,name,organisation,active,created_at FROM users WHERE id=?", (user_id,)).fetchone()
    connection.close()
    return dict(row)


@app.get("/requests")
def list_requests(limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), user=Depends(current_user)):
    connection = db()
    if user["role"] == "client":
        count = connection.execute("SELECT count(*) FROM requests WHERE client_id=?", (user["id"],)).fetchone()[0]
        rows = connection.execute("SELECT r.*, u.name client_name FROM requests r JOIN users u ON u.id=r.client_id WHERE r.client_id=? ORDER BY r.created_at DESC LIMIT ? OFFSET ?", (user["id"], limit, offset)).fetchall()
    else:
        count = connection.execute("SELECT count(*) FROM requests").fetchone()[0]
        rows = connection.execute("SELECT r.*, u.name client_name FROM requests r JOIN users u ON u.id=r.client_id ORDER BY r.created_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    result = [request_view(row, connection) for row in rows]
    connection.close()
    return {"items": result, "total": count, "limit": limit, "offset": offset}


@app.post("/requests", status_code=201)
def create_request(payload: RequestPayload, user=Depends(require_roles("client"))):
    connection = db()
    cursor = connection.execute("INSERT INTO requests(client_id,task_name,episodes_requested,deadline,notes,created_at) VALUES(?,?,?,?,?,?)", (user["id"], payload.task_name.strip(), payload.episodes_requested, payload.deadline, payload.notes.strip(), now()))
    connection.execute("INSERT INTO status_history(request_id,to_status,changed_by,changed_at) VALUES(?,?,?,?)", (cursor.lastrowid, "submitted", user["id"], now()))
    connection.commit()
    row = connection.execute("SELECT r.*, u.name client_name FROM requests r JOIN users u ON u.id=r.client_id WHERE r.id=?", (cursor.lastrowid,)).fetchone()
    result = request_view(row, connection)
    connection.close()
    return result


@app.post("/requests/{request_id}/status")
def change_status(request_id: int, status: str = Query(...), payload: StatusPayload | None = None, user=Depends(current_user)):
    payload = payload or StatusPayload()
    connection = db()
    row = connection.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
    if not row:
        connection.close(); raise HTTPException(404, "Request not found")
    if user["role"] == "client" and row["client_id"] != user["id"]:
        connection.close(); raise HTTPException(403, "This request belongs to another client")
    allowed_roles = {"accepted": {"client"}, "rejected": {"client"}, "in_progress": {"operator", "admin"}, "delivered": {"operator", "admin"}}
    if user["role"] not in allowed_roles.get(status, set()):
        connection.close(); raise HTTPException(403, "Your role cannot perform this transition")
    if status not in TRANSITIONS.get(row["status"], set()):
        connection.close(); raise HTTPException(409, f"Invalid transition from {row['status']} to {status}")
    if status == "delivered":
        assigned = connection.execute("SELECT count(*) FROM assignments WHERE request_id=?", (request_id,)).fetchone()[0]
        if assigned < row["episodes_requested"]:
            connection.close(); raise HTTPException(409, "Not enough episodes assigned to deliver this request")
    rejection_notes = payload.notes.strip() if status == "rejected" else row["rejection_notes"]
    connection.execute("UPDATE requests SET status=?, delivered_at=?, rejection_notes=? WHERE id=?", (status, now() if status == "delivered" else row["delivered_at"], rejection_notes, request_id))
    connection.execute("INSERT INTO status_history(request_id,from_status,to_status,changed_by,changed_at) VALUES(?,?,?,?,?)", (request_id, row["status"], status, user["id"], now()))
    connection.commit(); connection.close()
    return {"status": status}


@app.get("/episodes")
def list_episodes(task_name: str = "", quality: str = "", limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), user=Depends(require_roles("operator", "admin"))):
    connection = db(); query = "SELECT e.*, a.request_id FROM episodes e LEFT JOIN assignments a ON a.episode_id=e.id WHERE 1=1"; params = []
    if task_name:
        query += " AND lower(e.task_name) LIKE ?"; params.append(f"%{task_name.lower()}%")
    if quality in QUALITY:
        query += " AND e.quality=?"; params.append(quality)
    count = connection.execute(query.replace("SELECT e.*, a.request_id", "SELECT count(*)", 1), params).fetchone()[0]
    rows = connection.execute(query + " ORDER BY e.recorded_at DESC LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall(); connection.close()
    return {"items": [dict(row) for row in rows], "total": count, "limit": limit, "offset": offset}


@app.post("/requests/{request_id}/assign/{episode_id}", status_code=201)
def assign_episode(request_id: int, episode_id: int, user=Depends(require_roles("operator", "admin"))):
    connection = db(); request_row = connection.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone(); episode = connection.execute("SELECT * FROM episodes WHERE id=?", (episode_id,)).fetchone(); existing = connection.execute("SELECT request_id FROM assignments WHERE episode_id=?", (episode_id,)).fetchone()
    if not request_row or not episode:
        connection.close(); raise HTTPException(404, "Request or episode not found")
    if episode["quality"] == "bad":
        connection.close(); raise HTTPException(409, "Bad episodes cannot be assigned")
    if existing:
        connection.close(); raise HTTPException(409, "Episode is already assigned")
    connection.execute("INSERT INTO assignments(request_id,episode_id,assigned_at) VALUES(?,?,?)", (request_id, episode_id, now())); connection.commit(); connection.close()
    return {"request_id": request_id, "episode_id": episode_id}


@app.post("/episodes/import")
async def import_episodes(file: UploadFile = File(...), user=Depends(require_roles("operator", "admin"))):
    reader = csv.DictReader(io.StringIO((await file.read()).decode("utf-8-sig"))); connection = db(); imported = 0; skipped = []
    for line_number, row in enumerate(reader, start=2):
        try:
            episode_id = csv_text(row, "episode_id"); robot_id = csv_text(row, "robot_id").lower(); task_name = csv_text(row, "task_name"); recorded_at = csv_text(row, "recorded_at"); duration = int(csv_text(row, "duration_seconds")); operator_name = csv_text(row, "operator_name"); quality = csv_text(row, "quality").lower()
            parse_recorded_at(recorded_at)
            if not episode_id or robot_id not in KNOWN_ROBOTS or not task_name or duration <= 0 or not operator_name or quality not in QUALITY:
                raise ValueError("missing or invalid field")
            if connection.execute("SELECT 1 FROM episodes WHERE episode_id=?", (episode_id,)).fetchone():
                skipped.append({"line": line_number, "episode_id": episode_id, "reason": "duplicate"}); continue
            connection.execute("INSERT INTO episodes(episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality) VALUES(?,?,?,?,?,?,?)", (episode_id, robot_id, task_name, recorded_at, duration, operator_name, quality)); imported += 1
        except (ValueError, TypeError, OverflowError) as error:
            skipped.append({"line": line_number, "episode_id": csv_text(row, "episode_id"), "reason": str(error)})
    connection.commit(); connection.close(); return {"imported": imported, "skipped": len(skipped), "skipped_rows": skipped}


@app.get("/analytics")
def analytics(start: str = Query(...), end: str = Query(...), user=Depends(require_roles("operator", "admin"))):
    connection = db()
    per_day = connection.execute("SELECT substr(recorded_at,1,10) day, robot_id, count(*) count FROM episodes WHERE recorded_at >= ? AND recorded_at < ? GROUP BY day, robot_id ORDER BY day, robot_id", (start, end)).fetchall()
    status_counts = connection.execute("SELECT status, count(*) count FROM requests GROUP BY status").fetchall()
    median_row = connection.execute("""
        WITH durations AS (
            SELECT julianday(delivered_at)-julianday(created_at) days
            FROM requests
            WHERE delivered_at IS NOT NULL AND created_at >= ? AND created_at < ?
        ), ranked AS (
            SELECT days, row_number() OVER (ORDER BY days) position, count(*) OVER () total
            FROM durations
        )
        SELECT avg(days) median_days FROM ranked
        WHERE position IN ((total + 1) / 2, (total + 2) / 2)
    """, (start, end)).fetchone()
    top_tasks = connection.execute("SELECT task_name, count(*) count FROM episodes WHERE quality='good' AND recorded_at >= ? AND recorded_at < ? GROUP BY task_name ORDER BY count DESC LIMIT 5", (start, end)).fetchall(); connection.close()
    return {"episodes_per_day_robot": [dict(row) for row in per_day], "requests_by_status": [dict(row) for row in status_counts], "median_submitted_to_delivered_days": median_row["median_days"], "top_good_tasks": [dict(row) for row in top_tasks]}
