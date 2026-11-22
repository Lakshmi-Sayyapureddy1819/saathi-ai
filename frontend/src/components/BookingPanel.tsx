import { useState } from "react";
import { STEPS, formatINR, stepIndex } from "../format";
import type { BookingItem, BookingView, ChatMessage, HandoffView } from "../types";
import { PackageBrowser } from "./PackageBrowser";

interface Props {
  booking: BookingView;
  handoff: HandoffView;
  confirmed: ChatMessage | null; // tool-confirmed booking, shown until the member moves on
  bookings: BookingItem[];       // confirmed bookings that can still be cancelled (from the backend)
  busy: boolean;
  paused: boolean;
  onSend: (text: string) => void;
}

export function BookingPanel({ booking, handoff, confirmed, bookings, busy, paused, onSend }: Props) {
  const [askId, setAskId] = useState<string | null>(null); // booking awaiting "are you sure?"
  const off = busy || paused;
  const pending = handoff.status === "pending";
  const idx = stepIndex(booking.stage, confirmed !== null);

  return (
    <aside className="panel" aria-label="Booking assistant" data-testid="booking-panel">
      <h2>Lab booking</h2>

      {handoff.status !== "none" && (
        <div className={`card handoff-status ${handoff.status}`} role="status" data-testid="handoff-status">
          {handoff.status === "pending" && (<>
            <strong>Waiting for a care coordinator</strong>
            <p>We couldn't complete your booking automatically, so a person needs to review it. Ticket{" "}
              <b data-testid="ticket-id">{handoff.ticket_id}</b>. Messaging is paused until they decide. Nothing has been booked.</p>
          </>)}
          {handoff.status === "approved" && (<>
            <strong>Coordinator approved ticket {handoff.ticket_id}</strong>
            <p>A care coordinator will call you to arrange the test. {handoff.note}</p>
          </>)}
          {handoff.status === "rejected" && (<>
            <strong>Coordinator couldn't complete ticket {handoff.ticket_id}</strong>
            <p>{handoff.note || "No reason given."} You can choose a different time below.</p>
          </>)}
        </div>
      )}

      {handoff.status === "pending" && booking.package && (
        <div className="card summary" data-testid="requested-booking">
          <strong>Requested (not booked)</strong>
          <dl className="kv">
            <dt>Test</dt><dd>{booking.package.name}</dd>
            <dt>Date</dt><dd>{booking.date_label}</dd>
            {booking.slot && <><dt>Time</dt><dd>{booking.slot}</dd></>}
          </dl>
        </div>
      )}

      {!pending && (
      <ol className="steps" aria-label="Booking progress">
        {STEPS.map((s, i) => (
          <li key={s.stage} className={i < idx ? "done" : i === idx ? "current" : ""}
            aria-current={i === idx ? "step" : undefined}>{s.label}</li>
        ))}
      </ol>
      )}

      {confirmed?.confirmation && (
        <div className="card success" data-testid="panel-confirmation">
          <strong>Booked</strong>
          <dl className="kv">
            <dt>Booking ID</dt><dd>{confirmed.confirmation.booking_id}</dd>
            <dt>Test</dt><dd>{confirmed.confirmation.package_name}</dd>
            <dt>When</dt><dd>{confirmed.confirmation.date} · {confirmed.confirmation.slot}</dd>
          </dl>
          <button className="btn small" disabled={off} onClick={() => onSend("I want to book another lab test")}>Book another test</button>
        </div>
      )}

      {!pending && booking.stage === "idle" && !confirmed && (
        <>
          <p className="muted">No booking in progress. Pick a test, or type something like “book a thyroid test”.</p>
          <PackageBrowser compact actionLabel="Book" disabled={off} onPick={(p) => onSend(`Book ${p.name}`)} />
        </>
      )}

      {!pending && booking.stage === "choosing_package" && (
        <>
          <p><b>Which test would you like?</b></p>
          <PackageBrowser compact actionLabel="Select" disabled={off} options={booking.options}
            onPick={(p) => onSend(p.package_id)} />
          <button className="btn ghost small" disabled={off} onClick={() => onSend("cancel")}>Cancel booking</button>
        </>
      )}

      {!pending && booking.stage === "choosing_slot" && booking.package && (
        <>
          <p><b>{booking.package.name}</b> · {formatINR(booking.package.price_inr)}
            {booking.package.fasting_required && <span className="muted"> · fasting {booking.package.fasting_hours}h, so morning slots</span>}</p>
          <fieldset className="chip-group"><legend>Day</legend>
            {booking.dates.map((d) => (
              <button key={d.word} className={`chip${d.iso === booking.date_iso ? " active" : ""}`} disabled={off}
                aria-pressed={d.iso === booking.date_iso} onClick={() => onSend(d.word)}>{d.label}</button>
            ))}
          </fieldset>
          <fieldset className="chip-group"><legend>Time on {booking.date_label}</legend>
            {booking.slots.map((s) => (
              <button key={s} className="chip" disabled={off} onClick={() => onSend(s)}>{s}</button>
            ))}
            {booking.slots.length === 0 && <span className="muted">No free slots on this day.</span>}
          </fieldset>
          <button className="btn ghost small" disabled={off} onClick={() => onSend("cancel")}>Cancel booking</button>
        </>
      )}

      {!pending && booking.stage === "confirming" && booking.package && (
        <>
          <div className="card summary" data-testid="booking-summary">
            <strong>Booking summary</strong>
            <dl className="kv">
              <dt>Test</dt><dd>{booking.package.name}</dd>
              <dt>Date</dt><dd>{booking.date_label}</dd>
              <dt>Time</dt><dd>{booking.slot}</dd>
              <dt>Price</dt><dd>{formatINR(booking.package.price_inr)}</dd>
              {booking.package.fasting_required && <><dt>Prep</dt><dd>Fast for {booking.package.fasting_hours} hours</dd></>}
            </dl>
            <p className="muted">Nothing is booked until you confirm.</p>
          </div>
          <div className="actions">
            <button className="btn primary" disabled={off} onClick={() => onSend("yes, confirm")}>Confirm booking</button>
            <button className="btn" disabled={off} onClick={() => onSend("change time")}>Change time</button>
            <button className="btn ghost" disabled={off} onClick={() => onSend("cancel")}>Cancel</button>
          </div>
        </>
      )}
      {bookings.length > 0 && (
        <section className="card my-bookings" aria-label="Your bookings" data-testid="my-bookings">
          <strong>Your bookings</strong>
          <ul>
            {bookings.map((b) => (
              <li key={b.booking_id} data-testid="my-booking">
                <div>
                  <b>{b.package_name}</b>
                  <span className="muted"> {b.date} · {b.slot} · {b.booking_id}</span>
                </div>
                {askId === b.booking_id ? (
                  <span className="actions">
                    <button className="btn small danger" disabled={off} onClick={() => { setAskId(null); onSend(`cancel ${b.booking_id}`); }}>
                      Yes, cancel it</button>
                    <button className="btn small ghost" onClick={() => setAskId(null)}>Keep it</button>
                  </span>
                ) : (
                  <button className="btn small" disabled={off} onClick={() => setAskId(b.booking_id)}
                    aria-label={`Cancel booking ${b.booking_id}`}>Cancel</button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  );
}
