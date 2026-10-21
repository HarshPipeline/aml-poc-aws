import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Panel, Badge } from "../components/ui";
import CustomerKyc from "../pages/CustomerKyc";
import { request, useData, usd, human, scenario, download } from "./client";
import { Heading, Message, Facts, Json } from "./shared";

export default function Investigation() {
  const { alertId = "" } = useParams(),
    [params, setParams] = useSearchParams();
  const tab = params.get("section") ?? "Overview";
  const {
    data: alerts,
    error,
    reload: refreshAlert,
  } = useData<any[]>("/alerts", 5000);
  const a = alerts?.find((row) => row.alert_id === alertId);
  const {
    data: report,
    error: caseError,
    loading,
    reload: refreshCase,
  } = useData(`/alerts/${alertId}/case`);
  const [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const [name, setName] = useState(""),
    [reason, setReason] = useState(""),
    [action, setAction] = useState("request_info"),
    [sar, setSar] = useState("");
  useEffect(() => {
    setAction(report?.recommendation ?? "request_info");
    setSar(report?.sar_draft ?? "");
    setReason("");
    setName("");
  }, [report?.case_id, report?.recommendation, report?.sar_draft]);
  useEffect(() => {
    setFailure("");
  }, [alertId, tab]);
  const refresh = () => {
    refreshAlert();
    refreshCase();
  };
  async function investigate(force = false, failure = "none") {
    setBusy(true);
    setFailure("");
    try {
      await request(`/alerts/${alertId}/investigate`, { force, failure });
      refresh();
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function decide(e: React.SubmitEvent) {
    e.preventDefault();
    setBusy(true);
    setFailure("");
    try {
      await request(`/alerts/${alertId}/review`, {
        case_id: report.case_id,
        action,
        investigator: name.trim(),
        reason: reason.trim(),
        sar_narrative: sar || null,
      });
      refresh();
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const tabs = [
    "Overview",
    "Customer KYC",
    "Transactions & evidence",
    "Documents",
    "Decision",
    "Activity",
  ];
  return (
    <div className="page">
      <Link className="text-xs text-neutral-500 hover:text-brand" to="/alerts">
        ← Alert queue
      </Link>
      <div className="mt-4">
        <Heading
          title="Case investigation"
          description="Review the customer and evidence, then record an investigator decision."
        />
      </div>
      {(error || caseError || failure) && (
        <Message error>{error || caseError || failure}</Message>
      )}
      {!a && !error && <Message>{alerts ? "Alert not found. Return to the alert queue." : "Loading investigation…"}</Message>}
      {a && (
        <>
          <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-xl font-bold">{a.customer_name}</h2>
              <p className="mt-1 text-sm text-neutral-400">
                {a.customer_id} · {scenario(a.pattern_ids)} · {a.alert_id}
              </p>
            </div>
            <div className="flex gap-2">
              <Badge tone={a.priority === "high" ? "red" : a.priority === "medium" ? "amber" : "neutral"}>{a.priority} priority</Badge>
              <Badge>{a.signal_status}</Badge>
            </div>
          </div>
          <div className="mb-5 grid grid-cols-3 gap-4 rounded-xl border border-line bg-panel p-4">
            <div>
              <small>Evidence value</small>
              <p>{usd(a.amount)}</p>
            </div>
            <div>
              <small>Transactions</small>
              <p>{a.transaction_ids.length}</p>
            </div>
            <div>
              <small>Workflow</small>
              <p>{human(report?.status ?? "not_started")}</p>
            </div>
          </div>
          {!loading && (!report || a.report_stale) && (
            <div className="mb-5">
              <button
                className="primary"
                disabled={busy}
                onClick={() => investigate()}
              >
                {busy
                  ? "Investigating…"
                  : report
                    ? "Update investigation"
                    : "Start investigation"}
              </button>
              {a.report_stale && (
                <p className="mt-2 text-sm text-brand">
                  Evidence changed. Update the report before recording a
                  decision.
                </p>
              )}
            </div>
          )}
          {busy && (
            <Message>Processing your request. This may take a moment…</Message>
          )}
          <nav
            className="mb-6 flex overflow-x-auto border-b border-line"
            aria-label="Investigation sections"
          >
            {tabs.map((t) => (
              <button
                key={t}
                className={`shrink-0 border-b-2 px-4 py-3 text-sm ${tab === t ? "border-brand text-brand" : "border-transparent text-neutral-400"}`}
                onClick={() => setParams({ section: t })}
              >
                {t}
              </button>
            ))}
          </nav>
          {tab === "Customer KYC" && (
            <CustomerKyc customerIdOverride={a.customer_id} />
          )}
          {tab === "Overview" &&
            (report ? (
              <div className="grid gap-5 xl:grid-cols-3">
                <div className="space-y-4 xl:col-span-2">
                  <Message>
                    {report.completeness === "complete"
                      ? `Suggested action: ${human(report.recommendation)}. Review the evidence before recording a decision.`
                      : "Incomplete assessment. Review the missing evidence; no recommendation has been made."}
                  </Message>
                  <p className="text-sm leading-6 text-neutral-300">
                    {report.summary}
                  </p>
                  {(report.findings ?? []).map((f: any, i: number) => (
                    <Panel key={i} title={`Finding ${i + 1}`}>
                      <p className="text-sm leading-6">{f.text}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {f.evidence_ids.map((id: string) => (
                          <button
                            key={id}
                            onClick={() =>
                              setParams({
                                section: "Transactions & evidence",
                                evidence: id,
                              })
                            }
                          >
                            <Badge tone="brand">{id}</Badge>
                          </button>
                        ))}
                      </div>
                    </Panel>
                  ))}
                  <Panel title="Alternative explanation">
                    <p className="text-sm leading-6">
                      {report.innocent_explanation ?? "Not available"}
                    </p>
                  </Panel>
                  <button
                    className="secondary"
                    onClick={() =>
                      download(
                        `${report.case_id}.md`,
                        report.report ?? "",
                        "text/markdown",
                      )
                    }
                  >
                    Download report
                  </button>
                </div>
                <div className="space-y-5">
                  <Facts
                    title="Review readiness"
                    items={[
                      ["Report", human(report.completeness)],
                      ["Evidence records", report.evidence?.length ?? 0],
                      ["Outstanding items", report.missing?.length ?? 0],
                      [
                        "Quality checks",
                        report.critic?.passed ? "Passed" : "Attention required",
                      ],
                      ["Decision", report.decision ? "Recorded" : "Pending"],
                    ]}
                  />
                  <Facts
                    title="Customer context"
                    items={[
                      ["Type", human(report.profile?.customer_type)],
                      [
                        "Occupation",
                        report.profile?.occupation_or_industry ?? "Unavailable",
                      ],
                      [
                        "Risk rating",
                        report.profile?.risk_rating ?? "Unavailable",
                      ],
                    ]}
                  />
                  {report.missing?.length > 0 && (
                    <Panel title="Outstanding evidence">
                      <ul className="list-inside list-disc text-sm text-brand-light">
                        {report.missing.map((m: string) => (
                          <li key={m}>{m}</li>
                        ))}
                      </ul>
                    </Panel>
                  )}
                  {report.critic?.defects?.length > 0 && (
                    <Panel title="Quality exceptions">
                      <Json value={report.critic.defects} />
                    </Panel>
                  )}
                </div>
              </div>
            ) : (
              <Message>
                Start the investigation to prepare the customer assessment and
                supporting evidence.
              </Message>
            ))}
          {tab === "Transactions & evidence" && (
            <div className="space-y-4">
              <details>
                <summary>Scenario calculations and thresholds</summary>
                <Json value={a.metrics} />
              </details>
              {(report?.evidence ?? []).map((item: any) => (
                <details
                  key={item.id}
                  open={params.get("evidence") === item.id}
                >
                  <summary>
                    {item.id} · {human(item.kind)} · {item.title}
                  </summary>
                  <p className="my-2 text-xs text-neutral-500">{item.source}</p>
                  {Array.isArray(item.value) &&
                  item.value[0]?.transaction_id ? (
                    <div className="table-panel">
                      <table>
                        <thead>
                          <tr>
                            {[
                              "Transaction",
                              "Time",
                              "Type",
                              "Direction",
                              "Amount",
                            ].map((h) => (
                              <th key={h}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {item.value.map((r: any) => (
                            <tr key={r.transaction_id}>
                              <td>{r.transaction_id}</td>
                              <td>{r.txn_ts}</td>
                              <td>{human(r.txn_type)}</td>
                              <td>{r.direction}</td>
                              <td>{usd(r.amount)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Json value={item.value} />
                  )}
                </details>
              ))}
            </div>
          )}
          {tab === "Documents" && (
            <Documents alert={a} report={report} refresh={refresh} />
          )}
          {tab === "Decision" &&
            (report?.decision ? (
              <Panel title="Recorded decision">
                <Badge tone="green">{human(report.decision.action)}</Badge>
                <p className="mt-4">{report.decision.reason}</p>
                <p className="mt-2 text-sm text-neutral-400">
                  Reviewed by {report.decision.investigator}
                </p>
                {report.sar_narrative && (
                  <p className="mt-4 whitespace-pre-wrap">
                    {report.sar_narrative}
                  </p>
                )}
              </Panel>
            ) : report?.status === "awaiting_review" ? (
              <Panel title="Investigator decision">
                <form onSubmit={decide} className="space-y-5">
                  <div className="grid gap-4 md:grid-cols-2">
                    <label>
                      Investigator name
                      <input
                        required
                        minLength={2}
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                      />
                    </label>
                    <label>
                      Disposition
                      <select
                        value={action}
                        onChange={(e) => setAction(e.target.value)}
                      >
                        <option value="clear">Clear / close</option>
                        <option value="request_info">
                          Request information
                        </option>
                        <option value="escalate">
                          Escalate for further review
                        </option>
                      </select>
                    </label>
                  </div>
                  <label>
                    Decision rationale
                    <textarea
                      required
                      minLength={5}
                      rows={5}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </label>
                  {action === "escalate" && (
                    <label>
                      SAR narrative draft
                      <textarea
                        rows={8}
                        value={sar}
                        onChange={(e) => setSar(e.target.value)}
                      />
                    </label>
                  )}
                  <p className="text-xs text-neutral-500">
                    Records an attributed decision. SAR drafts are not filed
                    automatically.
                  </p>
                  <button
                    className="primary"
                    disabled={
                      busy ||
                      a.report_stale ||
                      name.trim().length < 2 ||
                      reason.trim().length < 5
                    }
                  >
                    Record investigator decision
                  </button>
                </form>
              </Panel>
            ) : (
              <Message>
                Complete an investigation before recording a decision.
              </Message>
            ))}
          {tab === "Activity" && (
            <div className="space-y-4">
              {(report?.steps ?? []).map((s: any, i: number) => (
                <Panel key={i} title={`${i + 1}. ${human(s.agent)}`}>
                  <p className="text-sm text-neutral-400">
                    {s.mode} · {s.evidence_count} evidence entries ·{" "}
                    {s.finished_at}
                  </p>
                </Panel>
              ))}
              <details>
                <summary>Report controls & demonstration scenarios</summary>
                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    disabled={busy}
                    className="secondary"
                    onClick={() => investigate(true)}
                  >
                    Regenerate report
                  </button>
                  {[
                    "missing_document",
                    "missing_profile",
                    "transaction_unavailable",
                    "unreadable_document",
                    "policy_conflict",
                  ].map((f) => (
                    <button
                      key={f}
                      className="secondary"
                      disabled={busy}
                      onClick={() => investigate(true, f)}
                    >
                      {human(f)}
                    </button>
                  ))}
                </div>
              </details>
              {report && (
                <button
                  className="secondary"
                  onClick={() =>
                    download(
                      `${report.case_id}.json`,
                      JSON.stringify(report, null, 2),
                    )
                  }
                >
                  Export case record
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Documents({
  alert,
  report,
  refresh,
}: {
  alert: any;
  report: any;
  refresh: () => void;
}) {
  const [file, setFile] = useState<File | null>(null),
    [coverage, setCoverage] = useState<string[]>([]),
    [title, setTitle] = useState(""),
    [content, setContent] = useState(""),
    [readable, setReadable] = useState(true),
    [confidence, setConfidence] = useState(1),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [error, setError] = useState("");
  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await fn();
      setMessage("Evidence attached. Update the investigation to include it.");
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function upload(e: React.SubmitEvent) {
    e.preventDefault();
    if (!file || !coverage.length) return;
    await run(async () => {
      const form = new FormData();
      form.append("file", file);
      form.append("alert_id", alert.alert_id);
      form.append("evidence_types", JSON.stringify(coverage));
      const r = await fetch("/backend/documents/extract", {
        method: "POST",
        body: form,
      });
      const d = await r.json();
      if (!r.ok)
        throw new Error(
          typeof d.detail === "string" ? d.detail : "Extraction failed",
        );
    });
  }
  return (
    <div className="space-y-5">
      {message && <Message>{message}</Message>}
      {error && <Message error>{error}</Message>}
      <Panel title="Supporting documents">
        <p className="mb-4 text-sm text-neutral-400">
          Choose the evidence requirements supported by the document. Extraction
          does not establish authenticity.
        </p>
        <fieldset className="mb-5 grid gap-2 md:grid-cols-2">
          <legend className="mb-2 text-xs text-neutral-500">
            Evidence requirements
          </legend>
          {alert.evidence_required.map((r: string) => (
            <label key={r} className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={coverage.includes(r)}
                onChange={(e) =>
                  setCoverage((c) =>
                    e.target.checked ? [...c, r] : c.filter((x) => x !== r),
                  )
                }
              />
              {r}
            </label>
          ))}
        </fieldset>
        <form onSubmit={upload} className="space-y-3">
          <label>
            Upload PDF, text, or image
            <input
              type="file"
              accept=".pdf,.txt,.png,.jpg,.jpeg,.webp"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <p className="text-xs text-neutral-500">
            Maximum 5 MB. Scanned PDFs require OCR or a verified transcription.
          </p>
          <button
            disabled={busy || !file || !coverage.length}
            className="primary"
          >
            {busy ? "Extracting…" : "Extract and attach"}
          </button>
        </form>
      </Panel>
      <details>
        <summary>Enter document text manually</summary>
        <form
          className="mt-4 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run(() =>
              request("/documents", {
                document_id: `DOC-${crypto.randomUUID()}`,
                customer_id: alert.customer_id,
                title,
                content,
                evidence_types: coverage,
                transaction_ids: alert.transaction_ids,
                readable,
                extraction_confidence: confidence,
              }),
            );
          }}
        >
          <label>
            Document title
            <input
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label>
            Document text
            <textarea
              required
              rows={6}
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
          </label>
          <label className="flex gap-2">
            <input
              type="checkbox"
              checked={readable}
              onChange={(e) => setReadable(e.target.checked)}
            />
            Document is readable
          </label>
          <label>
            Extraction confidence
            <input
              type="number"
              min="0"
              max="1"
              step="0.05"
              value={confidence}
              onChange={(e) => setConfidence(Number(e.target.value))}
            />
          </label>
          <button className="primary" disabled={busy || !coverage.length}>
            Attach evidence
          </button>
        </form>
      </details>
      {(report?.evidence ?? [])
        .filter((e: any) => String(e.kind).includes("document"))
        .map((d: any) => (
          <details key={d.id}>
            <summary>
              {d.id} · {d.title}
            </summary>
            <Json value={d.value} />
          </details>
        ))}
      <details>
        <summary>Demonstration evidence</summary>
        <div className="mt-4 flex gap-3">
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              run(() => request(`/alerts/${alert.alert_id}/demo-packet`, {}))
            }
          >
            Attach synthetic packet
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              run(() =>
                request(
                  `/alerts/${alert.alert_id}/demo-packet?resolution=documented_legitimate`,
                  {},
                ),
              )
            }
          >
            Attach legitimate-explanation fixture
          </button>
        </div>
      </details>
    </div>
  );
}
