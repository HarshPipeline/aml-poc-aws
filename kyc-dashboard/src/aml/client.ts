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
export const human = (s: unknown) => String(s ?? "—").replaceAll("_", " ");
export const scenarios: Record<string, string> = {
  "TM-01": "Cash structuring",
  "TM-03": "Funnel account",
  "TM-04": "Rapid movement of funds",
  "TM-07": "Pass-through activity",
  "TM-08": "Unusual activity burst",
  "TM-09": "International wires",
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
