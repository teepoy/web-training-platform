"use client";

import { FormEvent, useState } from "react";

type Inspection = {
  wafer_key: number;
  inspection_time: string;
  lot_id: string;
  wafer_id: string;
  layer_id: string;
  device: string;
  state: "draft" | "published";
  change_token: number | null;
  last_updated_at: string | null;
};

const eventRoutes = {
  "Create draft": ["POST", "/api/v1/inspections"],
  "Append records": ["POST", "/api/v1/inspections/records"],
  "Publish inspection": ["POST", "/api/v1/inspections/publish"],
  "Change source fields": ["PATCH", "/api/v1/inspections"],
  "Inspect one": ["POST", "/api/v1/inspections/inspect"],
} as const;

type EventName = keyof typeof eventRoutes;

const eventExamples: Record<EventName, object> = {
  "Create draft": {
    wafer_key: 7,
    inspection_time: "2026-08-30T01:02:00Z",
    lot_id: "LOT-1",
    wafer_id: "WAFER-1",
    layer_id: "LAYER-1",
    device: "DEVICE-1",
    inspect_equip_id: "EQP-1",
    recipe_key: 11,
    recipe_id: "RECIPE-1",
    origin_index_x: 0,
    origin_index_y: 0,
    center_x: 150000000,
    center_y: 150000000,
    origin_x: 145000000,
    origin_y: 145000000,
    die_size_x: 8000000,
    die_size_y: 5000000,
    defects: [],
    review_images: [],
    patch_archives: [],
  },
  "Append records": {
    wafer_key: 7,
    inspection_time: "2026-08-30T01:02:00Z",
    defects: [],
    review_images: [],
    patch_archives: [
      {
        archive_id: 1,
        s3_bucket: "sc-patch-images",
        s3_key: "manual/inspection.zip",
      },
    ],
  },
  "Publish inspection": {
    wafer_key: 7,
    inspection_time: "2026-08-30T01:02:00Z",
    published_at: "2026-08-30T01:05:00Z",
  },
  "Change source fields": {
    wafer_key: 7,
    inspection_time: "2026-08-30T01:02:00Z",
    changed_at: "2026-08-30T01:06:00Z",
    device: "DEVICE-2",
  },
  "Inspect one": {
    wafer_key: 7,
    inspection_time: "2026-08-30T01:02:00Z",
  },
};

function now(offsetMinutes = 0): string {
  return new Date(Date.now() + offsetMinutes * 60_000).toISOString();
}

