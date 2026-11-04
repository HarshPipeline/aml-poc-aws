# AML Demo — three customers

For team / Pruthvi review · updated Nov 2026

**In one sentence**
AML looks newly launched: Investigations and Customers stay empty while Monitoring **Start** streams. When Start **finishes**, three customers appear across three patterns. **Reset** empties everything again.

---

## What the client sees

### Before Start / while streaming
Investigations empty · Customers empty

### After Start finishes
| Customer | Pattern | Investigations |
|---|---|---|
| **Sunnyvale Corner Quick Stop** | Cash structuring (TM-01) | Episode 1 open · Request documents · on hold |
| **Casa Brisa Kitchen** | Funnel (TM-03) | Episodes 1–2 Reviewed · Episode 3 Awaiting (live) · on hold |
| **Priya Anand-Sorensen** | Pass-through (TM-07) | Episode 1 Reviewed · Episode 2 Awaiting (live) · on hold |

Episode labels are `Episode 1`, `Episode 2`, `Episode 3` only — never “of N”.

### Monitoring
- **Start** — streams ~100 transactions (Sunnyvale structuring + Casa + Priya patterns and filler); story reveals only when the stream completes
- **Transactions processed** — counts that stream (0 → 100)
- **Pause** — stop mid-stream (queue stays empty until a full Start completes)
- **Reset** — clear streamed demo rows and hide the story again

---

## Documents vs the real decision

- Human requests documents and records the final decision
- Mailroom uploads count as customer submissions
- Agent does not auto-ask or auto-decide

---

## Meeting flow

1. Investigations and Customers are empty
2. Monitoring → **Start** (watch payments stream; queue still empty)
3. When Start finishes → three customers + reviewed history + two open live episodes
4. Investigator may request docs, upload PDF/PNG, run AI, record decision
5. **Reset**, then **Start** to repeat

---

## Backup

RDS insert/reset SQL for `TXN-LIVE-*` remains available if needed. Story reveals once the full ~100-transaction Start stream finishes.
