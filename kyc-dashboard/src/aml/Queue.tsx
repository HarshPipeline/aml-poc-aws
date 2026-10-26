import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "../components/ui";
import { useData, scenario, download } from "./client";
import { Heading, Message } from "./shared";

export default function Queue() {
  const { data, error, loading, reload } = useData<any[]>("/alerts", 5000);
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState("stream");
  const [priority, setPriority] = useState("all");
  const [view, setView] = useState("open");
  const all = (data ?? []).filter(r => scope === "all" || r.source === scope);
  const open = all.filter(r => r.case_status !== "reviewed");
  const rows = all.filter(r =>
    (view === "all" || (view === "open" ? r.case_status !== "reviewed" : r.case_status === "reviewed")) &&
    (priority === "all" || r.priority === priority) &&
    `${r.customer_name} ${r.customer_id} ${r.alert_id}`.toLowerCase().includes(search.toLowerCase())
  ).sort((a,b) => ["high","medium","low"].indexOf(a.priority) - ["high","medium","low"].indexOf(b.priority));
  return <div className="page queue-page">
    <Heading title="Investigations" description="Review alerts, assess supporting evidence and record investigation outcomes." />
    {error && <Message error>{error} <button className="secondary ml-3" onClick={reload}>Retry</button></Message>}
    <div className="queue-summary">
      <div><strong>{loading ? "—" : open.length}</strong><span>Awaiting review</span></div>
      <div><strong>{loading ? "—" : open.filter(r => r.priority === "high").length}</strong><span>High priority</span></div>
      <div><strong>{loading ? "—" : all.length-open.length}</strong><span>Reviewed</span></div>
    </div>
    <div className="queue-toolbar">
      <nav className="view-tabs" aria-label="Investigation status">
        {[["open","Awaiting review"],["reviewed","Reviewed"],["all","All"]].map(([id,label]) =>
          <button key={id} aria-pressed={view===id} className={view===id ? "selected" : ""} onClick={() => setView(id)}>{label}</button>)}
      </nav>
      <input aria-label="Search investigations" placeholder="Search customer or alert…" value={search} onChange={e=>setSearch(e.target.value)} />
      <details className="queue-filters"><summary>Filters{scope !== "stream" || priority !== "all" ? " · Active" : ""}</summary>
        <div className="flex flex-wrap gap-4 pt-3">
          <label>Activity<select value={scope} onChange={e=>setScope(e.target.value)}><option value="stream">Recent activity</option><option value="all">All activity</option><option value="history">Historical</option></select></label>
          <label>Priority<select value={priority} onChange={e=>setPriority(e.target.value)}><option value="all">All priorities</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
        </div>
      </details>
    </div>
    <div className="table-panel queue-table"><table>
      <thead><tr><th>Customer</th><th>Alert category</th><th>Priority</th><th>Required action</th><th><span className="sr-only">Open investigation</span></th></tr></thead>
      <tbody>{rows.map(r=><tr key={r.alert_id}>
        <td><Link className="customer-link" to={`/investigations/${r.alert_id}`}>{r.customer_name}</Link><p className="mt-1 text-xs text-neutral-500">{r.alert_id}</p></td>
        <td>{scenario(r.pattern_ids)}{r.signal_status === "provisional" && <p className="text-xs text-amber-300">Provisional signal</p>}{r.signal_status === "withdrawn" && <p className="text-xs text-neutral-400">Withdrawn signal</p>}</td>
        <td><span className={`priority-dot ${r.priority}`} />{r.priority === "high" ? "High" : r.priority === "medium" ? "Medium" : "Low"}</td>
        <td>{r.report_stale ? <Badge tone="amber">Update report</Badge> : r.case_status === "reviewed" ? "Decision recorded" : r.case_status === "awaiting_review" ? "Review assessment" : "Start investigation"}</td>
        <td><Link className="open-case" to={`/investigations/${r.alert_id}`}>Review <span aria-hidden="true">→</span></Link></td>
      </tr>)}</tbody>
    </table>{!rows.length && <div className="p-10 text-center"><p>{loading ? "Loading investigations…" : "No alerts in this view"}</p>{!loading && <p className="mt-2 text-sm text-neutral-400">Change the filters or view incoming activity in <Link className="text-brand" to="/monitoring">Monitoring</Link>.</p>}</div>}</div>
    <div className="mt-5 flex items-center justify-between text-xs text-neutral-500"><span>{rows.length} alerts · {scope === "stream" ? "Recent activity" : scope === "history" ? "Historical activity" : "All activity"} · Highest priority first</span><button className="hover:text-white" onClick={()=>download("alert-queue.json",JSON.stringify(rows,null,2))}>Export alerts</button></div>
  </div>;
}
