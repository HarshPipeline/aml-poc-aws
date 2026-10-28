import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Panel, Badge } from "../components/ui";
import CustomerKyc from "../pages/CustomerKyc";
import Evidence from "./Evidence";
import SummaryRun from "./SummaryRun";
import { request, useData, usd, human, scenario, download, episodeWindow, documentsLabel } from "./client";
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
    reload: refreshCase,
  } = useData(`/alerts/${alertId}/case`, 1000);
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
        ← Investigations
      </Link>
      <div className="mt-4">
        <Heading
          title={a?.customer_name ?? "Investigation"}
          description={
            a
              ? `${scenario(a.pattern_ids)} · ${a.episode_label ?? "Episode 1"}${episodeWindow(a.window_start, a.window_end) ? ` · ${episodeWindow(a.window_start, a.window_end)}` : ""}`
              : "Assess the customer profile and supporting evidence."
          }
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
              <p className="text-xs text-neutral-500">Alert reference</p>
              <p className="mt-1 text-sm text-neutral-400">
                {a.alert_id} · Customer {a.customer_id}
              </p>
            </div>
            <div className="flex gap-2">
              <Badge tone={a.priority === "high" ? "red" : a.priority === "medium" ? "amber" : "neutral"}>{human(a.priority)} priority</Badge>
              <Badge tone={a.documents_status === "received" ? "green" : a.documents_status === "requested" ? "amber" : "neutral"}>{documentsLabel(a.documents_status)}</Badge>
              {a.signal_status !== "confirmed" && <Badge>{human(a.signal_status)}</Badge>}
            </div>
          </div>
          <div className="mb-5 grid grid-cols-2 gap-4 rounded-xl border border-line bg-panel p-4 md:grid-cols-4">
            <div>
              <small>Episode amount</small>
              <p>{usd(a.amount)}</p>
            </div>
            <div>
              <small>Episode</small>
              <p>{a.episode_label ?? "Episode 1"}</p>
            </div>
            <div>
              <small>Transactions</small>
              <p>{a.transaction_ids.length}</p>
            </div>
            <div>
              <small>Investigation status</small>
              <p>{human(report?.status ?? "not_started")}</p>
            </div>
          </div>
          <nav
            className="mb-6 flex overflow-x-auto border-b border-line"
            aria-label="Investigation sections"
          >
            {tabs.filter(t => t !== "Activity").map((t) => (
              <button
                key={t}
                className={`shrink-0 border-b-2 px-4 py-3 text-sm ${tab === t ? "border-brand text-brand" : "border-transparent text-neutral-400"}`}
                onClick={() => setParams({ section: t })}
              >
                {({Overview: "Summary", "Customer KYC": "Customer", "Transactions & evidence": "Evidence", Documents: "Documents", Decision: "Decision"} as Record<string,string>)[t] ?? t}
              </button>
            ))}
          </nav>
          {tab === "Overview" && <SummaryRun key={alertId} alertId={alertId} report={report} stale={a.report_stale} onFinished={refreshCase} />}
          {tab === "Customer KYC" && (
            <CustomerKyc customerIdOverride={a.customer_id} />
          )}
          {tab === "Overview" && report && report.status !== "investigating" && !report.decision && !a.report_stale && (
            <div className="next-step"><div><strong>{report.completeness === "complete" ? `Suggested action: ${human(report.recommendation)}` : "Additional evidence required"}</strong><p>{report.completeness === "complete" ? "Read the summary, check the evidence, then record your decision." : (a.customer_ask ?? []).filter((item: {status: string}) => item.status !== "received").map((item: {title: string}) => item.title).join("; ") || "A recommendation requires additional evidence. Request the listed documents from the customer."}</p></div><button className="primary" onClick={() => setParams({section: report.completeness === "complete" ? "Decision" : "Documents"})}>{report.completeness === "complete" ? "Review decision" : (a.customer_ask ?? []).some((item: {status: string}) => item.status === "missing") ? "Request documents" : "Open documents"} →</button></div>
          )}
          {tab === "Overview" && report?.status !== "investigating" &&
            (report ? (
              <div className="grid gap-5 xl:grid-cols-3">
                <div className="space-y-4 xl:col-span-2">
                  <p className="text-sm leading-6 text-neutral-300">
                    {report.summary}
                  </p>
                  {(report.observed || report.next_step) && (
                    <Panel title="Verdict">
                      {report.observed && <p className="text-sm leading-6">{report.observed}</p>}
                      {report.next_step && (
                        <p className="mt-3 text-sm leading-6">
                          <strong>Suggested next step. </strong>
                          {report.next_step}
                        </p>
                      )}
                    </Panel>
                  )}
                  {(report.findings ?? []).map((f: any, i: number) => (
                    <Panel key={i} title={`Finding ${i + 1}`}>
                      <p className="text-sm leading-6">{f.text}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {(f.evidence_ids ?? []).map((id: string) => (
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
                  <Panel title="Alternative Explanation">
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
                  <details><summary>Report details</summary>
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
                  </details>
                  {report.missing?.length > 0 && (
                    <Panel title="Outstanding Evidence">
                      <ul className="list-inside list-disc text-sm text-brand-light">
                        {report.missing.map((m: string) => (
                          <li key={m}>{m}</li>
                        ))}
                      </ul>
                    </Panel>
                  )}
                  {report.critic?.defects?.length > 0 && (
                    <details><summary>Quality checks need attention</summary><Json value={report.critic.defects} /></details>
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
            <Evidence alert={a} report={report} selected={params.get("evidence")} />
          )}
          {tab === "Documents" && (
            <Documents alert={a} report={report} refresh={refresh} />
          )}
          {tab === "Decision" &&
            (report?.decision ? (
              <Panel title="Recorded Decision">
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
              <Panel title="Investigator Decision">
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
                        <option value="clear">Close alert</option>
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
                    Record decision
                  </button>
                </form>
              </Panel>
            ) : (
              <Message>
                Complete an investigation before recording a decision.
              </Message>
            ))}
          <div className="mb-5 mt-6"><button className="text-xs text-neutral-400 hover:text-brand" onClick={() => setParams({section: tab === "Activity" ? "Overview" : "Activity"})}>{tab === "Activity" ? "← Back to summary" : "Investigation history and options"}</button></div>
          {tab === "Activity" && (
            <div className="space-y-4">
              {(report?.steps ?? []).map((s: any, i: number) => (
                <Panel key={i} title={`${i + 1}. ${human(s.agent)}`}>
                  <p className="text-sm text-neutral-400">
                    {human(s.mode)} · {s.evidence_count} evidence entries ·{" "}
                    {s.finished_at}
                  </p>
                </Panel>
              ))}
              <details>
                <summary>Report controls and demo scenarios</summary>
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
  const { data: documents, error: documentError, reload: refreshDocuments } =
    useData<any[]>(`/alerts/${alert.alert_id}/documents`, 5000);
  const asks: {artifact_type: string; title: string; status: string}[] = alert.customer_ask ?? [];
  const outstanding = asks.filter((item) => item.status !== "received");
  async function run(fn: () => Promise<unknown>, done = "Document attached. Run the investigation from Summary to include the new evidence.") {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await fn();
      const note = result && typeof result === "object" && "note" in result ? String((result as {note?: string}).note || "") : "";
      setMessage(note || done);
      refreshDocuments();
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
      <Panel title="Requested from the customer">
        <p className="mb-4 text-sm text-neutral-400">
          This is the investigator workbench. The customer does not upload here.
          Record an RFI for anything still missing. Files already on the case were treated as customer submissions.
        </p>
        <ul className="coverage-list">
          {(asks.length ? asks : [{title: "No specific customer document is mapped to this alert.", status: "received", artifact_type: ""}]).map((item) => (
            <li key={item.title}>
              <span>{item.title}</span>
              <Badge tone={item.status === "received" ? "green" : item.status === "requested" ? "amber" : "neutral"}>
                {item.status === "received" ? "Received" : item.status === "requested" ? "Requested" : human(item.artifact_type) + " required"}
              </Badge>
            </li>
          ))}
        </ul>
        {outstanding.length > 0 && (
          <button
            className="primary mt-4"
            disabled={busy || outstanding.every((item) => item.status === "requested")}
            onClick={() =>
              void run(
                () => request(`/alerts/${alert.alert_id}/request-documents`, {}),
                "Request recorded on the case.",
              )
            }
          >
            {outstanding.every((item) => item.status === "requested") ? "Request already recorded" : "Request documents from customer"}
          </button>
        )}
      </Panel>
      <Panel title="Customer submissions">
        {documentError && <Message error>{documentError}</Message>}
        {!documents?.filter((doc: any) => doc.submitted_by === "customer").length && !documentError && (
          <p className="text-sm text-neutral-400">The customer has not submitted documents for this alert.</p>
        )}
        <div className="space-y-4">
          {(documents ?? []).filter((doc: any) => doc.submitted_by === "customer").map((doc: any) => (
            <article key={doc.document_id} className="rounded-lg border border-neutral-800 p-4">
              <div className="flex items-start justify-between gap-3">
                <div><h3 className="font-medium">{doc.title}</h3><p className="mt-1 text-xs text-neutral-500">{doc.document_id} · {human(doc.artifact_type || "document")}</p></div>
                <Badge tone={doc.readable ? "green" : "amber"}>{doc.readable ? "Received from customer" : "Needs Transcription"}</Badge>
              </div>
              <p className="mt-3 text-sm text-neutral-400">Policy coverage: {doc.evidence_types.join(" · ")}</p>
              {doc.viewable && <p className="mt-3"><a className="secondary" href={`/backend/documents/${doc.document_id}/file`} target="_blank" rel="noreferrer">View document</a></p>}
              <details className="mt-3"><summary>View extracted text</summary><div className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap text-sm leading-6">{doc.content}</div></details>
            </article>
          ))}
        </div>
      </Panel>
      <details>
        <summary>Attach a document already received (mailroom)</summary>
        <div className="mt-4 space-y-4">
      <Panel title="Supporting Documents">
        <p className="mb-4 text-sm text-neutral-400">
          Use this only when a file arrived outside the customer portal. Extraction
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
            Maximum 5 MB. Typed PDFs use pypdf. PNG/JPEG use Claude or OpenAI.
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
      <Panel title="Other attached documents">
        {documentError && <Message error>{documentError}</Message>}
        {!(documents ?? []).filter((doc: any) => doc.submitted_by !== "customer").length && !documentError && (
          <p className="text-sm text-neutral-400">No investigator or mailroom files on this investigation.</p>
        )}
        <div className="space-y-4">
          {(documents ?? []).filter((doc: any) => doc.submitted_by !== "customer").map((doc: any) => (
            <article key={doc.document_id} className="rounded-lg border border-neutral-800 p-4">
              <div className="flex items-start justify-between gap-3">
                <div><h3 className="font-medium">{doc.title}</h3><p className="mt-1 text-xs text-neutral-500">{doc.document_id}</p></div>
                <Badge tone={doc.readable ? "green" : "amber"}>{doc.readable ? "Text Extracted" : "Needs Transcription"}</Badge>
              </div>
              <p className="mt-3 text-sm text-neutral-400">Evidence categories: {doc.evidence_types.join(" · ")}</p>
              {doc.viewable && <p className="mt-3"><a className="secondary" href={`/backend/documents/${doc.document_id}/file`} target="_blank" rel="noreferrer">View document</a></p>}
              <details className="mt-3"><summary>View Extracted Text</summary><div className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap text-sm leading-6">{doc.content}</div></details>
            </article>
          ))}
        </div>
      </Panel>
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
      </details>
    </div>
  );
}
