import type { ReactNode } from "react";
import { Panel } from "../components/ui";
export function Heading({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <header className="mb-6">
      <h1 className="text-2xl font-bold">{title}</h1>
      <p className="mt-1 text-sm text-neutral-400">{description}</p>
    </header>
  );
}
export function Message({
  children,
  error = false,
}: {
  children: ReactNode;
  error?: boolean;
}) {
  return (
    <div
      role={error ? "alert" : "status"}
      className={`mb-4 rounded-xl border p-4 text-sm ${error ? "border-red-500/40 bg-red-500/5 text-red-300" : "border-brand/40 bg-brand/5 text-brand-light"}`}
    >
      {children}
    </div>
  );
}
export function Stats({ items }: { items: [string, string | number][] }) {
  return (
    <div className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
      {items.map(([k, v]) => (
        <div key={k} className="rounded-xl border border-line bg-panel p-5">
          <p className="text-xs uppercase tracking-wider text-neutral-400">
            {k}
          </p>
          <p className="mt-3 text-3xl font-bold text-brand">{v}</p>
        </div>
      ))}
    </div>
  );
}
export function Facts({
  title,
  items,
}: {
  title: string;
  items: [string, ReactNode][];
}) {
  return (
    <Panel title={title}>
      <dl className="space-y-3">
        {items.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs uppercase tracking-wider text-neutral-500">
              {k}
            </dt>
            <dd className="mt-1 break-words text-sm">{v}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}
export function Json({ value }: { value: unknown }) {
  return (
    <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-black/30 p-3 text-xs text-neutral-300">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
