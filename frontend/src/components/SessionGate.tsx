import type { ReactNode } from "react";
import { UserRound } from "lucide-react";
import { useApp } from "../app/context";
import type { RouteId } from "../app/routes";
import { Button, Card, StatusBadge } from "./ui";

/** Member picker + start button. Members are the backend's demo members (there is no real login in this build). */
export function StartCard({ to = "chat", first, title = "Start a conversation", compact }: { to?: RouteId; first?: string; title?: string; compact?: boolean }) {
  const { members, membersLoading, memberId, setMemberId, begin, s, cfgError } = useApp();
  return (
    <Card className={`start-card${compact ? " compact" : ""}`}>
      <form onSubmit={(e) => { e.preventDefault(); if (memberId) void begin(memberId, { to, first }); }}>
        <div className="card-title"><UserRound size={18} aria-hidden="true" />{title}<StatusBadge tone="info" icon={false}>Demo members</StatusBadge></div>
        <div className="field">
          <label htmlFor="member">Continue as</label>
          <select id="member" className="select" value={memberId} onChange={(e) => setMemberId(e.target.value)} disabled={membersLoading || members.length === 0}>
            {members.map((m) => <option key={m.member_id} value={m.member_id}>{m.name}</option>)}
          </select>
          <span className="help">Sign-in is simulated: pick one of the backend's sample members. Nothing here is real patient data.</span>
        </div>
        <Button variant="primary" size="lg" block type="submit" loading={s.starting} disabled={!memberId} data-testid="start-chat" style={{ marginTop: 16 }}>
          Start conversation
        </Button>
        {cfgError && <p className="help err" role="alert" style={{ marginTop: 8 }}>{cfgError}</p>}
      </form>
    </Card>
  );
}

/** Renders children only with an active session; otherwise explains why and offers to start one. */
export function SessionGate({ to, children, what }: { to: RouteId; children: ReactNode; what: string }) {
  const { s } = useApp();
  if (s.restoring) return <p className="muted" role="status">Restoring your session…</p>;
  if (s.session) return <>{children}</>;
  return (
    <div className="gate">
      <div className="gate-copy"><h2>Start a session to use {what}</h2><p className="muted">Saathi needs a member profile to personalise answers and to attach bookings to someone. Choose a demo member to continue.</p></div>
      <StartCard to={to} />
    </div>
  );
}
