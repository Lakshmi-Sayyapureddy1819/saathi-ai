import { motion } from "framer-motion";
import { Bell, CalendarCheck, HeartHandshake, LogOut, Menu, OctagonAlert, Settings } from "lucide-react";
import { TITLES, goto, type RouteId } from "../../app/routes";
import { useApp } from "../../app/context";
import { statusLabel } from "../../format";
import { Avatar, Dropdown, IconButton, StatusBadge } from "../ui";
import type { SessionView } from "../../types";

interface Note { id: string; icon: typeof Bell; text: string; to: RouteId; tone: "warn" | "danger" | "success" }

/** Notifications are derived only from real session state (handoff, emergency, confirmed bookings). */
export function notificationsFor(session: SessionView | null): Note[] {
  if (!session) return [];
  const out: Note[] = [];
  if (session.triage_status === "RED_CRISIS") out.push({ id: "emg", icon: OctagonAlert, text: "Emergency guidance was shown in your conversation.", to: "chat", tone: "danger" });
  const h = session.handoff;
  if (h.status === "pending") out.push({ id: "h", icon: HeartHandshake, text: `Ticket ${h.ticket_id}: awaiting coordinator review.`, to: "support", tone: "warn" });
  if (h.status === "approved") out.push({ id: "h", icon: HeartHandshake, text: `Ticket ${h.ticket_id}: a coordinator approved your request.`, to: "support", tone: "success" });
  if (h.status === "rejected") out.push({ id: "h", icon: HeartHandshake, text: `Ticket ${h.ticket_id}: the coordinator could not complete your request.`, to: "support", tone: "warn" });
  if (session.bookings.length > 0) out.push({ id: "b", icon: CalendarCheck, text: `${session.bookings.length} confirmed booking${session.bookings.length > 1 ? "s" : ""} in this session.`, to: "bookings", tone: "success" });
  return out;
}

export function Topbar({ route, onMenu }: { route: RouteId; onMenu: () => void }) {
  const { s } = useApp();
  const st = statusLabel(s.session);
  const notes = notificationsFor(s.session);
  const urgent = notes.some((n) => n.tone === "danger" || n.tone === "warn");
  const tone = st.tone === "ok" ? "brand" : st.tone === "wait" ? "warn" : st.tone === "alert" ? "danger" : "neutral";
  return (
    <header className="topbar">
      <IconButton icon={Menu} label="Open menu" className="tb-menu" onClick={onMenu} />
      <motion.h2 key={route} className="tb-title" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25, ease: [0.22, 0.8, 0.24, 1] }}>{TITLES[route]}</motion.h2>
      <div className="tb-right">
        <StatusBadge tone={tone} role="status" data-testid="status-pill">{st.label}</StatusBadge>
        <Dropdown label="Notifications" trigger={(p) => (
          <button className="icon-btn bordered notif" aria-label={`Notifications${notes.length ? `, ${notes.length} new` : ", none"}`} {...p}>
            <Bell size={19} aria-hidden="true" />{notes.length > 0 && <i className={`dot${urgent ? " urgent" : ""}`} aria-hidden="true" />}
          </button>
        )}>
          {(close) => notes.length === 0
            ? <p className="menu-empty muted">No notifications. Updates about handoffs and bookings appear here.</p>
            : notes.map((n) => { const I = n.icon; return <button key={n.id} role="menuitem" onClick={() => { close(); goto(n.to); }}><I size={16} aria-hidden="true" /><span>{n.text}</span></button>; })}
        </Dropdown>
        {s.session ? (
          <Dropdown label="Account" trigger={(p) => (
            <button className="profile-btn" aria-label={`Account menu for ${s.session!.member.name}`} {...p}>
              <Avatar name={s.session!.member.name} size="sm" /><span className="pn">{s.session!.member.name.split(" ")[0]}</span>
            </button>
          )}>
            {(close) => <>
              <button role="menuitem" onClick={() => { close(); goto("settings"); }}><Settings size={16} aria-hidden="true" />Settings</button>
              <div className="sep" />
              <button role="menuitem" data-testid="end-session" onClick={() => { close(); void s.end(); goto("overview"); }}><LogOut size={16} aria-hidden="true" />End session</button>
            </>}
          </Dropdown>
        ) : <a className="btn sm primary" href="#/">Start</a>}
      </div>
    </header>
  );
}
