import { useState } from "react";
import { Panel, Badge } from "../components/ui";
import { useData, download, human } from "./client";
import { Heading, Message, Stats, Json } from "./shared";
export function Audit() {
  const { data, error } = useData("/audit"),
    [query, setQuery] = useState("");
  const events = (data?.events ?? [])
    .filter((e: any) =>
      `${e.actor} ${e.event} ${e.case_id}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    )
    .reverse();
  return (
    <div className="page">
      <Heading
        title="Audit trail"
        description="Review recorded evidence activity and attributed investigator decisions."
      />
      {error && <Message error>{error}</Message>}
      {data && (
        <>
          <Stats
            items={[
              ["Events", data.events.length],
              ["Integrity", data.valid ? "Verified" : "FAILED"],
              [
                "Human decisions",
                data.events.filter((e: any) => e.event === "human_decision")
                  .length,
              ],
              [
                "Agent executions",
                data.events.filter((e: any) => e.event === "agent_completed")
                  .length,
              ],
            ]}
          />
          <label>
            Filter by actor, activity or case
            <input
              className="mb-5"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="table-panel">
            <table>
              <thead>
                <tr>
                  {["Time (UTC)", "Actor", "Activity", "Case"].map((s) => (
                    <th key={s}>{s}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {events.map((e: any) => (
                  <tr key={e.seq}>
                    <td>{e.ts}</td>
                    <td>{human(e.actor)}</td>
                    <td>{human(e.event)}</td>
                    <td>{e.case_id ?? "Monitoring"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            className="secondary mt-4"
            onClick={() =>
              download("audit.json", JSON.stringify(events, null, 2))
            }
          >
            Export audit register
          </button>
        </>
      )}
    </div>
  );
}
export function Policies() {
  const { data: p, error } = useData("/policies");
  return (
    <div className="page">
      <Heading
        title="Detection policies"
        description="Inspect detection scenarios and thresholds configured in PostgreSQL."
      />
      {error && <Message error>{error}</Message>}
      <div className="space-y-4">
        {p?.patterns?.map((r: any) => (
          <Panel
            key={r.pattern_id}
            title={`${r.pattern_id} · ${r.pattern_name}`}
            action={<Badge tone="brand">Enabled</Badge>}
          >
            <p className="mb-4 text-sm">
              {typeof r.detection_logic === "string"
                ? r.detection_logic
                : JSON.stringify(r.detection_logic)}
            </p>
            <details>
              <summary>Thresholds and sources</summary>
              <Json value={r.demo_thresholds} />
              <div className="mt-4 flex flex-wrap gap-4">
                {r.source_refs?.map((ref: any) => (
                  <a
                    key={ref.source_id}
                    className="text-sm text-brand underline"
                    href={ref.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {ref.source_id}
                  </a>
                ))}
              </div>
            </details>
          </Panel>
        ))}
      </div>
    </div>
  );
}
