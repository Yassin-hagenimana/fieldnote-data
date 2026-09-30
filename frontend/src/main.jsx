import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowRight,
  Check,
  CircleAlert,
  FileUp,
  Filter,
  LogOut,
  Plus,
  RefreshCw,
  Search,
  Upload,
  X,
} from "lucide-react";
import "./styles.css";

const API =
  import.meta.env.VITE_API_URL ||
  `${window.location.protocol}//${window.location.hostname}:8000`;
const demoAccounts = {
  client: ["client-a@example.com", "client123"],
  operator: ["ops1@example.com", "ops123"],
};

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  let response;
  try {
    response = await fetch(`${API}${path}`, { ...options, headers });
  } catch {
    throw new Error(`Cannot reach the API at ${API}. Check that Docker Compose is running.`);
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "Something went wrong");
  return body;
}

function Login({ onLogin }) {
  const [email, setEmail] = useState("client-a@example.com");
  const [password, setPassword] = useState("client123");
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      const result = await request("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      onLogin(result);
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <main className="login-shell">
      <div className="login-art">
        <div className="brand-mark">
          <Activity size={18} /> FIELDNOTE
        </div>
        <div>
          <p className="kicker">ROBOTICS OPERATIONS / 01</p>
          <h1>Requests in motion.</h1>
          <p>
            One quiet workspace for turning raw robot sessions into client-ready
            datasets.
          </p>
        </div>
        <div className="login-art-footer">
          <span>DATASET REQUEST DESK</span>
          <span>v1.0 / KIGALI</span>
        </div>
      </div>
      <form className="login-form" onSubmit={submit}>
        <div>
          <p className="kicker">Welcome back</p>
          <h2>Sign in to Fieldnote</h2>
          <p className="muted">
            Use a seeded account to explore the workspace.
          </p>
        </div>
        <label>
          Email
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
          />
        </label>
        <label>
          Password
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
          />
        </label>
        {error && (
          <div className="error">
            <CircleAlert size={16} />
            {error}
          </div>
        )}
        <button className="primary full" type="submit">
          Enter workspace <ArrowRight size={16} />
        </button>
        <div className="login-hints">
          <button
            type="button"
            onClick={() => {
              setEmail(demoAccounts.client[0]);
              setPassword(demoAccounts.client[1]);
            }}
          >
            Client demo
          </button>
          <button
            type="button"
            onClick={() => {
              setEmail(demoAccounts.operator[0]);
              setPassword(demoAccounts.operator[1]);
            }}
          >
            Operator demo
          </button>
        </div>
      </form>
    </main>
  );
}

function StatusPill({ status }) {
  return (
    <span className={`status status-${status}`}>
      {status.replace("_", " ")}
    </span>
  );
}
function Empty({ children }) {
  return (
    <div className="empty">
      <Activity size={22} />
      <p>{children}</p>
    </div>
  );
}

