import { useState } from "react";
import { Panel } from "../components/ui";
import { request, useData, usd, human } from "./client";
import { Heading, Message, Stats } from "./shared";
export default function Monitoring() {
  const { data: s, error, reload } = useData("/status", 2000),
    { data: rows } = useData<any[]>("/transactions?limit=30", 2000);
  const [rate, setRate] = useState(50),
    [auto, setAuto] = useState(true),
    [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  async function action(path: string, body: unknown) {
    setBusy(true);
    setFailure("");
    try {
      await request(path, body);
      reload();
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <Heading
        title="Transaction Monitoring"
        description="Review incoming transactions, alert volumes and monitoring status."
      />
      {(error || failure) && <Message error>{error || failure}</Message>}
      {s && (
        <>
          <Stats
            items={[
              ["Transactions processed", `${s.stream_processed} / ${s.stream_total}`],
              ["Alerts", s.stream_alerts],
              ["Awaiting review", s.awaiting_review],
              ["Decisions", s.reviewed],
            ]}
          />
          <Panel title="Transaction Replay">
            <div className="flex flex-wrap items-end gap-4">
              <label>
                Events per second
                <select
                  value={rate}
                  onChange={(e) => setRate(Number(e.target.value))}
                >
                  {[5, 20, 50, 100, 250].map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2 pb-3">
                <input
                  type="checkbox"
                  checked={auto}
                  onChange={(e) => setAuto(e.target.checked)}
                />
                Prepare assessments after replay
              </label>
              <button
                disabled={
                  busy || s.running || s.stream_processed === s.stream_total
                }
                className="primary"
                onClick={() =>
                  action("/replay/start", {
                    events_per_second: rate,
                    auto_investigate: auto,
                  })
                }
              >
                Start / resume
              </button>
              <button
                disabled={busy || !s.running}
                className="secondary"
                onClick={() => action("/replay/pause", {})}
              >
                Pause
              </button>
            </div>
            <progress
              className="mt-5 w-full accent-brand"
              value={s.stream_processed}
              max={s.stream_total || 1}
            />
            <p className="mt-2 text-xs text-neutral-400">
              {s.running
                ? "Running"
                : s.stream_processed === s.stream_total
                  ? "Finished"
                  : "Ready / paused"}{" "}
              · Event time {s.event_clock} UTC · {human(s.mode)}
            </p>
            {s.error && <Message error>{s.error}</Message>}
          </Panel>
        </>
      )}
      <div className="table-panel mt-6">
        <table>
          <thead>
            <tr>
              {["Time (UTC)", "Customer", "Type", "Direction", "Amount"].map(
                (h) => (
                  <th key={h}>{h}</th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {(rows ?? []).map((r) => (
              <tr key={r.transaction_id}>
                <td>{r.txn_ts.replace("T", " ")}</td>
                <td>{r.customer_id}</td>
                <td>{human(r.txn_type)}</td>
                <td>{r.direction}</td>
                <td>{usd(r.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
