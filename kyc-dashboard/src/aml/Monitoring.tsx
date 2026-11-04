import { useState } from "react";
import { Panel } from "../components/ui";
import { request, useData, usd, human } from "./client";
import { Heading, Message, Stats } from "./shared";

export default function Monitoring() {
  const { data: s, error, reload } = useData("/status", 5000),
    { data: rows } = useData<any[]>("/transactions?limit=100&scope=monitoring", 5000);
  const [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  async function action(path: string, body: unknown = {}) {
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
  const total = s?.live_total ?? 100;
  const done = s?.live_processed ?? 0;
  const processed = s?.transactions_processed ?? 0;
  const running = Boolean(s?.running);
  const liveReady = done > 0 || running;
  const storyActive = Boolean(s?.demo_story_active);
  const canReset = !running && (liveReady || storyActive);
  const finished = !running && total > 0 && done >= total;
  const progressValue = finished ? total : running ? done : done > 0 ? done : 0;
  return (
    <div className="page">
      <Heading
        title="Transaction Monitoring"
        description="Start streams transactions into monitoring. Investigations and Customers stay empty until the stream finishes. Reset clears everything again."
      />
      {(error || failure) && <Message error>{error || failure}</Message>}
      {s && (
        <>
          <Stats
            items={[
              ["Transactions processed", String(processed)],
              ["Alerts", s.alerts],
              ["Awaiting review", s.awaiting_review],
              ["Decisions", s.reviewed],
            ]}
          />
          <Panel title="Transaction stream">
            <p className="mb-4 text-sm text-neutral-400">
              Press Start to stream transactions. When the stream finishes, Customers and
              Investigations appear for review. Press Reset to clear and start over.
            </p>
            <div className="flex flex-wrap items-end gap-4">
              <button
                disabled={busy || running || liveReady}
                className="primary"
                onClick={() =>
                  action("/replay/start", {
                    events_per_second: 10,
                    auto_investigate: false,
                  })
                }
              >
                Start
              </button>
              <button
                disabled={busy || !running}
                className="secondary"
                onClick={() => action("/replay/pause", {})}
              >
                Pause
              </button>
              <button
                disabled={busy || !canReset}
                className="secondary"
                onClick={() => action("/replay/reset", {})}
              >
                Reset
              </button>
            </div>
            <progress
              className="mt-5 w-full accent-brand"
              value={progressValue}
              max={Math.max(total, 1)}
            />
            <p className="mt-2 text-xs text-neutral-400">
              {running
                ? "Streaming transactions"
                : finished
                  ? "Episode ready · press Reset before the next Start"
                  : storyActive && !done
                    ? "Customer activity is visible · press Reset to empty Investigations and Customers"
                    : done
                      ? "Paused · press Reset to clear, or wait if still streaming"
                      : "Ready · press Start"}{" "}
              · Event time {s.event_clock} UTC
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
