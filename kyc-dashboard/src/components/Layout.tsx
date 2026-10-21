import {
  Activity,
  ClipboardList,
  FileCheck2,
  ShieldCheck,
  Users,
  ScrollText,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useData } from "../aml/client";
const links = [
  ["/alerts", "Alert queue", ClipboardList],
  ["/kyc", "Customer KYC", Users],
  ["/monitoring", "Monitoring", Activity],
  ["/audit", "Audit trail", ScrollText],
  ["/policies", "Detection policies", FileCheck2],
] as const;
export default function Layout() {
  const { data: s, error } = useData("/status", 10000);
  return (
    <div className="flex h-full flex-col md:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-line bg-black md:w-64 md:border-r md:border-b-0">
        <div className="flex items-center gap-2 px-5 py-5">
          <ShieldCheck className="h-6 w-6 text-brand" />
          <span className="text-lg font-bold">AML Operations</span>
        </div>
        <nav className="flex gap-1 overflow-auto px-4 pb-4 md:flex-col">
          {links.map(([to, label, Icon]) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex shrink-0 items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium ${isActive ? "bg-brand/15 text-brand-light" : "text-neutral-300 hover:bg-panel"}`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto hidden border-t border-line px-5 py-4 text-xs text-neutral-500 md:block">
          <p className="mb-2 text-brand">Synthetic demonstration</p>
          <p>
            {error
              ? "API unavailable"
              : s
                ? `${s.mode.toUpperCase()} · ${s.model ?? "Rules engine"}`
                : "Connecting…"}
          </p>
          <p className="mt-3">
            Investigator review required for every disposition.
          </p>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto bg-surface">
        <Outlet />
      </main>
    </div>
  );
}
