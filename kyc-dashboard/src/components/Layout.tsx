import {
  Activity,
  ClipboardList,
  FileCheck2,
  Users,
} from "lucide-react";
import { Link, NavLink, Outlet } from "react-router-dom";
const links = [
  ["/alerts", "Investigations", ClipboardList],
  ["/kyc", "Customers", Users],
  ["/monitoring", "Monitoring", Activity],
  ["/policies", "Detection Policies", FileCheck2],
] as const;
export default function Layout() {
  return (
    <div className="flex h-full flex-col md:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-line bg-black md:w-56 md:border-r md:border-b-0">
        <Link to="/alerts" className="aml-brand" aria-label="AML Operations — Investigations">
          <img src={`${import.meta.env.BASE_URL}aml-mark.svg`} width="40" height="40" alt="" />
          <span className="aml-wordmark"><span className="aml-wordmark-name">AML</span><span className="aml-wordmark-subtitle">OPERATIONS</span></span>
        </Link>
        <nav className="flex gap-1 overflow-auto px-4 pb-4 md:flex-col">
          {links.map(([to, label, Icon], index) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                ` ${index === 3 ? "md:mt-8" : ""} flex shrink-0 items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium ${isActive ? "bg-brand/15 text-brand-light" : "text-neutral-300 hover:bg-panel"}`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto bg-surface">
        <Outlet />
      </main>
    </div>
  );
}