function ClientView({ session, reload }) {
  const [requests, setRequests] = useState([]);
  const [liveVersion, setLiveVersion] = useState(0);
  const [rejectingRequest, setRejectingRequest] = useState(null);
  const [rejectionNotes, setRejectionNotes] = useState("");
  const [form, setForm] = useState({
    task_name: "",
    episodes_requested: 10,
    deadline: "",
    notes: "",
  });
  const [error, setError] = useState("");
  async function load() {
    const result = await request("/requests", {
      headers: { Authorization: `Bearer ${session.token}` },
    });
    setRequests(result.items || result);
  }
  useEffect(() => {
    load();
  }, [liveVersion]);
  useEffect(() => {
    const source = new EventSource(
      `${API}/events?token=${encodeURIComponent(session.token)}`,
    );
    source.addEventListener("request_update", () =>
      setLiveVersion((version) => version + 1),
    );
    return () => source.close();
  }, [session.token]);
  async function create(event) {
    event.preventDefault();
    setError("");
    try {
      await request("/requests", {
        method: "POST",
        headers: { Authorization: `Bearer ${session.token}` },
        body: JSON.stringify(form),
      });
      setForm({
        task_name: "",
        episodes_requested: 10,
        deadline: "",
        notes: "",
      });
      load();
    } catch (e) {
      setError(e.message);
    }
  }
  async function decision(id, status, notes = "") {
    try {
      await request(`/requests/${id}/status?status=${status}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${session.token}` },
        body: status === "rejected" ? JSON.stringify({ notes }) : undefined,
      });
      setRejectingRequest(null);
      setRejectionNotes("");
      load();
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <div className="page-grid">
      <section>
        <div className="section-heading">
          <div>
            <p className="kicker">Client workspace</p>
            <h2>My requests</h2>
          </div>
          <button
            className="icon-button"
            onClick={load}
            title="Refresh requests"
          >
            <RefreshCw size={17} />
          </button>
        </div>
        <div className="request-list">
          {requests.length ? (
            requests.map((item) => (
              <article className="request-row" key={item.id}>
                <div className="request-main">
                  <span className="request-id">
                    REQ-{String(item.id).padStart(4, "0")}
                  </span>
                  <h3>{item.task_name}</h3>
                  <p>
                    {item.assigned_count} / {item.episodes_requested} episodes
                    assigned <span className="dot">·</span> due {item.deadline}
                  </p>
                </div>
                <div className="request-side">
                  <StatusPill status={item.status} />
                  {item.status === "delivered" && (
                    <div className="row-actions">
                      <button
                        className="approve"
                        onClick={() => decision(item.id, "accepted")}
                      >
                        <Check size={14} /> Accept
                      </button>
                      <button
                        className="reject"
                        onClick={() => {
                          setRejectingRequest(item);
                          setRejectionNotes("");
                        }}
                      >
                        <X size={14} /> Reject
                      </button>
                    </div>
                  )}
                </div>
              </article>
            ))
          ) : (
            <Empty>No requests yet. Start with a new dataset brief.</Empty>
          )}
        </div>
      </section>
      <section className="form-panel">
        <p className="kicker">New request</p>
        <h2>Describe the dataset</h2>
        <form onSubmit={create}>
          <label>
            Task name
            <input
              required
              value={form.task_name}
              onChange={(e) => setForm({ ...form, task_name: e.target.value })}
              placeholder="e.g. pick cups from a tray"
            />
          </label>
          <div className="form-split">
            <label>
              Episodes
              <input
                required
                min="1"
                type="number"
                value={form.episodes_requested}
                onChange={(e) =>
                  setForm({
                    ...form,
                    episodes_requested: Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Deadline
              <input
                required
                type="date"
                value={form.deadline}
                onChange={(e) => setForm({ ...form, deadline: e.target.value })}
              />
            </label>
          </div>
          <label>
            Notes
            <textarea
              rows="4"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="Quality bar, scene details, or delivery context"
            />
          </label>
          {error && (
            <div className="error">
              <CircleAlert size={16} />
              {error}
            </div>
          )}
          <button className="primary full" type="submit">
            <Plus size={16} /> Create request
          </button>
        </form>
      </section>
      {rejectingRequest && (
        <div className="modal-backdrop" role="presentation">
          <form
            className="modal"
            onSubmit={(event) => {
              event.preventDefault();
              decision(rejectingRequest.id, "rejected", rejectionNotes);
            }}
          >
            <div className="modal-heading">
              <div>
                <p className="kicker">Reject request</p>
                <h2>{rejectingRequest.task_name}</h2>
              </div>
              <button
                className="icon-button"
                type="button"
                title="Close"
                onClick={() => setRejectingRequest(null)}
              >
                <X size={17} />
              </button>
            </div>
            <label>
              Comments or notes <span className="optional">Optional</span>
              <textarea
                autoFocus
                rows="5"
                maxLength="2000"
                value={rejectionNotes}
                onChange={(event) => setRejectionNotes(event.target.value)}
                placeholder="Tell the operator what needs to change"
              />
            </label>
            <div className="modal-actions">
              <button
                className="secondary"
                type="button"
                onClick={() => setRejectingRequest(null)}
              >
                Cancel
              </button>
              <button className="reject-action" type="submit">
                <X size={14} /> Reject request
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

function OperatorView({ session }) {
  const [requests, setRequests] = useState([]);
  const [liveVersion, setLiveVersion] = useState(0);
  const [episodes, setEpisodes] = useState([]);
  const [requestMeta, setRequestMeta] = useState({
    total: 0,
    limit: 10,
    offset: 0,
  });
  const [episodeMeta, setEpisodeMeta] = useState({
    total: 0,
    limit: 25,
    offset: 0,
  });
  const [requestPage, setRequestPage] = useState(0);
  const [episodePage, setEpisodePage] = useState(0);
  const [selected, setSelected] = useState("");
  const [filters, setFilters] = useState({ task_name: "", quality: "" });
  const [notice, setNotice] = useState("");
  const auth = { Authorization: `Bearer ${session.token}` };
  async function load() {
    const requestResult = await request(
      `/requests?limit=10&offset=${requestPage * 10}`,
      { headers: auth },
    );
    const episodeResult = await request(
      `/episodes?task_name=${encodeURIComponent(filters.task_name)}&quality=${filters.quality}&limit=25&offset=${episodePage * 25}`,
      { headers: auth },
    );
    setRequests(requestResult.items || requestResult);
    setEpisodes(episodeResult.items || episodeResult);
    setRequestMeta(
      requestResult.items
        ? requestResult
        : { total: requestResult.length, limit: 10, offset: 0 },
    );
    setEpisodeMeta(
      episodeResult.items
        ? episodeResult
        : { total: episodeResult.length, limit: 25, offset: 0 },
    );
  }
  useEffect(() => {
    load();
  }, [requestPage, episodePage, filters.task_name, filters.quality, liveVersion]);
  useEffect(() => {
    const source = new EventSource(
      `${API}/events?token=${encodeURIComponent(session.token)}`,
    );
    source.addEventListener("request_update", () =>
      setLiveVersion((version) => version + 1),
    );
    return () => source.close();
  }, [session.token]);
  async function status(id, value) {
    try {
      await request(`/requests/${id}/status?status=${value}`, {
        method: "POST",
        headers: auth,
      });
      setNotice(`Request moved to ${value}.`);
      load();
    } catch (e) {
      setNotice(e.message);
    }
  }
  async function assign(episodeId) {
    if (!selected) return setNotice("Select a request first.");
    try {
      await request(`/requests/${selected}/assign/${episodeId}`, {
        method: "POST",
        headers: auth,
      });
      setNotice("Episode assigned.");
      load();
    } catch (e) {
      setNotice(e.message);
    }
  }
  async function importFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    const result = await fetch(`${API}/episodes/import`, {
      method: "POST",
      headers: auth,
      body: (() => {
        const data = new FormData();
        data.append("file", file);
        return data;
      })(),
    }).then((r) => r.json());
    setNotice(`Imported ${result.imported}; skipped ${result.skipped}.`);
    load();
  }
  return (
    <div className="operator-layout">
      <section>
        <div className="section-heading">
          <div>
            <p className="kicker">Operations queue</p>
            <h2>All requests</h2>
          </div>
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">Assign to request...</option>
            {requests.map((item) => (
              <option value={item.id} key={item.id}>
                REQ-{String(item.id).padStart(4, "0")} · {item.task_name}
              </option>
            ))}
          </select>
        </div>
        <div className="request-list">
          {requests.length ? (
            requests.map((item) => (
              <article className="request-row" key={item.id}>
                <div className="request-main">
                  <span className="request-id">
                    REQ-{String(item.id).padStart(4, "0")} · {item.client_name}
                  </span>
                  <h3>{item.task_name}</h3>
                  <p>
                    {item.assigned_count} / {item.episodes_requested} episodes
                    assigned <span className="dot">·</span> due {item.deadline}
                  </p>
                </div>
                <div className="request-side">
                  <StatusPill status={item.status} />
                  {item.status === "submitted" && (
                    <button
                      className="text-button"
                      onClick={() => status(item.id, "in_progress")}
                    >
                      Start work <ArrowRight size={14} />
                    </button>
                  )}
                  {item.status === "in_progress" && (
                    <button
                      className="text-button"
                      onClick={() => status(item.id, "delivered")}
                    >
                      Deliver <ArrowRight size={14} />
                    </button>
                  )}
                  {item.status === "rejected" && (
                    <button
                      className="text-button"
                      onClick={() => status(item.id, "in_progress")}
                    >
                      Rework <ArrowRight size={14} />
                    </button>
                  )}
                </div>
              </article>
            ))
          ) : (
            <Empty>No requests in the queue.</Empty>
          )}
        </div>
      </section>
      <section className="episode-panel">
        <div className="section-heading">
          <div>
            <p className="kicker">Episode library</p>
            <h2>Assignable sessions</h2>
          </div>
          <label className="upload-button">
            <Upload size={15} /> Import CSV
            <input type="file" accept=".csv" onChange={importFile} />
          </label>
        </div>
        <div className="filters">
          <div className="search-input">
            <Search size={15} />
            <input
              placeholder="Filter task name"
              value={filters.task_name}
              onChange={(e) => {
                setFilters({ ...filters, task_name: e.target.value });
                setEpisodePage(0);
              }}
            />
          </div>
          <select
            value={filters.quality}
            onChange={(e) => {
              setFilters({ ...filters, quality: e.target.value });
              setEpisodePage(0);
            }}
          >
            <option value="">All quality</option>
            <option value="good">Good</option>
            <option value="usable">Usable</option>
            <option value="bad">Bad</option>
          </select>
        </div>
        {notice && (
          <div className="notice">
            <FileUp size={15} />
            {notice}
          </div>
        )}
        <div className="episode-list">
          {episodes.map((item) => (
            <div
              className={`episode-row ${item.request_id ? "is-assigned" : ""}`}
              key={item.id}
            >
              <div>
                <span className="request-id">
                  {item.episode_id} · {item.robot_id}
                </span>
                <strong>{item.task_name}</strong>
                <small>
                  {item.recorded_at.replace("T", " ")} · {item.duration_seconds}
                  s
                </small>
              </div>
              <div className="episode-action">
                <span className={`quality quality-${item.quality}`}>
                  {item.quality}
                </span>
                {item.request_id ? (
                  <span className="assigned-label">Assigned</span>
                ) : (
                  item.quality !== "bad" && (
                    <button
                      className="icon-button"
                      title="Assign episode"
                      onClick={() => assign(item.id)}
                    >
                      <Plus size={16} />
                    </button>
                  )
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="pager">
          <button className="text-button" disabled={episodePage === 0} onClick={() => setEpisodePage(episodePage - 1)}>Previous</button>
          <span>{episodeMeta.total ? episodeMeta.offset + 1 : 0}–{Math.min(episodeMeta.offset + episodeMeta.limit, episodeMeta.total)} of {episodeMeta.total}</span>
          <button className="text-button" disabled={episodeMeta.offset + episodeMeta.limit >= episodeMeta.total} onClick={() => setEpisodePage(episodePage + 1)}>Next</button>
        </div>
      </section>
    </div>
  );
}

function AnalyticsView({ session }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    request("/analytics?start=2026-01-01&end=2027-01-01", {
      headers: { Authorization: `Bearer ${session.token}` },
    })
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);
  if (error)
    return (
      <section className="analytics-panel">
        <p className="error">
          <CircleAlert size={15} />
          {error}
        </p>
      </section>
    );
  if (!data)
    return (
      <section className="analytics-panel">
        <p className="muted">Loading analytics...</p>
      </section>
    );
  return (
    <section className="analytics-panel">
      <div className="section-heading">
        <div>
          <p className="kicker">Reporting</p>
          <h2>Production pulse</h2>
        </div>
        <span className="request-id">2026 calendar year</span>
      </div>
      <div className="metric-grid">
        <div>
          <small>Requests</small>
          <strong>
            {data.requests_by_status.reduce((sum, item) => sum + item.count, 0)}
          </strong>
        </div>
        <div>
          <small>Median delivery</small>
          <strong>
            {data.median_submitted_to_delivered_days == null
              ? "—"
              : `${data.median_submitted_to_delivered_days.toFixed(1)}d`}
          </strong>
        </div>
        <div>
          <small>Recorded episodes</small>
          <strong>
            {data.episodes_per_day_robot.reduce(
              (sum, item) => sum + item.count,
              0,
            )}
          </strong>
        </div>
      </div>
      <div className="analytics-columns">
        <div>
          <p className="kicker">Request status</p>
          {data.requests_by_status.map((item) => (
            <div className="bar-row" key={item.status}>
              <span>{item.status.replace("_", " ")}</span>
              <strong>{item.count}</strong>
            </div>
          ))}
        </div>
        <div>
          <p className="kicker">Top good tasks</p>
          {data.top_good_tasks.map((item) => (
            <div className="bar-row" key={item.task_name}>
              <span>{item.task_name}</span>
              <strong>{item.count}</strong>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function AdminView({ session }) {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({
    email: "",
    password: "",
    name: "",
    role: "client",
    organisation: "",
  });
  const [notice, setNotice] = useState("");
  const auth = { Authorization: `Bearer ${session.token}` };
  async function load() {
    setUsers(await request("/users", { headers: auth }));
  }
  useEffect(() => {
    load();
  }, []);
  async function create(event) {
    event.preventDefault();
    try {
      await request("/users", {
        method: "POST",
        headers: auth,
        body: JSON.stringify(form),
      });
      setForm({
        email: "",
        password: "",
        name: "",
        role: "client",
        organisation: "",
      });
      setNotice("User created.");
      load();
    } catch (e) {
      setNotice(e.message);
    }
  }
  async function update(id, changes) {
    try {
      await request(`/users/${id}?${new URLSearchParams(changes)}`, {
        method: "PATCH",
        headers: auth,
      });
      load();
    } catch (e) {
      setNotice(e.message);
    }
  }
  return (
    <>
      <AnalyticsView session={session} />
      <section className="admin-panel">
        <div className="section-heading">
          <div>
            <p className="kicker">Administration</p>
            <h2>People & access</h2>
          </div>
          <span className="request-id">{users.length} accounts</span>
        </div>
        <div className="admin-grid">
          <form className="admin-form" onSubmit={create}>
            <label>
              Name
              <input
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>
            <label>
              Email
              <input
                required
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </label>
            <label>
              Temporary password
              <input
                required
                minLength="8"
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </label>
            <label>
              Organisation
              <input
                value={form.organisation}
                onChange={(e) =>
                  setForm({ ...form, organisation: e.target.value })
                }
              />
            </label>
            <label>
              Role
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                <option value="client">Client</option>
                <option value="operator">Operator</option>
                <option value="admin">Admin</option>
              </select>
            </label>
            <button className="primary" type="submit">
              <Plus size={15} /> Add user
            </button>
          </form>
          <div className="user-table">
            {users.map((item) => (
              <div className="user-row" key={item.id}>
                <div>
                  <strong>{item.name}</strong>
                  <small>{item.email}</small>
                </div>
                <select
                  value={item.role}
                  onChange={(e) => update(item.id, { role: e.target.value })}
                >
                  <option value="client">Client</option>
                  <option value="operator">Operator</option>
                  <option value="admin">Admin</option>
                </select>
                <button
                  className={`access-toggle ${item.active ? "active" : ""}`}
                  onClick={() => update(item.id, { active: !item.active })}
                >
                  {item.active ? "Active" : "Inactive"}
                </button>
              </div>
            ))}
          </div>
        </div>
        {notice && (
          <div className="notice">
            <CircleAlert size={15} />
            {notice}
          </div>
        )}
      </section>
    </>
  );
}

function App() {
  const [session, setSession] = useState(() =>
    JSON.parse(localStorage.getItem("fieldnote_session") || "null"),
  );
  function login(value) {
    localStorage.setItem("fieldnote_session", JSON.stringify(value));
    setSession(value);
  }
  async function logout() {
    if (session)
      await request("/auth/logout", {
        method: "POST",
        headers: { Authorization: `Bearer ${session.token}` },
      }).catch(() => {});
    localStorage.removeItem("fieldnote_session");
    setSession(null);
  }
  if (!session) return <Login onLogin={login} />;
  const isOperator = session.user.role !== "client";
  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark">
          <Activity size={18} /> FIELDNOTE
        </div>
        <div className="topbar-right">
          <span className="user-chip">
            <span className="avatar">{session.user.name[0]}</span>
            <span>
              <strong>{session.user.name}</strong>
              <small>{session.user.role}</small>
            </span>
          </span>
          <button className="icon-button" onClick={logout} title="Sign out">
            <LogOut size={17} />
          </button>
        </div>
      </header>
      <div className="app-content">
        <div className="page-intro">
          <div>
            <p className="kicker">
              {isOperator ? "Control room" : "Client portal"}
            </p>
            <h1>{isOperator ? "Fulfilment desk" : "Dataset requests"}</h1>
          </div>
          <span className="live-indicator">
            <span /> Systems operational
          </span>
        </div>
        {isOperator ? (
          <>
            <OperatorView session={session} />
            {session.user.role === "admin" && <AdminView session={session} />}
          </>
        ) : (
          <ClientView session={session} />
        )}
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
