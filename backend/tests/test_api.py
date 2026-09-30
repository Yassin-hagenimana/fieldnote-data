import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[2]
os.environ["DATABASE_PATH"] = str(ROOT / "test.db")
sys.path.insert(0, str(ROOT / "backend"))
from app import app, db, hash_password, migrate, now  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    path = ROOT / "test.db"
    if path.exists():
        path.unlink()
    connection = db()
    migrate(connection)
    for email, password, role in (("client@example.com", "client123", "client"), ("ops@example.com", "ops123", "operator")):
        connection.execute("INSERT INTO users(email,password_hash,role,name,created_at) VALUES(?,?,?,?,?)", (email, hash_password(password), role, role.title(), now()))
    connection.commit()
    connection.close()
    yield
    if path.exists():
        path.unlink()


def login(email, password):
    response = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {response.json()['token']}"}


def make_request(headers, count=1):
    return client.post("/requests", headers=headers, json={"task_name": "pick cup", "episodes_requested": count, "deadline": "2026-10-01"})


def seed_episode(quality="good", episode_id="EP-1"):
    connection = db()
    connection.execute("INSERT INTO episodes(episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality) VALUES(?,?,?,?,?,?,?)", (episode_id, "arm-01", "pick cup", "2026-09-01T10:00:00", 30, "A", quality))
    connection.commit()
    connection.close()


def test_auth_and_role_boundaries():
    assert client.get("/requests").status_code == 401
    client_headers = login("client@example.com", "client123")
    assert make_request(client_headers).status_code == 201
    assert client.post("/requests/1/status?status=in_progress", headers=client_headers).status_code == 403


def test_status_and_assignment_rules():
    ops_headers = login("ops@example.com", "ops123")
    client_headers = login("client@example.com", "client123")
    make_request(client_headers)
    assert client.post("/requests/1/status?status=in_progress", headers=ops_headers).status_code == 200
    assert client.post("/requests/1/status?status=delivered", headers=ops_headers).status_code == 409
    seed_episode("bad")
    assert client.post("/requests/1/assign/1", headers=ops_headers).status_code == 409


def test_import_is_idempotent_and_reports_duplicates():
    headers = login("ops@example.com", "ops123")
    content = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\nEP-X,arm-01,pick cup,2026-09-01T10:00:00,30,A,good\nEP-X,arm-01,pick cup,2026-09-01T10:00:00,30,A,good\nEP-BAD,unknown,pick cup,2026-09-01T10:00:00,30,A,good\n"
    first = client.post("/episodes/import", headers=headers, files={"file": ("episodes.csv", content, "text/csv")}).json()
    second = client.post("/episodes/import", headers=headers, files={"file": ("episodes.csv", content, "text/csv")}).json()
    assert first["imported"] == 1 and first["skipped"] == 2
    assert second["imported"] == 0 and second["skipped"] == 3


def test_import_skips_rows_with_missing_columns_instead_of_crashing():
    headers = login("ops@example.com", "ops123")
    content = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\nEP-MISSING,arm-01,pick cup,2026-09-01T10:00:00,30,A\n"
    response = client.post("/episodes/import", headers=headers, files={"file": ("episodes.csv", content, "text/csv")})
    assert response.status_code == 200
    assert response.json()["imported"] == 0
    assert response.json()["skipped_rows"][0]["episode_id"] == "EP-MISSING"