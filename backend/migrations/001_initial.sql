CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('client','operator','admin')),
    name TEXT NOT NULL,
    organisation TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY,
    episode_id TEXT UNIQUE NOT NULL,
    robot_id TEXT NOT NULL,
    task_name TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    operator_name TEXT NOT NULL,
    quality TEXT NOT NULL CHECK(quality IN ('good','usable','bad'))
);

CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES users(id),
    task_name TEXT NOT NULL,
    episodes_requested INTEGER NOT NULL CHECK(episodes_requested > 0),
    deadline TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'submitted',
    created_at TEXT NOT NULL,
    delivered_at TEXT
);

CREATE TABLE IF NOT EXISTS assignments (
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    episode_id INTEGER NOT NULL UNIQUE REFERENCES episodes(id),
    assigned_at TEXT NOT NULL,
    PRIMARY KEY(request_id, episode_id)
);

CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status TEXT NOT NULL,
    changed_by INTEGER NOT NULL REFERENCES users(id),
    changed_at TEXT NOT NULL
);
