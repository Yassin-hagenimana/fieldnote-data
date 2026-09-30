ALTER TABLE sessions ADD COLUMN expires_at TEXT;

CREATE INDEX IF NOT EXISTS idx_episodes_recorded_robot ON episodes(recorded_at, robot_id);
CREATE INDEX IF NOT EXISTS idx_episodes_quality_task ON episodes(quality, task_name);
CREATE INDEX IF NOT EXISTS idx_requests_client_created ON requests(client_id, created_at);
CREATE INDEX IF NOT EXISTS idx_requests_status_created ON requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_assignments_request ON assignments(request_id);
