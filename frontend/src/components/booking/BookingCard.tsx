import { CalendarClock, CheckCircle2, Circle, Clock, FlaskConical, XCircle } from "lucide-react";
import type { BookingItem, HandoffView } from "../../types";
import { Button, StatusBadge } from "../ui";

type Props =
  | { kind: "confirmed"; booking: BookingItem; compact?: boolean; onCancel?: () => void; disabled?: boolean }
  | { kind: "handoff"; handoff: HandoffView; name: string; date: string; slot: string; compact?: boolean };

interface Step { label: string; state: "done" | "current" | "todo" | "failed"; note?: string }

function Timeline({ steps }: { steps: Step[] }) {
  return (
    <ol className="timeline" aria-label="Status timeline">
      {steps.map((s) => (
        <li key={s.label} className={s.state}>
          {s.state === "done" ? <CheckCircle2 size={16} aria-hidden="true" /> : s.state === "failed" ? <XCircle size={16} aria-hidden="true" />
            : s.state === "current" ? <Clock size={16} aria-hidden="true" /> : <Circle size={16} aria-hidden="true" />}
          <span><b>{s.label}</b>{s.note && <em>{s.note}</em>}</span>
        </li>
      ))}
    </ol>
  );
}

/** One booking, in one of the states the backend can actually report. Never shows "confirmed" for a handoff. */
export function BookingCard(p: Props) {
  if (p.kind === "confirmed") {
    const b = p.booking;
    return (
      <article className="booking-card" data-testid="my-booking">
        <div className="bc-ic"><FlaskConical size={20} aria-hidden="true" /></div>
        <div className="bc-main">
          <div className="bc-top"><h3>{b.package_name}</h3><StatusBadge tone="success">Confirmed</StatusBadge></div>
          <p className="bc-when"><CalendarClock size={15} aria-hidden="true" />{b.date} · {b.slot}</p>
          <p className="muted bc-ref">Reference <b className="num">{b.booking_id}</b></p>
          {!p.compact && <Timeline steps={[{ label: "Requested", state: "done" }, { label: "Confirmed by booking system", state: "done", note: b.booking_id }]} />}
        </div>
        {p.onCancel && <Button size="sm" disabled={p.disabled} onClick={p.onCancel} aria-label={`Cancel booking ${b.booking_id}`}>Cancel</Button>}
      </article>
    );
  }
  const h = p.handoff;
  const tone = h.status === "approved" ? "success" : h.status === "rejected" ? "danger" : "warn";
  const label = h.status === "approved" ? "Approved by coordinator" : h.status === "rejected" ? "Not completed" : "Awaiting coordinator review";
  const steps: Step[] = [
    { label: "Requested", state: "done", note: "Automatic booking could not be completed" },
    { label: "Coordinator review", state: h.status === "pending" ? "current" : h.status === "rejected" ? "failed" : "done", note: h.note || undefined },
    { label: h.status === "rejected" ? "Not booked" : "Coordinator will call to arrange", state: h.status === "approved" ? "done" : "todo" },
  ];
  return (
    <article className="booking-card handoff" data-testid="pending-booking">
      <div className="bc-ic"><FlaskConical size={20} aria-hidden="true" /></div>
      <div className="bc-main">
        <div className="bc-top"><h3>{p.name}</h3><StatusBadge tone={tone}>{label}</StatusBadge></div>
        <p className="bc-when"><CalendarClock size={15} aria-hidden="true" />{p.date}{p.slot ? ` · ${p.slot}` : ""} <span className="muted">(requested, not booked)</span></p>
        <p className="muted bc-ref">Ticket <b className="num">{h.ticket_id}</b></p>
        {!p.compact && <Timeline steps={steps} />}
      </div>
    </article>
  );
}
