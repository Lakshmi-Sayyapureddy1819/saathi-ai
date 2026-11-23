import { CalendarDays, Check, CheckCircle2, Clock, FlaskConical, HeartHandshake, Hourglass, ShieldCheck, Utensils, XCircle } from "lucide-react";
import { formatINR } from "../../format";
import type { BookingConfirmation, BookingView, DateOption, HandoffView, PackageOption } from "../../types";
import { Button, EmptyState, StatusBadge } from "../ui";

export const FLOW_STEPS = ["Package", "Date", "Time", "Review", "Confirm", "Result"] as const;

export type FlowResult = "confirmed" | "pending" | "rejected" | null;

/** Maps the backend's booking stage to the 6-step progress indicator. Pure, so it is unit-tested. */
export function flowPosition(booking: BookingView, confirmed: boolean, handoff: HandoffView): { current: number; result: FlowResult } {
  if (confirmed) return { current: 5, result: "confirmed" };
  if (handoff.status === "pending") return { current: 5, result: "pending" };
  if (handoff.status === "rejected") return { current: 5, result: "rejected" };
  switch (booking.stage) {
    case "choosing_package": return { current: 0, result: null };
    case "choosing_slot": return { current: booking.date_iso ? 2 : 1, result: null };
    case "confirming": return { current: 3, result: null };
    default: return { current: -1, result: null };
  }
}

export function BookingStepper({ current, result }: { current: number; result: FlowResult }) {
  const label = current < 0 ? "Not started" : `Step ${current + 1} of ${FLOW_STEPS.length}: ${FLOW_STEPS[current]}`;
  return (
    <div className="stepper-wrap">
      <p className="step-mobile" aria-hidden="true"><b>{current < 0 ? "Pick a test to begin" : `Step ${current + 1} of ${FLOW_STEPS.length}`}</b>{current >= 0 && ` · ${FLOW_STEPS[current]}`}</p>
      <ol className="stepper" aria-label={`Booking progress. ${label}`}>
        {FLOW_STEPS.map((s, i) => {
          const done = i < current || (i === current && result === "confirmed");
          const failed = i === current && result === "rejected";
          const cls = failed ? "failed" : done ? "done" : i === current ? "current" : "";
          return (
            <li key={s} className={cls} aria-current={i === current ? "step" : undefined}>
              <span className="dot">{failed ? <XCircle size={14} aria-hidden="true" /> : done ? <Check size={14} aria-hidden="true" /> : i + 1}</span>
              <span className="lbl">{s}</span>
            </li>
          );
        })}
      </ol>
      <div className="step-bar" aria-hidden="true"><i style={{ width: `${Math.max(0, (current + 1) / FLOW_STEPS.length) * 100}%` }} /></div>
    </div>
  );
}

export function PackageCard({ p, actionLabel, onPick, disabled }: { p: PackageOption; actionLabel: string; onPick: (p: PackageOption) => void; disabled?: boolean }) {
  return (
    <li className="pkg-card" data-testid="pkg-card">
      <div className="pkg-ic"><FlaskConical size={20} aria-hidden="true" /></div>
      <div className="pkg-body">
        <h3>{p.name}</h3>
        <p className="muted pkg-meta">
          <span>{p.test_count} test{p.test_count === 1 ? "" : "s"}</span>
          {p.fasting_required ? <span><Utensils size={13} aria-hidden="true" /> Fasting {p.fasting_hours}h</span> : <span>No fasting</span>}
        </p>
      </div>
      <div className="pkg-side">
        <b className="num price">{formatINR(p.price_inr)}</b>
        <Button size="sm" variant="primary" disabled={disabled} onClick={() => onPick(p)} aria-label={`${actionLabel} ${p.name}`}>{actionLabel}</Button>
      </div>
    </li>
  );
}

