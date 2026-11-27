import { useState } from "react";
import { Phone, PhoneCall } from "lucide-react";
import { ApiError } from "../api";
import { useApp } from "../app/context";
import { SessionGate } from "../components/SessionGate";
import { Button, Card, PageHeader, StatusBadge } from "../components/ui";
import type { ReminderCallResult } from "../types";

const OUTCOME: Record<ReminderCallResult["outcome"], { tone: "success" | "neutral" | "warn"; label: string }> = {
  booked: { tone: "success", label: "Booked" },
  declined: { tone: "neutral", label: "Declined: nothing booked" },
  no_pending_checkup: { tone: "neutral", label: "No pending checkup" },
  unfinished: { tone: "warn", label: "Not finished: a care coordinator will follow up" },
};

function Inner() {
  const { s } = useApp();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ReminderCallResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await s.reminderCall());
    } catch (e) {
      setResult(null);
      setError(e instanceof ApiError ? e.message : "The reminder call could not be started.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <PageHeader eyebrow="Demo" title="Reminder call" subtitle="Mimi phones you about a pending checkup and offers to book it." />

      <Card>
        <div className="card-title"><Phone size={18} aria-hidden="true" />Simulated phone call</div>
        <p className="muted">
          The call uses simulated telephony and scripted replies: Mimi asks to book, you agree, pick 09:00 AM and confirm.
          A successful call books a real demo lab test for this member.
        </p>
        <div className="row-gap" style={{ marginTop: 12 }}>
          <Button variant="primary" icon={PhoneCall} onClick={run} disabled={busy}>
            {busy ? "Calling…" : "Start reminder call"}
          </Button>
        </div>
      </Card>

      {error && <Card className="flat" role="alert"><p>{error}</p></Card>}

      {result && (
        <Card>
          <div className="row-gap"><StatusBadge tone={OUTCOME[result.outcome].tone}>{OUTCOME[result.outcome].label}</StatusBadge></div>
          <h3 style={{ margin: "12px 0 6px" }}>Call transcript</h3>
          <ol className="call-transcript">
            {result.transcript.map((line, i) => <li key={i}>{line}</li>)}
          </ol>
          {result.booking_ids.length > 0 && (
            <>
              <h3 style={{ margin: "12px 0 6px" }}>Booked</h3>
              <ul>{result.booking_ids.map((b) => <li key={b}>{b}</li>)}</ul>
            </>
          )}
          <p className="help">Trace {result.trace_id}</p>
        </Card>
      )}
    </div>
  );
}

export function ReminderCallPage() {
  return <SessionGate to="reminder" what="the reminder call"><Inner /></SessionGate>;
}
