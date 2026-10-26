import { titleCase } from "../utils/titleCase";
import { useEffect, useRef } from "react";
import { Badge } from "../components/ui";
import { human, usd } from "./client";

type RecordValue = Record<string, any>;
const labels: Record<string, string> = {
  fake_name: "Customer name", cash_total: "Cash value under review",
  expected_monthly_cash_max: "Expected monthly cash maximum", near_threshold_count: "Near-threshold transactions",
  annual_income_or_revenue_usd: "Annual income or revenue", kyc_profile: "KYC profile",
  pep_flag: "Politically exposed person", id_verified: "Identity verified", naics_code: "NAICS code",
  min: "Minimum", max: "Maximum", threshold_type: "Threshold basis", min_txn_count: "Minimum transactions",
  min_aggregate_usd: "Aggregate threshold (must be exceeded)", window_days: "Rolling window (days)",
  near_threshold_floor_usd: "Minimum transaction amount", near_threshold_ceiling_usd: "Maximum transaction amount",
  min_outflow_to_inflow_ratio: "Minimum share of funds sent out", amount_tolerance_pct: "Amount tolerance",
  min_out_of_region_share: "Minimum out-of-region share", min_round_wire_share: "Minimum round-amount share",
  window_start: "First transaction (UTC)", window_end: "Last transaction (UTC)",
  display_pair_ratios_3dp: "Matched payment ratios", source_refs: "Reference guidance",
};
const label = (key: string) => labels[key] ?? (/^TM-\d+$/.test(key) ? key : human(key.replace(/_usd$/, " (USD)")).replace(/\b(id|usd|naics)\b/gi, word => word.toUpperCase()));
const moneyKey = (key: string) => /_usd$|^amount$|cash_total|expected_monthly_cash_max|^balance$/.test(key);
function display(value: any, key: string): string {
  if (value === null || value === undefined || value === "") return "Not available";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (moneyKey(key)) return usd(value);
    if (key.includes("share") || key.endsWith("_ratio") || key.endsWith("_pct")) return `${Number((value*100).toFixed(2))}%`;
    if (key.endsWith("percent")) return `${value}%`;
    return value.toLocaleString("en-US");
  }
  if (value === "SYNTHETIC_DEMO_CONFIG_NOT_REGULATORY") return "Demo configuration — not a regulatory requirement";
  if (/^\d{4}-\d{2}-\d{2}/.test(value)) {
    const parsed = new Date(value.length === 10 ? `${value}T00:00:00Z` : /Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
    if (!Number.isNaN(parsed.valueOf())) return new Intl.DateTimeFormat("en-US", {month:"short", day:"numeric", year:"numeric", timeZone:"UTC", ...(value.length > 10 ? {hour:"2-digit", minute:"2-digit",second:"2-digit",timeZoneName:"short"} as const : {})}).format(parsed);
  }
  if (["risk_rating","customer_type","direction","signal_status","status","sanctions_status","level","id_document_type","address_type"].includes(key)) return human(value);
  return String(value);
}
function Readable({value, field = ""}: {value: any; field?: string}) {
  if (Array.isArray(value)) {
    if (!value.length) return <p className="evidence-muted">No records provided.</p>;
    return <ul className="readable-list">{value.map((item, i) => <li key={i}><Readable value={item} field={field} /></li>)}</ul>;
  }
  if (value && typeof value === "object") {
    if (!Object.keys(value).length) return <p className="evidence-muted">No records provided.</p>;
    const simple = Object.entries(value).filter(([,v]) => v === null || typeof v !== "object");
    const nested = Object.entries(value).filter(([,v]) => v !== null && typeof v === "object");
    return <><dl className="evidence-fields">{simple.map(([key,v])=><div key={key}><dt>{label(key)}</dt><dd>{display(v, (key === "min" || key === "max") && moneyKey(field) ? field : key)}</dd></div>)}</dl>{nested.map(([key,v])=><section className="evidence-group" key={key}><h4>{titleCase(label(key))}</h4><Readable value={v} field={key}/></section>)}</>;
  }
  return <span>{display(value,field)}</span>;
}
function Customer({value:v}: {value:RecordValue}) {
  const fields = {business_name:v.business_name, customer_name:v.fake_name, customer_id:v.customer_id, account_id:v.account_id, customer_type:v.customer_type, risk_rating:v.risk_rating, occupation_or_industry:v.occupation_or_industry, source_of_funds:v.kyc_profile?.source_of_funds};
  return <><Readable value={fields}/>{v.normal_behavior_summary && <div className="evidence-callout"><h4>Expected Account Activity</h4><p>{v.normal_behavior_summary}</p></div>}
    {v.expected_cash_activity && <section className="evidence-group"><h4>Expected Cash Activity</h4><Readable value={v.expected_cash_activity}/></section>}
    <details className="mt-5"><summary>Full customer profile and KYC details</summary><Readable value={v}/></details></>;
}
function Transactions({rows}: {rows: RecordValue[]}) {
  return <div className="table-panel evidence-table"><table><thead><tr>{["Transaction","Date and time (UTC)","Type","Direction","Amount"].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={r.transaction_id ?? i}><td>{r.transaction_id}</td><td>{display(r.txn_ts,"txn_ts")}</td><td>{human(r.txn_type)}</td><td>{human(r.direction)}</td><td className="whitespace-nowrap">{usd(r.amount)}</td></tr>)}</tbody></table></div>;
}
function Coverage({value:v}: {value:RecordValue}) {
  const required: string[] = v.required ?? [], missing: string[] = v.missing ?? [], provided: string[] = v.provided ?? [];
  return <><p className="evidence-muted mb-4">{provided.length} provided · {missing.length} outstanding</p><ul className="coverage-list">{Array.from(new Set([...required,...provided,...missing])).map(item=><li key={item}><span>{item}</span><Badge tone={missing.includes(item) ? "amber" : provided.includes(item) ? "green" : "neutral"}>{missing.includes(item) ? "Required" : provided.includes(item) ? "Provided" : "Not confirmed"}</Badge></li>)}</ul><p className="evidence-muted mt-4">Coverage refers to supporting documents. Profile and transaction records may already be available elsewhere in the case.</p></>;
}
function Reference({value:v}: {value:RecordValue}) {
  return <section className="evidence-reference"><h4>{v.pattern_id} · {titleCase(v.pattern_name)}</h4><p>{v.detection_logic}</p>{v.legitimate_explanations?.length > 0 && <div className="evidence-group"><h4>Potential Legitimate Explanations to Verify</h4><ul className="readable-list">{v.legitimate_explanations.map((s:string)=><li key={s}>{s}</li>)}</ul></div>}
    <div className="mt-4 flex flex-wrap gap-4">{v.source_refs?.map((r:RecordValue)=>/^https?:\/\//.test(r.url) ? <a className="text-sm text-brand underline" key={r.source_id} href={r.url} target="_blank" rel="noreferrer">{r.source_id.replace(/^SRC-/,"")} {r.pages ? `· pages ${r.pages}` : ""} ↗</a> : <span key={r.source_id}>{r.source_id}</span>)}</div></section>;
}
function EvidenceValue({value:v}: {value:any}) {
  if (Array.isArray(v)) {
    if (v.length && v[0]?.transaction_id) return <Transactions rows={v}/>;
    if (v.length && v[0]?.source_refs) return <div className="space-y-6">{v.map((r,i)=><Reference key={r.pattern_id ?? i} value={r}/>)}</div>;
  }
  if (v && !Array.isArray(v) && typeof v === "object") {
    if (v.kyc_profile) return <Customer value={v}/>;
    if (Array.isArray(v.required) && Array.isArray(v.missing)) return <Coverage value={v}/>;
    if (v.INCOMING || v.OUTGOING) return <><p className="evidence-muted mb-4">Committed account history at the time of this assessment. These totals cover the account history, not only the alert transactions.</p><div className="table-panel"><table><thead><tr><th>Direction</th><th>Transaction count</th><th>Total amount</th></tr></thead><tbody>{Object.entries(v).map(([direction,totals])=><tr key={direction}><td>{human(direction)}</td><td>{display((totals as any).count,"count")}</td><td>{display((totals as any).amount,"amount")}</td></tr>)}</tbody></table></div></>;
    if (!Object.keys(v).length) return <p className="evidence-muted">No records were included in this evidence item. This does not indicate that screening or verification was completed.</p>;
  }
  return <Readable value={v}/>;
}
export default function Evidence({alert, report, selected}: {alert:RecordValue;report:RecordValue|null;selected:string|null}) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(()=>{if (selected) root.current?.querySelector(`[data-evidence-id="${CSS.escape(selected)}"]`)?.scrollIntoView({block:"start"});},[selected]);
  return <div ref={root} className="evidence-workspace">
    <section className="evidence-card"><header><div><h2>Activity Behind This Alert</h2><p>Observed values used in the assessment.</p></div></header><div className="evidence-body"><Readable value={alert.metrics}/><p className="evidence-muted mt-4">The alert total and expected monthly activity can cover different periods. Compare their time windows before drawing conclusions.</p></div></section>
    {!report?.evidence?.length && <p className="evidence-muted">Run the investigation to assemble the supporting evidence.</p>}
    {(report?.evidence ?? []).filter((item:RecordValue) => item.title !== "Counterparty registry").map((item:RecordValue)=><section key={item.id} data-evidence-id={item.id} className={`evidence-card ${selected===item.id ? "evidence-selected" : ""}`}><header><div><span className="evidence-number">{item.id} · {human(item.kind)}</span><h2>{titleCase(item.title === "Deterministic rule results" ? "How the detection rule was met" : item.title)}</h2></div></header><div className="evidence-body"><EvidenceValue value={item.value}/><details className="evidence-provenance"><summary>Evidence source</summary><p>{item.source}</p></details></div></section>)}
  </div>;
}
