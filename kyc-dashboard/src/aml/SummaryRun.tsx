import { titleCase } from "../utils/titleCase";
import { useEffect, useRef, useState } from "react";
import { Check, LoaderCircle, Sparkles, AlertCircle, Search, X, FileCheck2 } from "lucide-react";
import { request, useData } from "./client";
const stages = [
  ["orchestrator", "Collecting evidence", "Gathering the flagged activity and setting the investigation scope."],
  ["kyc", "Checking customer details", "Reviewing KYC, business activity and the expected account behavior."],
  ["transaction", "Examining transactions", "Tracing the payments and checking the counterparty records."],
  ["document", "Checking supporting documents", "Identifying available documents and outstanding evidence."],
  ["policy", "Checking policy criteria", "Comparing the activity with detection rules and advisory references."],
  ["investigation", "Assessing the evidence", "Evaluating the findings and potential legitimate explanations."],
  ["report", "Preparing the assessment", "Organizing the findings and their evidence references."],
  ["critic", "Validating the report", "Checking citations, consistency and evidence completeness."],
] as const;
export default function SummaryRun({alertId, report, stale, onFinished}: {alertId:string;report:any;stale:boolean;onFinished:()=>void}) {
  const {data:system} = useData("/status");
  const dialog = useRef<HTMLDialogElement>(null);
  const [expanded,setExpanded] = useState(false);
  const [pending,setPending] = useState(false);
  const [previous,setPrevious] = useState<string|null>(null);
  const [result,setResult] = useState<any>(null);
  const [failure,setFailure] = useState("");
  const [playback,setPlayback] = useState<number|null>(null);
  const completedRun = result && (!report || result.case_id === report.case_id) ? result : report;
  const current = pending && report?.case_id === previous ? null : completedRun;
  const running = pending || current?.status === "investigating";
  const recorded = new Set<string>((current?.steps ?? []).map((s:any)=>s.agent));
  const errors = new Set<string>((current?.errors ?? []).map((s:any)=>s.agent));
  const playbackStages = stages.filter(([id])=>recorded.has(id));
  const currentId = playback !== null ? playbackStages[playback]?.[0] : running ? current?.active_agent ?? "orchestrator" : null;
  const active = stages.find(s=>s[0]===currentId);
  useEffect(()=>{
    if(playback===null) return;
    const timer=setTimeout(()=>setPlayback(playback+1>=playbackStages.length ? null : playback+1),1600);
    return ()=>clearTimeout(timer);
  },[playback,playbackStages.length]);
  useEffect(()=>{
    if(expanded && !dialog.current?.open) dialog.current?.showModal();
    if(!expanded && dialog.current?.open) dialog.current?.close();
  },[expanded]);
  async function start() {
    setExpanded(true);
    setPrevious(report?.case_id ?? null);setPending(true);setResult(null);setFailure("");setPlayback(null);
    const started=Date.now();
    try {
      const next=await request(`/alerts/${alertId}/investigate`,{force:!!report});
      setResult(next);
      // Fast runs show an explicitly labeled playback of recorded steps, never fabricated live progress.
      if(Date.now()-started<2000 && next.steps?.length) setPlayback(0);
      onFinished();
    } catch(e) {setFailure((e as Error).message);onFinished();}
    finally {setPending(false);}
  }
  const showingProgress=running || playback!==null;
  return <section className={`summary-run ${showingProgress ? "summary-run-active" : ""}`}>
    <div className="summary-run-top"><div><span className="summary-run-kicker"><Sparkles size={14}/> Investigation assistant</span><h2>{titleCase(showingProgress ? active?.[1] ?? "Starting investigation" : "Run an evidence-based investigation")}</h2><p>{showingProgress ? active?.[2] : "Collect evidence, check the activity and prepare an assessment for your review."}</p></div>
      <button className="primary" disabled={!system || showingProgress} onClick={start}>{showingProgress ? <><LoaderCircle size={16} className="run-spin"/>{playback!==null ? "Showing completed steps" : "Investigating…"}</> : <><Sparkles size={16}/> Run AI investigation</>}</button>
    </div>
    {system?.mode !== "openai" && <p className="summary-run-mode">{system ? "Demo preview · This run uses deterministic results, not a live AI model." : "Checking investigation mode…"}</p>}
    {stale && !showingProgress && <p className="mt-3 text-sm text-amber-300">Evidence has changed. Run a new investigation to update the assessment.</p>}
    {failure && <p role="alert" className="mt-4 text-sm text-red-300">{failure} The server may still be processing; check the case status before retrying.</p>}
    {showingProgress && !expanded && <button className="run-skip" onClick={()=>setExpanded(true)}>View investigation progress →</button>}
    <dialog ref={dialog} className="investigation-cinema" onCancel={()=>setExpanded(false)} aria-labelledby="cinema-title">
      <header className="cinema-header"><span><Sparkles size={15}/> AML OPERATIONS <span className="cinema-separator">/</span> INVESTIGATION</span><button onClick={()=>setExpanded(false)} aria-label="Minimize investigation progress"><X size={19}/></button></header>
      <div className="cinema-context"><span>{current?.alert?.customer_id ?? "Customer investigation"}</span><span>{alertId}</span></div>
      <div className="cinema-grid"><div className="cinema-main">
        <div className={`cinema-radar ${showingProgress ? "is-scanning" : "is-finished"}`} aria-hidden="true"><div className="radar-ring ring-one"/><div className="radar-ring ring-two"/><div className="radar-ring ring-three"/>{showingProgress && <><div className="radar-sweep"/><i className="radar-dot dot-one"/><i className="radar-dot dot-two"/><i className="radar-dot dot-three"/></>}<div className="radar-core">{showingProgress ? <Search size={34} strokeWidth={1.4}/> : failure ? <AlertCircle size={34}/> : <FileCheck2 size={34} strokeWidth={1.4}/>}</div></div>
        <span className="cinema-phase">{showingProgress ? playback!==null ? "RECORDED RUN · STEP PLAYBACK" : "INVESTIGATION IN PROGRESS" : failure ? "INVESTIGATION INTERRUPTED" : "INVESTIGATION FINISHED"}</span>
        <div key={currentId ?? "finished"} className="cinema-stage" role="status" aria-live="polite"><h2 id="cinema-title">{titleCase(showingProgress ? active?.[1] ?? "Preparing your investigation" : failure ? "Unable to finish the request" : "Your assessment is ready")}</h2><p>{showingProgress ? active?.[2] : failure ? failure : current?.completeness === "complete" ? "The findings and supporting evidence are ready for your review." : "The checks are finished. Review the outstanding evidence and quality items in the assessment."}</p></div>
        <div className="cinema-progress-meta"><span>{playback!==null ? "Recorded steps shown" : "Steps recorded"}</span><strong>{playback!==null ? playback : recorded.size} / {stages.length}</strong></div>
        <progress className="cinema-progress" aria-label={playback!==null ? "Recorded steps shown" : "Investigation steps recorded"} value={playback!==null ? playback : recorded.size} max={stages.length}/>
        <div className="cinema-facts"><span><strong>{current?.evidence?.length ?? 0}</strong> evidence records</span><span><strong>{current?.missing?.length ?? 0}</strong> outstanding items</span></div>
      </div><aside className="cinema-checks"><h3>Investigation Stages</h3><ol>{stages.map(([id,title],index)=>{
        const isActive=id===currentId;
        const done=recorded.has(id) && !isActive && (playback===null || playbackStages.findIndex(s=>s[0]===id)<playback);
        return <li key={id} className={isActive ? "is-active" : done ? "is-done" : ""} aria-current={isActive ? "step" : undefined}><span className="run-node">{isActive ? <LoaderCircle size={15} className="run-spin"/> : done ? errors.has(id) ? <AlertCircle size={15}/> : <Check size={15}/> : index+1}</span><div><span>{titleCase(title)}</span><small>{isActive ? playback!==null ? "Showing recorded step" : "In progress" : done ? errors.has(id) ? "Needs attention" : "Completed" : playback!==null ? "Recorded · up next" : "Pending"}</small></div></li>;
      })}</ol></aside></div>
      <footer className="cinema-footer">{system?.mode !== "openai" && <p>Demo preview · No live AI model is being called</p>}{showingProgress ? playback!==null ? <button className="primary" onClick={()=>{setPlayback(null);setExpanded(false);}}>Open assessment →</button> : <button className="secondary" onClick={()=>setExpanded(false)}>Continue reviewing customer</button> : <button className="primary" onClick={()=>setExpanded(false)}>{failure ? "Return to summary" : "View assessment →"}</button>}</footer>
    </dialog>
    {!showingProgress && result && <p role="status" className="run-finished"><Check size={16}/> {result.completeness === "complete" ? "Assessment ready. Review the findings below." : "Investigation finished. Additional evidence or quality review is required; see the assessment below."}</p>}
  </section>;
}
