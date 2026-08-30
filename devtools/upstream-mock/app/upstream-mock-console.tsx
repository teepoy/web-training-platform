"use client";

import { FormEvent, useEffect, useState } from "react";

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

type Health = "checking" | "online" | "offline";
type ResponseRecord = { label: string; status: number | "error"; body: unknown };
type Activity = Omit<ResponseRecord, "body"> & { id: string; time: string };

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
      { archive_id: 1, s3_bucket: "sc-patch-images", s3_key: "manual/inspection.zip" },
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
  "Inspect one": { wafer_key: 7, inspection_time: "2026-08-30T01:02:00Z" },
};

function now(offsetMinutes = 0): string {
  return new Date(Date.now() + offsetMinutes * 60_000).toISOString();
}

function payloadFor(name: EventName, inspection?: Inspection): string {
  const payload = { ...eventExamples[name] } as Record<string, unknown>;
  if (inspection) {
    payload.wafer_key = inspection.wafer_key;
    payload.inspection_time = inspection.inspection_time;
  }
  return JSON.stringify(payload, null, 2);
}

export function UpstreamMockConsole() {
  const [token, setToken] = useState("");
  const [health, setHealth] = useState<Health>("checking");
  const [rows, setRows] = useState<Inspection[]>([]);
  const [state, setState] = useState<"" | "draft" | "published">("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Add the bearer token to enable write tools.");
  const [eventName, setEventName] = useState<EventName>("Create draft");
  const [eventBody, setEventBody] = useState(payloadFor("Create draft"));
  const [lastResponse, setLastResponse] = useState<ResponseRecord | null>(null);
  const [activity, setActivity] = useState<Activity[]>([]);
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

  useEffect(() => {
    fetch("/health")
      .then((response) => setHealth(response.ok ? "online" : "offline"))
      .catch(() => setHealth("offline"));
  }, []);

  function recordActivity(record: ResponseRecord) {
    setActivity((current) =>
      [
        {
          id: crypto.randomUUID(),
          label: record.label,
          status: record.status,
          time: new Date().toLocaleTimeString(),
        },
        ...current,
      ].slice(0, 12),
    );
  }

  async function request<T>(
    label: string,
    path: string,
    init?: RequestInit,
    captureResponse = true,
  ): Promise<T> {
    let recorded = false;
    try {
      const response = await fetch(path, {
        ...init,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          ...init?.headers,
        },
      });
      const body = response.status === 204 ? null : await response.json().catch(() => null);
      const record: ResponseRecord = { label, status: response.status, body };
      if (captureResponse) setLastResponse(record);
      recordActivity(record);
      recorded = true;
      if (!response.ok) {
        const problem = body as { detail?: string } | null;
        throw new Error(problem?.detail ?? `${response.status} ${response.statusText}`);
      }
      return body as T;
    } catch (error) {
      if (!recorded) {
        const record: ResponseRecord = {
          label,
          status: "error",
          body: error instanceof Error ? error.message : "Request failed",
        };
        if (captureResponse) setLastResponse(record);
        recordActivity(record);
      }
      throw error;
    }
  }

  async function refresh(captureResponse = true) {
    setBusy(true);
    try {
      const query = state ? `?state=${state}` : "";
      const values = await request<Inspection[]>(
        "List inspections",
        `/api/v1/inspections${query}`,
        undefined,
        captureResponse,
      );
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
    setMessage("Generating published upstream data…");
    try {
      const result = await request<{ inspections: Array<{ reused: boolean }> }>(
        "Generate dev showcase",
        "/api/v1/scenarios/dev-showcase",
        { method: "POST", body: JSON.stringify(scenario) },
      );
      const reused = result.inspections.filter((item) => item.reused).length;
      setMessage(
        `Scenario complete: ${result.inspections.length - reused} published, ${reused} reused.`,
      );
      await refresh(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Scenario failed");
      setBusy(false);
    }
  }

  function chooseEvent(name: EventName, inspection?: Inspection) {
    setEventName(name);
    setEventBody(payloadFor(name, inspection));
  }

  async function sendEvent(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const [method, path] = eventRoutes[eventName];
      await request(eventName, path, {
        method,
        body: JSON.stringify(JSON.parse(eventBody)),
      });
      setMessage(`${eventName} accepted by the mock.`);
      await refresh(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Event failed");
      setBusy(false);
    }
  }

  return (
    <section className="console">
      <div className="connection-bar">
        <span className={`health ${health}`}>
          <i />
          API {health}
        </span>
        <label className="token-field">
          Bearer token
          <input
            type="password"
            value={token}
            placeholder="UPSTREAM_MOCK_TOKEN"
            onChange={(event) => setToken(event.target.value)}
          />
        </label>
        <label>
          State filter
          <select
            value={state}
            onChange={(event) => setState(event.target.value as "" | "draft" | "published")}
          >
            <option value="">All</option>
            <option value="draft">Draft</option>
            <option value="published">Published</option>
          </select>
        </label>
        <button type="button" onClick={() => refresh()} disabled={busy || !token}>
          Reload state
        </button>
        <span className="status" role="status">
          {message}
        </span>
      </div>

      <div className="tool-grid">
        <div className="tool-column">
          <section className="panel event-panel">
            <div className="panel-title">
              <div>
                <h2>Send an upstream event</h2>
                <p>Choose an event, edit its compatibility payload, then send it over HTTP.</p>
              </div>
              <code>
                {eventRoutes[eventName][0]} {eventRoutes[eventName][1]}
              </code>
            </div>
            <div className="event-picker" role="group" aria-label="Upstream event type">
              {(Object.keys(eventRoutes) as EventName[]).map((name) => (
                <button
                  type="button"
                  key={name}
                  className={eventName === name ? "selected" : ""}
                  aria-pressed={eventName === name}
                  onClick={() => chooseEvent(name)}
                >
                  {name}
                </button>
              ))}
            </div>
            <form onSubmit={sendEvent}>
              <label>
                JSON payload
                <textarea
                  className="json-editor"
                  spellCheck={false}
                  value={eventBody}
                  onChange={(event) => setEventBody(event.target.value)}
                />
              </label>
              <div className="button-row">
                <button type="button" onClick={() => chooseEvent(eventName)}>
                  Reset example
                </button>
                <button className="primary" disabled={busy || !token}>
                  Send event
                </button>
              </div>
            </form>
          </section>

          <details className="panel scenario-panel">
            <summary>
              <span>
                <strong>Generate dev showcase</strong>
                <small>Create a repeatable published inspection and records.</small>
              </span>
              <span>Scenario tool</span>
            </summary>
            <form onSubmit={runScenario}>
              <div className="field-grid">
                {Object.entries(scenario).map(([name, value]) => {
                  const isTimestamp = name.includes("time") || name.endsWith("_at");
                  return (
                    <label key={name} className={isTimestamp ? "wide" : ""}>
                      {name.replaceAll("_", " ")}
                      <input
                        type={isTimestamp ? "text" : "number"}
                        min={isTimestamp ? undefined : 0}
                        value={value}
                        onChange={(event) =>
                          setScenario((current) => ({
                            ...current,
                            [name]: isTimestamp ? event.target.value : Number(event.target.value),
                          }))
                        }
                      />
                    </label>
                  );
                })}
              </div>
              <button className="primary" disabled={busy || !token}>
                Generate fixtures
              </button>
            </form>
          </details>
        </div>

        <div className="response-column">
          <section className="panel response-panel">
            <div className="panel-title">
              <div>
                <h2>Last response</h2>
                <p>The most recent tool response, including failures.</p>
              </div>
              {lastResponse && (
                <span className={`response-status s-${lastResponse.status}`}>
                  {lastResponse.status}
                </span>
              )}
            </div>
            <pre>
              {lastResponse ? JSON.stringify(lastResponse.body, null, 2) : "No request sent yet."}
            </pre>
          </section>

          <section className="panel activity-panel">
            <div className="panel-title">
              <div>
                <h2>Recent requests</h2>
                <p>Browser-local activity for this session.</p>
              </div>
            </div>
            {activity.length === 0 ? (
              <p className="empty-copy">Requests will appear here.</p>
            ) : (
              <ol>
                {activity.map((item) => (
                  <li key={item.id}>
                    <span>
                      <strong>{item.label}</strong>
                      <small>{item.time}</small>
                    </span>
                    <span className={`response-status s-${item.status}`}>{item.status}</span>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      </div>

      <section className="panel state-panel">
        <div className="panel-title">
          <div>
            <h2>Observed inspection state</h2>
            <p>Rows currently visible in the mock PostgreSQL database.</p>
          </div>
          <span>{rows.length} rows</span>
        </div>
        {rows.length === 0 ? (
          <p className="empty-copy">No rows loaded. Add a token and reload state.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Key / time</th>
                  <th>Lot / wafer</th>
                  <th>Layer / device</th>
                  <th>State</th>
                  <th>Change</th>
                  <th />
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
                          : "not visible"}
                      </small>
                    </td>
                    <td>
                      <button type="button" onClick={() => chooseEvent("Inspect one", row)}>
                        Load inspect event
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  );
}
