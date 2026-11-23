import type { ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Utensils } from "lucide-react";
import { formatINR, lastBooking } from "../../format";
import type { SessionView } from "../../types";
import { Button } from "../ui";
import { BookingStepper, BookingSummary, ConfirmedCard, HandoffNotice, PackageCard, SlotPicker, flowPosition } from "./BookingFlow";

interface Props {
  session: SessionView;
  busy: boolean;
  paused: boolean;
  onSend: (text: string) => void;
  idle?: ReactNode;          // rendered when no booking is in progress
  hideStepper?: boolean;
}

/**
 * Drives the booking journey from the backend's typed `booking` state. Every button sends exactly the
 * message a user could type, so the safety gate, router and slot locking behave identically.
 */
export function BookingWizard({ session, busy, paused, onSend, idle, hideStepper }: Props) {
  const { booking, handoff } = session;
  const confirmedMsg = lastBooking(session.messages);
  const pos = flowPosition(booking, confirmedMsg !== null, handoff);
  const off = busy || paused;
  const pending = handoff.status === "pending";
  const view = confirmedMsg?.confirmation ? "confirmed" : pending ? "pending" : booking.stage;

  return (
    <div className="wizard" data-testid="booking-wizard">
      {!hideStepper && pos.current >= 0 && <BookingStepper current={pos.current} result={pos.result} />}
      <HandoffNotice handoff={handoff} booking={booking} />

      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={view} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }} transition={{ duration: 0.16 }}>
          {view === "confirmed" && confirmedMsg?.confirmation && <ConfirmedCard c={confirmedMsg.confirmation} disabled={off} onAnother={() => onSend("I want to book another lab test")} />}

          {view === "choosing_package" && (
            <section aria-label="Choose a test">
              <h3 className="wz-h">Which test would you like?</h3>
              <ul className="pkg-grid" data-testid="pkg-list">
                {booking.options.map((p) => <PackageCard key={p.package_id} p={p} actionLabel="Select" disabled={off} onPick={(x) => onSend(x.package_id)} />)}
              </ul>
              <Button variant="ghost" size="sm" disabled={off} onClick={() => onSend("cancel")}>Cancel booking</Button>
            </section>
          )}

          {view === "choosing_slot" && booking.package && (
            <section aria-label="Choose a date and time">
              <h3 className="wz-h">{booking.package.name} <span className="muted num">· {formatINR(booking.package.price_inr)}</span></h3>
              {booking.package.fasting_required && <p className="help wz-note"><Utensils size={13} aria-hidden="true" /> Fasting {booking.package.fasting_hours}h required, so morning slots are offered.</p>}
              <SlotPicker dates={booking.dates} dateIso={booking.date_iso} dateLabel={booking.date_label} slots={booking.slots} disabled={off}
                onDate={(w) => onSend(w)} onSlot={(s) => onSend(s)} />
              <Button variant="ghost" size="sm" disabled={off} onClick={() => onSend("cancel")}>Cancel booking</Button>
            </section>
          )}

          {view === "confirming" && booking.package && (
            <section aria-label="Review and confirm">
              <BookingSummary booking={booking} />
              <div className="wz-actions">
                <Button variant="primary" size="lg" loading={busy} disabled={paused} onClick={() => onSend("yes, confirm")} data-testid="confirm-booking">Confirm booking</Button>
                <Button disabled={off} onClick={() => onSend("change time")}>Change time</Button>
                <Button variant="ghost" disabled={off} onClick={() => onSend("cancel")}>Cancel</Button>
              </div>
            </section>
          )}

          {view === "idle" && idle}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
