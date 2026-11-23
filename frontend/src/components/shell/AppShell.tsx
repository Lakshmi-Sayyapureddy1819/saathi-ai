import { useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { NAV, type RouteId } from "../../app/routes";
import { Drawer } from "../ui";
import { Backdrop } from "./Backdrop";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

const KEY = "saathi.sidebar.collapsed";

export function AppShell({ route, children }: { route: RouteId; children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(KEY) === "1");
  const [menu, setMenu] = useState(false);
  const toggle = () => setCollapsed((c) => { localStorage.setItem(KEY, c ? "0" : "1"); return !c; });
  const immersive = route === "voice" || route === "chat";

  return (
    <div className={`shell${collapsed ? " collapsed" : ""}`}>
      <a className="skip-link" href="#main">Skip to content</a>
      <Backdrop />
      <motion.i key={`bar-${route}`} className="route-bar" aria-hidden="true" initial={{ scaleX: 0, opacity: 1 }} animate={{ scaleX: 1, opacity: 0 }} transition={{ scaleX: { duration: 0.55, ease: [0.22, 0.8, 0.24, 1] }, opacity: { duration: 0.35, delay: 0.5 } }} />
      <aside className="sb-wrap"><Sidebar route={route} collapsed={collapsed} onToggle={toggle} /></aside>
      <div className="shell-main">
        <Topbar route={route} onMenu={() => setMenu(true)} />
        <main id="main" className={`content${immersive ? " immersive" : ""}`} tabIndex={-1}>
          <motion.div key={route} className="page" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18, ease: [0.22, 0.8, 0.24, 1] }}>
            {children}
          </motion.div>
        </main>
        {!immersive && (
          <footer className="foot" role="contentinfo">
            Saathi is an AI wellness assistant. It does not diagnose and is not a substitute for a medical professional.
            In an emergency call <b>112</b> (India) or your local emergency number.
          </footer>
        )}
      </div>

      <nav className="bottom-nav" aria-label="Primary">
        {NAV.filter((n) => n.mobile).map((n) => {
          const I = n.icon;
          return (
            <a key={n.id} href={n.path} className={route === n.id ? "active" : ""} aria-current={route === n.id ? "page" : undefined}>
              {route === n.id && <motion.i layoutId="bn-indicator" className="bn-ind" transition={{ type: "spring", stiffness: 420, damping: 34 }} aria-hidden="true" />}
              <I size={21} aria-hidden="true" className="bn-ic" /><span>{n.label.replace("Voice assistant", "Voice").replace("Chat with Mimi", "Chat").replace("My Bookings", "Bookings").replace("Lab Tests", "Labs")}</span>
            </a>
          );
        })}
      </nav>
      <Drawer open={menu} onClose={() => setMenu(false)} title="Menu">
        <Sidebar route={route} collapsed={false} onToggle={toggle} onNavigate={() => setMenu(false)} mobile />
      </Drawer>
    </div>
  );
}