export function UpstreamMockConsole() {
  const [token, setToken] = useState("");
  const [rows, setRows] = useState<Inspection[]>([]);
  const [state, setState] = useState<"" | "draft" | "published">("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Enter the upstream mock token to begin.");
  const [eventName, setEventName] = useState<EventName>("Create draft");
  const [eventBody, setEventBody] = useState(
    JSON.stringify(eventExamples["Create draft"], null, 2),
  );
  const [scenario, setScenario] = useState({
    inspection_time: now(-5),
    published_at: now(),
    total_defects: 2500,
    imaged_defects: 16,
    images_per_defect: 5,
    gallery_defects: 64,
    gallery_imaged_defects: 8,
    defects_per_archive: 500,
    append_batch_size: 500,
  });

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    sessionStorage.setItem("upstream-mock-token", token);
    const response = await fetch(path, {
      ...init,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
    if (!response.ok) {
      const problem = (await response.json().catch(() => ({}))) as {
        detail?: string;
      };
      throw new Error(problem.detail ?? `${response.status} ${response.statusText}`);
    }
    return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
  }

  async function refresh() {
    setBusy(true);
    try {
      const query = state ? `?state=${state}` : "";
      const values = await request<Inspection[]>(`/api/v1/inspections${query}`);
      setRows(values);
      setMessage(`${values.length} inspection${values.length === 1 ? "" : "s"} loaded.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  async function runScenario(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("Publishing objects, records, and change tokens…");
    try {
      const result = await request<{ inspections: Array<{ reused: boolean }> }>(
        "/api/v1/scenarios/dev-showcase",
        { method: "POST", body: JSON.stringify(scenario) },
      );
      const reused = result.inspections.filter((item) => item.reused).length;
      setMessage(
        `Scenario complete: ${result.inspections.length - reused} published, ${reused} reused.`,
      );
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Scenario failed");
      setBusy(false);
    }
  }

  function chooseEvent(name: EventName) {
    setEventName(name);
    setEventBody(JSON.stringify(eventExamples[name], null, 2));
  }

  async function sendEvent(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const [method, path] = eventRoutes[eventName];
      await request(path, { method, body: JSON.stringify(JSON.parse(eventBody)) });
      setMessage(`${eventName} accepted by the mock.`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Event failed");
      setBusy(false);
    }
  }

  return (
    <section className="workspace">
      <aside className="control-panel">
        <div className="panel-heading">
          <span className="step">01</span>
          <div>
            <h2>Connect</h2>
            <p>The token stays in this browser tab.</p>
          </div>
        </div>
        <label>
          Bearer token
          <input
            type="password"
            value={token}
            placeholder="Paste UPSTREAM_MOCK_TOKEN"
            onChange={(event) => setToken(event.target.value)}
          />
        </label>
        <div className="filter-row">
          <label>
            State
            <select
              value={state}
              onChange={(event) => setState(event.target.value as "" | "draft" | "published")}
            >
              <option value="">All</option>
              <option value="draft">Draft</option>
              <option value="published">Published</option>
            </select>
          </label>
          <button type="button" onClick={refresh} disabled={busy || !token}>
            Refresh
          </button>
        </div>

        <div className="divider" />
        <div className="panel-heading">
          <span className="step">02</span>
          <div>
            <h2>Run a behavior</h2>
            <p>One named scenario, visible inputs, repeatable output.</p>
          </div>
        </div>
        <form onSubmit={runScenario}>
          <div className="field-grid">
            {Object.entries(scenario).map(([name, value]) => (
              <label key={name} className={name.includes("time") ? "wide" : ""}>
                {name.replaceAll("_", " ")}
                <input
                  type={name.includes("time") ? "text" : "number"}
                  min={name.includes("time") ? undefined : 0}
                  value={value}
                  onChange={(event) =>
                    setScenario((current) => ({
                      ...current,
                      [name]: name.includes("time")
                        ? event.target.value
                        : Number(event.target.value),
                    }))
                  }
                />
              </label>
            ))}
          </div>
          <button className="primary" disabled={busy || !token}>
            {busy ? "Working…" : "Publish dev showcase"}
          </button>
        </form>

        <div className="divider" />
        <div className="panel-heading">
          <span className="step">03</span>
          <div>
            <h2>Compose an event</h2>
            <p>Edit the real compatibility payload and send it through HTTP.</p>
          </div>
        </div>
        <form onSubmit={sendEvent}>
          <label>
            Event
            <select
              value={eventName}
              onChange={(event) => chooseEvent(event.target.value as EventName)}
            >
              {Object.keys(eventRoutes).map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          <label className="json-editor">
            JSON payload
            <textarea
              spellCheck={false}
              value={eventBody}
              onChange={(event) => setEventBody(event.target.value)}
            />
          </label>
          <button className="primary" disabled={busy || !token}>
            Send upstream event
          </button>
        </form>
      </aside>

      <div className="results-panel">
        <div className="results-heading">
          <div>
            <p className="eyebrow">Observed PostgreSQL state</p>
            <h2>Inspections</h2>
          </div>
          <span className="status" role="status">
            {message}
          </span>
        </div>
        {rows.length === 0 ? (
          <div className="empty-state">
            <span>∅</span>
            <h3>No rows loaded</h3>
            <p>Refresh the list or publish a scenario to see upstream state.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Wafer</th>
                  <th>Lot / wafer</th>
                  <th>Layer / device</th>
                  <th>State</th>
                  <th>Change</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.wafer_key}-${row.inspection_time}`}>
                    <td>
                      <strong>{row.wafer_key}</strong>
                      <small>{new Date(row.inspection_time).toLocaleString()}</small>
                    </td>
                    <td>
                      {row.lot_id}
                      <small>{row.wafer_id}</small>
                    </td>
                    <td>
                      {row.layer_id}
                      <small>{row.device}</small>
                    </td>
                    <td>
                      <span className={`pill ${row.state}`}>{row.state}</span>
                    </td>
                    <td>
                      <strong>{row.change_token ?? "—"}</strong>
                      <small>
                        {row.last_updated_at
                          ? new Date(row.last_updated_at).toLocaleTimeString()
                          : "not visible yet"}
                      </small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