export function SlotPicker({ dates, dateIso, dateLabel, slots, disabled, onDate, onSlot }: {
  dates: DateOption[]; dateIso: string | null; dateLabel: string | null; slots: string[]; disabled?: boolean;
  onDate: (word: DateOption["word"]) => void; onSlot: (slot: string) => void;
}) {
  return (
    <div className="slot-picker">
      <fieldset className="seg" disabled={disabled}>
        <legend className="label">Day</legend>
        <div className="seg-row">
          {dates.map((d) => (
            <button key={d.word} type="button" className={d.iso === dateIso ? "on" : ""} aria-pressed={d.iso === dateIso} onClick={() => onDate(d.word)}>
              <CalendarDays size={15} aria-hidden="true" />{d.label}
            </button>
          ))}
        </div>
      </fieldset>
      <fieldset className="seg" disabled={disabled}>
        <legend className="label">Available times{dateLabel ? ` on ${dateLabel}` : ""}</legend>
        {slots.length === 0
          ? <EmptyState icon={Clock} title="No free slots on this day" text="Try another day above. Slots are live from the lab schedule." data-testid="no-slots" />
          : <div className="slot-grid">{slots.map((s) => <button key={s} type="button" className="slot" onClick={() => onSlot(s)}>{s}</button>)}</div>}
      </fieldset>
    </div>
  );
}

export function BookingSummary({ booking }: { booking: BookingView }) {
  const p = booking.package;
  if (!p) return null;
  return (
    <div className="summary-card" data-testid="booking-summary">
      <div className="card-title"><ShieldCheck size={18} aria-hidden="true" />Review your booking</div>
      <dl className="kv">
        <dt>Test</dt><dd>{p.name}</dd>
        <dt>Date</dt><dd>{booking.date_label}</dd>
        <dt>Time</dt><dd>{booking.slot}</dd>
        <dt>Price</dt><dd>{formatINR(p.price_inr)}</dd>
        {p.fasting_required && <><dt>Preparation</dt><dd>Fast for {p.fasting_hours} hours before the test</dd></>}
      </dl>
      <p className="help" style={{ marginTop: 10 }}>Nothing is booked until you confirm. The booking system confirms the result.</p>
    </div>
  );
}

export function ConfirmedCard({ c, onAnother, disabled }: { c: BookingConfirmation; onAnother?: () => void; disabled?: boolean }) {
  return (
    <div className="result-card ok" data-testid="panel-confirmation">
      <div className="card-title"><CheckCircle2 size={20} aria-hidden="true" />Booking confirmed<StatusBadge tone="success">Confirmed</StatusBadge></div>
      <dl className="kv">
        <dt>Booking ID</dt><dd className="num">{c.booking_id}</dd>
        <dt>Test</dt><dd>{c.package_name}</dd>
        <dt>When</dt><dd>{c.date} · {c.slot}</dd>
      </dl>
      {onAnother && <Button size="sm" style={{ marginTop: 12 }} disabled={disabled} onClick={onAnother}>Book another test</Button>}
    </div>
  );
}

export function HandoffNotice({ handoff, booking }: { handoff: HandoffView; booking?: BookingView }) {
  if (handoff.status === "none") return null;
  const pending = handoff.status === "pending", approved = handoff.status === "approved";
  return (
    <div className={`result-card ${pending ? "wait" : approved ? "ok" : "bad"}`} role="status" data-testid="handoff-status">
      <div className="card-title">
        {pending ? <Hourglass size={20} aria-hidden="true" /> : approved ? <HeartHandshake size={20} aria-hidden="true" /> : <XCircle size={20} aria-hidden="true" />}
        {pending ? "Awaiting coordinator review" : approved ? "Coordinator approved" : "Coordinator could not complete this"}
        <StatusBadge tone={pending ? "warn" : approved ? "success" : "danger"}>{pending ? "Pending" : approved ? "Approved" : "Rejected"}</StatusBadge>
      </div>
      {pending && <p>We couldn't complete your booking automatically, so a person needs to review it. Ticket <b data-testid="ticket-id">{handoff.ticket_id}</b>. Messaging is paused until they decide. <b>Nothing has been booked.</b></p>}
      {approved && <p>Ticket <b>{handoff.ticket_id}</b>: a care coordinator will call you to arrange the test. {handoff.note}</p>}
      {handoff.status === "rejected" && <p>Ticket <b>{handoff.ticket_id}</b>: {handoff.note || "No reason was given."} You can pick a different time.</p>}
      {pending && booking?.package && (
        <dl className="kv" data-testid="requested-booking"><dt>Requested test</dt><dd>{booking.package.name}</dd><dt>Date</dt><dd>{booking.date_label}</dd>{booking.slot && <><dt>Time</dt><dd>{booking.slot}</dd></>}</dl>
      )}
      {pending && <p className="help" style={{ marginTop: 8 }}>What happens next: a coordinator reviews the request. This page updates by itself when they decide.</p>}
    </div>
  );
}
