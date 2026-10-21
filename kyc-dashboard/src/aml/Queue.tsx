import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "../components/ui";
import { useData, human, scenario, usd, download } from "./client";
import { Heading, Message, Stats } from "./shared";
export default function Queue() {
  const { data, error, loading, reload } = useData<any[]>("/alerts", 5000);
  const [search, setSearch] = useState(""),
    [scope, setScope] = useState("stream"),
    [priority, setPriority] = useState("All"),
    [status, setStatus] = useState("All");
  const all = data ?? [];
  const rows = all
    .filter(
      (r) =>
        (scope === "all" || r.source === scope) &&
        (priority === "All" || r.priority === priority) &&
        (status === "All" || r.case_status === status) &&
        `${r.customer_name} ${r.customer_id} ${r.alert_id}`
          .toLowerCase()
          .includes(search.toLowerCase()),
    )
    .sort(
      (a, b) =>
        ["high", "medium", "low"].indexOf(a.priority) -
        ["high", "medium", "low"].indexOf(b.priority),
    );
  return (
    <div className="page">
      <Heading
        title="Alert queue"
        description="Prioritize alerts, investigate customer activity and record a decision."
      />
      {error && (
        <Message error>
          {error}
          <button onClick={reload}>Retry</button>
        </Message>
      )}
      <Stats
        items={[
          ["Alerts", rows.length],
          ["High priority", rows.filter((r) => r.priority === "high").length],
          [
            "Awaiting review",
            rows.filter((r) => r.case_status === "awaiting_review").length,
          ],
          [
            "Provisional",
            rows.filter((r) => r.signal_status === "provisional").length,
          ],
        ]}
      />
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <label className="min-w-52 flex-1">
          Search
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Customer or alert reference"
          />
        </label>
        <label>
          Source
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="stream">Current stream</option>
            <option value="all">All activity</option>
            <option value="history">Historical</option>
          </select>
        </label>
        <label>
          Priority
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            {["All", "high", "medium", "low"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {["All", "not_started", "awaiting_review", "reviewed"].map((s) => (
              <option key={s} value={s}>
                {human(s)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="table-panel">
        <table>
          <thead>
            <tr>
              {[
                "Customer",
                "Scenario",
                "Priority",
                "Status",
                "Evidence value",
                "",
              ].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.alert_id}>
                <td>
                  <Link
                    className="font-medium text-white hover:text-brand"
                    to={`/investigations/${r.alert_id}`}
                  >
                    {r.customer_name}
                  </Link>
                  <p className="mt-1 text-xs text-neutral-500">{r.alert_id}</p>
                </td>
                <td>{scenario(r.pattern_ids)}</td>
                <td>
                  <Badge tone={r.priority === "high" ? "red" : r.priority === "medium" ? "amber" : "neutral"}>{r.priority} priority</Badge>
                </td>
                <td>
                  <Badge tone={r.report_stale ? "amber" : "neutral"}>
                    {r.report_stale ? "Evidence updated" : human(r.case_status)}
                  </Badge>
                  <p className="mt-1 text-xs text-neutral-500">
                    {r.signal_status}
                  </p>
                </td>
                <td className="whitespace-nowrap">{usd(r.amount)}</td>
                <td>
                  <Link
                    className="text-brand hover:underline"
                    to={`/investigations/${r.alert_id}`}
                  >
                    Investigate →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <p className="p-8 text-center text-neutral-400">
            {loading ? "Loading alerts…" : "No alerts match your filters."}
          </p>
        )}
      </div>
      <div className="mt-4 flex items-center justify-between gap-4">
        <p className="text-xs text-neutral-500">
          Evidence value includes both transaction directions; it is not an
          estimate of loss.
        </p>
        <button
          className="secondary"
          onClick={() =>
            download("alert-queue.json", JSON.stringify(rows, null, 2))
          }
        >
          Export queue
        </button>
      </div>
    </div>
  );
}
