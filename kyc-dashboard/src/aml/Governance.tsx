import { titleCase } from "../utils/titleCase";
import { useState } from "react";
import { Badge } from "../components/ui";
import { useData, download, human } from "./client";
import { Heading, Message, Stats } from "./shared";
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
        title="Audit Trail"
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
const policyGuides: Record<string, {title: string; summary: string; review: string; note?: string}> = {
  "TM-01": {
    title: "Repeated cash transactions below the reporting threshold",
    summary: "Identifies a series of cash transactions just below $10,000 that may warrant further review.",
    review: "Compare the deposits with the customer's expected cash activity and obtain a source-of-funds explanation before escalation.",
  },
  "TM-03": {
    title: "Cash deposits outside the customer's operating region",
    summary: "Identifies accounts receiving repeated cash deposits from locations outside their documented operating area.",
    review: "Check the deposit locations, depositor details and whether the customer has a legitimate business reason for activity in those states.",
  },
  "TM-04": {
    title: "Rapid movement of deposited funds",
    summary: "Identifies funnel-account activity where most incoming funds quickly leave the same checking account.",
    review: "Review the outgoing recipients, payment purpose and supporting documents to understand why the funds moved so quickly.",
    note: "This demo monitors movement within one checking account. Consolidation across multiple accounts is not implemented; its configured source-account threshold is not used by this detector.",
  },
  "TM-07": {
    title: "Incoming funds quickly passed to another party",
    summary: "Identifies repeated incoming and outgoing payments with the same or nearly the same amounts.",
    review: "Confirm the relationship between the parties and the business purpose of the payments. Review any countries that conflict with the customer's profile.",
    note: "Jurisdiction risk uses the demo risk table. It is not a live jurisdiction-risk feed.",
  },
  "TM-08": {
    title: "A sudden burst of wire transfers",
    summary: "Identifies a period of concentrated wire activity surrounded by long periods of inactivity.",
    review: "Compare the wire activity with the customer's expected behavior and establish the reason for the sudden start and stop.",
    note: "An initial alert may be provisional. Confirmation requires the full quiet period after the burst; future inactivity is not assumed.",
  },
  "TM-09": {
    title: "International wires requiring additional review",
    summary: "Identifies international wires with round amounts, unfamiliar parties, missing information or country-profile inconsistencies.",
    review: "Verify counterparties, payment details and country exposure. Give greater attention to cases with several indicators occurring together.",
  },
};
const thresholdLabels: Record<string, string> = {
  window_days: "Review period", lookback_days: "Review period", min_txn_count: "Minimum cash transactions",
  min_aggregate_usd: "Combined cash value", near_threshold_floor_usd: "Minimum amount per transaction",
  near_threshold_ceiling_usd: "Maximum amount per transaction", min_deposit_count: "Minimum deposits",
  min_out_of_region_share: "Deposits outside the operating region", min_distinct_out_of_state_states: "Minimum states outside the operating region",
  min_outflow_to_inflow_ratio: "Minimum share of incoming funds sent out", max_hours_deposit_to_outflow: "Time allowed for funds to leave",
  min_source_accounts_to_consolidated: "Source accounts for consolidation (not implemented)", min_pairs: "Minimum matched payment pairs",
  min_amount_usd: "Minimum incoming payment", max_days_between: "Time between incoming and outgoing payments",
  amount_tolerance_pct: "Maximum difference between payment amounts", jurisdiction_risk_source: "Jurisdiction reference",
  quiet_days_before: "Inactivity before the burst", quiet_days_after: "Inactivity after the burst",
  min_burst_total_usd: "Minimum total wire value", min_burst_wire_count: "Minimum wires in the burst",
  active_burst_days_max: "Maximum duration of the burst", min_wire_count: "Minimum international wires",
  min_round_wire_share: "Round-amount share (one alternative trigger)", new_counterparty_days: "New-counterparty reference period",
};
function thresholdValue(key: string, value: unknown, id: string): string {
  if (key === "jurisdiction_risk_source") return human(value);
  if (typeof value !== "number") return human(value);
  if (key.endsWith("_usd")) {
    const amount = new Intl.NumberFormat("en-US", {style:"currency",currency:"USD",maximumFractionDigits:2,minimumFractionDigits:0}).format(value);
    return key === "min_aggregate_usd" && id === "TM-01" ? `More than ${amount}` : amount;
  }
  if (key.includes("share") || key.includes("ratio") || key.endsWith("_pct")) return `${Number((value*100).toFixed(2))}%`;
  if (key.includes("hours")) return `${value} hours`;
  if (key.includes("days")) return `${value} days`;
  return value.toLocaleString("en-US");
}
const sourceNames: Record<string,string> = {
  "SRC-FFIEC-G": "FFIEC BSA/AML Manual · Appendix G",
  "SRC-FINCEN-2014-A005": "FinCEN Advisory · FIN-2014-A005",
  "SRC-FINCEN-2010-A001": "FinCEN Advisory · FIN-2010-A001",
};
export function Policies() {
  const { data, error, loading } = useData("/policies");
  return <div className="page policy-page">
    <Heading title="Detection Policies" description="Understand what each alert looks for, when it is triggered and what to review." />
    <p className="policy-context">The thresholds below are configured for this demonstration. They are not regulatory requirements. An alert prompts investigation; it does not establish suspicious activity.</p>
    {error && <Message error>{error}</Message>}
    {loading && <p className="text-sm text-neutral-400">Loading policies…</p>}
    <div className="space-y-6">{data?.patterns?.map((r: any) => {
      const guide = policyGuides[r.pattern_id];
      return <article className="policy-card" key={r.pattern_id}>
        <header className="policy-header"><div><span className="policy-reference">{r.pattern_id}</span><h2>{titleCase(guide?.title ?? r.pattern_name)}</h2><p>{guide?.summary}</p></div><Badge tone="green">Enabled</Badge></header>
        <div className="policy-body">
          <section><h3>When an Alert Is Triggered</h3><p className="policy-trigger">{typeof r.detection_logic === "string" ? r.detection_logic : "Refer to the configured criteria below."}</p></section>
          <section><h3>Configured Criteria</h3><dl className="policy-criteria">{Object.entries(r.demo_thresholds ?? {}).filter(([key])=>key !== "threshold_type").map(([key,value])=><div key={key}><dt>{thresholdLabels[key] ?? human(key)}</dt><dd>{thresholdValue(key,value,r.pattern_id)}</dd></div>)}</dl></section>
          {guide && <section className="policy-review"><h3>What the Investigator Should Review</h3><p>{guide.review}</p></section>}
          {guide?.note && <p className="policy-note">{guide.note}</p>}
          <footer className="policy-sources"><span>Reference guidance</span>{r.source_refs?.map((ref: any)=><a key={ref.source_id} href={ref.url} target="_blank" rel="noreferrer">{sourceNames[ref.source_id] ?? ref.source_id}{ref.pages ? ` · pp. ${ref.pages}` : ""} ↗</a>)}</footer>
        </div>
      </article>;
    })}</div>
  </div>;
}
