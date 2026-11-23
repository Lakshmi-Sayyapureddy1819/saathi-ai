import { motion } from "framer-motion";
import { ChevronsLeft, ChevronsRight, LifeBuoy } from "lucide-react";
import { NAV, type RouteId } from "../../app/routes";
import { Brand } from "./Logo";

interface Props { route: RouteId; collapsed: boolean; onToggle: () => void; onNavigate?: () => void; mobile?: boolean }

export function Sidebar({ route, collapsed, onToggle, onNavigate, mobile }: Props) {
  const c = collapsed && !mobile;
  return (
    <nav className={`sidebar${c ? " collapsed" : ""}${mobile ? " in-drawer" : ""}`} aria-label="Main navigation">
      <div className="sb-head"><Brand collapsed={c} /></div>
      <ul className="sb-list">
        {NAV.map((n) => {
          const Icon = n.icon;
          const active = route === n.id;
          return (
            <li key={n.id}>
              <a href={n.path} className={`sb-link${active ? " active" : ""}`} aria-current={active ? "page" : undefined}
                title={c ? n.label : undefined} onClick={onNavigate} data-testid={`nav-${n.id}`}>
                {active && <motion.span layoutId={`nav-pill-${mobile ? "m" : "d"}`} className="sb-pill" transition={{ type: "spring", stiffness: 420, damping: 36 }} aria-hidden="true" />}
                <Icon size={20} aria-hidden="true" className="sb-ic" />
                {!c && <span className="sb-lbl">{n.label}</span>}
                {c && <span className="sr-only">{n.label}</span>}
              </a>
            </li>
          );
        })}
      </ul>

      <div className="sb-foot">
        <a className="sb-link" href="#/support" onClick={onNavigate} title={c ? "Help and support" : undefined}>
          <LifeBuoy size={20} aria-hidden="true" />{!c ? <span>Help &amp; support</span> : <span className="sr-only">Help and support</span>}
        </a>
        {!mobile && (
          <button className="sb-link sb-toggle" onClick={onToggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}>
            {collapsed ? <ChevronsRight size={20} aria-hidden="true" /> : <><ChevronsLeft size={20} aria-hidden="true" /><span>Collapse</span></>}
          </button>
        )}
      </div>
    </nav>
  );
}
