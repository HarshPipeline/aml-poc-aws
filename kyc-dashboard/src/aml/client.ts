import { useCallback, useEffect, useState } from "react";

export async function request<T = any>(
  path: string,
  body?: unknown,
  method?: string,
): Promise<T> {
  const res = await fetch(`/backend${path}`, {
    method: method ?? (body === undefined ? "GET" : "POST"),
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok)
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : JSON.stringify(data?.detail ?? `Request failed (${res.status})`),
    );
  return data as T;
}

export function useData<T = any>(path: string, interval = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  useEffect(() => {
    let active = true;
    let pending = false;
    setData(null);
    setLoading(true);
    setError("");
    const run = async () => {
      if (pending) return;
      pending = true;
      try {
        const result = await request<T>(path);
        if (active) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        pending = false;
        if (active) setLoading(false);
      }
    };
    void run();
    const timer = interval ? setInterval(run, interval) : undefined;
    return () => {
      active = false;
      if (timer) clearInterval(timer);
    };
  }, [path, interval, version]);
  return { data, error, loading, reload };
}
export const usd = (n: unknown) =>
  Number(n ?? 0).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
export const episodeWindow = (start?: string, end?: string) => {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const part = (iso: string) => {
    const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
    if (!year || !month || !day) return "";
    return { year, month, day, label: `${day} ${months[month - 1]} ${year}` };
  };
  if (!start || !end) return "";
  const from = part(start);
  const to = part(end);
  if (!from || !to) return "";
  if (from.year === to.year && from.month === to.month) return `${from.day}–${to.label}`;
  return `${from.label} – ${to.label}`;
};
export const documentsLabel = (status?: string) =>
  status === "received" ? "Documents received" : status === "requested" ? "Requested" : "Request documents";
const displayLabels: Record<string, string> = {
  not_started: "Not started", awaiting_review: "Awaiting review", reviewed: "Reviewed",
  request_info: "Request information", clear: "Close alert", escalate: "Escalate",
  kyc: "KYC", sar: "SAR", openai: "OpenAI", claude: "Claude", demo: "Demo",
  ach: "ACH", ach_in: "ACH credit", ach_out: "ACH debit",
};
export const human = (s: unknown) => {
  const raw = String(s ?? "—");
  if (displayLabels[raw.toLowerCase()]) return displayLabels[raw.toLowerCase()];
  const text = raw.replaceAll("_", " ").toLowerCase();
  return (text.charAt(0).toUpperCase() + text.slice(1))
    .replace(/\b(kyc|sar|ach|atm|pdf|api|utc)\b/gi, word => word.toUpperCase());
};
export const scenarios: Record<string, string> = {
  "TM-01": "Cash Structuring",
  "TM-03": "Funnel Account",
  "TM-04": "Rapid Movement of Funds",
  "TM-07": "Pass-Through Activity",
  "TM-08": "Unusual Activity Burst",
  "TM-09": "International Wires",
};
export const scenario = (ids: string[]) =>
  ids.map((id) => scenarios[id] ?? id).join(" / ");
export function download(
  name: string,
  value: string,
  type = "application/json",
) {
  const url = URL.createObjectURL(new Blob([value], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
