import { useEffect, useState } from "react";
import { FlaskConical, LogOut, Play, Server, ShieldAlert, Sparkles, UserRound } from "lucide-react";
import { useApp } from "../app/context";
import { goto } from "../app/routes";
import { api } from "../api";
import type { Readiness } from "../types";
import { Banner, Button, Card, ConfirmationDialog, KeyValue, PageHeader, StatusBadge } from "../components/ui";

const SCENARIOS: { icon: typeof Sparkles; label: string; text: string; hint: string }[] = [
  { icon: Sparkles, label: "Grounded wellness question", text: "What yoga helps with exhaustion?", hint: "Answer from the program library" },
  { icon: Sparkles, label: "Hinglish question", text: "Mujhe bahut thakan rehti hai, kya yoga karun?", hint: "Language-aware reply" },
  { icon: FlaskConical, label: "Start a thyroid-test booking", text: "I want to book a thyroid test", hint: "Opens the booking flow" },
  { icon: ShieldAlert, label: "No-diagnosis rule", text: "do I have diabetes?", hint: "Deterministic safety notice" },
  { icon: ShieldAlert, label: "Emergency phrase", text: "I have severe chest pain", hint: "Deterministic emergency response" },
];

export function SettingsPage() {
  const { s, cfg, ask } = useApp();
  const [askEnd, setAskEnd] = useState(false);
  const [ready, setReady] = useState<Readiness | null>(null);
  useEffect(() => { api.readiness().then(setReady).catch(() => setReady(null)); }, []);
  const session = s.session;
  return (
    <div className="stack">
      <PageHeader eyebrow="Settings" title="Settings and demo tools" subtitle="Session details, server status and presenter shortcuts." />

      <div className="grid-2">
        <Card>
          <div className="card-title"><UserRound size={18} aria-hidden="true" />Session</div>
          {session ? <>
            <KeyValue rows={[["Member", session.member.name], ["Member ID", session.member.member_id], ["Language preference", session.member.language_preference],
              ["Session ID", <span className="num" key="sid">{session.session_id.slice(0, 8)}…</span>], ["Messages", String(session.messages.length)]]} />
            <Button variant="danger" icon={LogOut} style={{ marginTop: 14 }} onClick={() => setAskEnd(true)}>End session</Button>
          </> : <p className="muted">No active session. Start one from the Overview.</p>}
          <p className="help" style={{ marginTop: 10 }}>The session token lives in this tab's session storage only and is cleared when the tab closes.</p>
        </Card>
        <Card>
          <div className="card-title"><Server size={18} aria-hidden="true" />Server status</div>
          {cfg ? <KeyValue rows={[
            ["AI model", <StatusBadge key="m" tone={cfg.llm_configured ? "success" : "warn"}>{cfg.llm_configured ? "Configured" : "Not configured (demo replies)"}</StatusBadge>],
            ["Coordinator console", <StatusBadge key="c" tone={cfg.coordinator_console_enabled ? "success" : "neutral"}>{cfg.coordinator_console_enabled ? "Enabled" : "Disabled"}</StatusBadge>],
            ["Answer grounding", `${cfg.grounding_mode === "mode_b_facts" ? "Your records only (Mode B)" : "Library search (Mode A)"}`],
            ["Max message length", `${cfg.max_message_chars} characters`]]} />
            : <p className="muted">Can't reach the server.</p>}
          <p className="help" style={{ marginTop: 10 }}>Motion follows your operating system's "reduce motion" setting.</p>
        </Card>
      </div>

      <Card data-testid="readiness">
        <div className="card-title"><Server size={18} aria-hidden="true" />Deployment readiness
          {ready && <StatusBadge tone={ready.ready ? "success" : "warn"} icon={false}>{ready.environment}</StatusBadge>}</div>
        {ready ? <>
          <KeyValue rows={ready.components.map((c) => [c.name.replace(/_/g, " "),
            <span key={c.name}><StatusBadge tone={c.mode === "real" ? "success" : c.mode === "simulated" ? "warn" : "neutral"} icon={false}>{c.mode}</StatusBadge>{" "}<span className="muted">{c.detail}</span></span>])} />
          {ready.problems.length > 0 && <Banner tone="warn"><b>Blocks a production start:</b> {ready.problems.join(" ")}</Banner>}
        </> : <p className="muted">Readiness unavailable.</p>}
        <p className="help" style={{ marginTop: 10 }}>"Simulated" parts are demo stand-ins; a production start is refused while any remain (APP_ENV=production).</p>
      </Card>

      <Card data-testid="demo-tools">
        <div className="card-title"><Play size={18} aria-hidden="true" />Demo scenarios<StatusBadge tone="info" icon={false}>Presenter tools</StatusBadge></div>
        <Banner tone="info">These shortcuts send <b>real messages to the real backend</b>, exactly as if typed. Nothing is mocked or pre-recorded.</Banner>
        <div className="scenario-grid">
          {SCENARIOS.map((x) => { const I = x.icon; return (
            <button key={x.label} className="scenario" disabled={!session || s.busy || session.status === "awaiting_coordinator"} onClick={() => ask(x.text)}>
              <I size={18} aria-hidden="true" /><span><b>{x.label}</b><span className="muted">{x.hint}</span></span>
            </button>); })}
        </div>
        {!session && <p className="help" style={{ marginTop: 10 }}>Start a session first.</p>}
        <div className="row-gap" style={{ marginTop: 14 }}><Button onClick={() => goto("voice")}>Voice assistant</Button></div>
      </Card>

      <ConfirmationDialog open={askEnd} danger title="End this session?" confirmLabel="End session" onCancel={() => setAskEnd(false)}
        onConfirm={() => { setAskEnd(false); void s.end(); goto("overview"); }}>
        This clears the conversation from the server. Confirmed bookings stay in the booking system but will no longer be listed here.
      </ConfirmationDialog>
    </div>
  );
}
