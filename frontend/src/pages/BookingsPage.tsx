import { useState } from "react";
import { CalendarCheck, CalendarX2, CheckCheck, FlaskConical, Hourglass } from "lucide-react";
import { useApp } from "../app/context";
import { goto } from "../app/routes";
import { SessionGate } from "../components/SessionGate";
import { BookingCard } from "../components/booking/BookingCard";
import { Banner, Button, ConfirmationDialog, EmptyState, PageHeader, Tabs } from "../components/ui";
import type { BookingItem } from "../types";

type Tab = "upcoming" | "pending" | "completed" | "cancelled";

function Inner() {
  const { s } = useApp();
  const session = s.session!;
  const [tab, setTab] = useState<Tab>("upcoming");
  const [askCancel, setAskCancel] = useState<BookingItem | null>(null);
  const paused = session.status === "awaiting_coordinator";
  const h = session.handoff;
  const hasRequest = h.status !== "none" && !!session.booking.package;
  const off = s.busy || paused;

  const doCancel = () => { const b = askCancel; setAskCancel(null); if (b) { void s.send(`cancel ${b.booking_id}`); } };

  return (
    <div className="stack">
      <PageHeader eyebrow="Bookings" title="My bookings" subtitle="Everything shown here is read from the booking system for this session. Nothing is invented."
        actions={<Button variant="primary" icon={FlaskConical} onClick={() => goto("labs")}>Book a lab test</Button>} />
      <Tabs label="Booking status" value={tab} onChange={setTab} tabs={[
        { id: "upcoming", label: "Upcoming", count: session.bookings.length },
        { id: "pending", label: "Pending approval", count: h.status === "pending" ? 1 : 0 },
        { id: "completed", label: "Completed" },
        { id: "cancelled", label: "Cancelled" },
      ]} />

      <section aria-live="polite" className="stack-sm" data-testid="my-bookings">
        {tab === "upcoming" && (session.bookings.length === 0
          ? <EmptyState icon={CalendarCheck} title="No upcoming bookings" text="When you confirm a lab test with Saathi it appears here with its reference number." action={<Button variant="primary" onClick={() => goto("labs")}>Browse lab tests</Button>} />
          : session.bookings.map((b) => <BookingCard key={b.booking_id} kind="confirmed" booking={b} disabled={off} onCancel={() => setAskCancel(b)} />))}

        {tab === "pending" && (!hasRequest
          ? <EmptyState icon={Hourglass} title="Nothing awaiting approval" text="If a booking can't be completed automatically, a care coordinator reviews it and it shows up here with its status." />
          : <>
            {h.status === "pending" && <Banner tone="warn">Awaiting coordinator review. Nothing is booked until they approve. This updates automatically.</Banner>}
            <BookingCard kind="handoff" handoff={h} name={session.booking.package!.name} date={session.booking.date_label ?? ""} slot={session.booking.slot ?? ""} />
          </>)}

        {tab === "completed" && <EmptyState icon={CheckCheck} title="No completed bookings to show" text="This build doesn't keep visit history, so there is nothing to list. Past visits are never made up." />}
        {tab === "cancelled" && <EmptyState icon={CalendarX2} title="No cancelled bookings to show" text="Cancelled bookings aren't retained by the booking system in this build. A cancellation you make is confirmed in the chat." />}
      </section>

      <ConfirmationDialog open={!!askCancel} danger title="Cancel this booking?" confirmLabel="Yes, cancel it" cancelLabel="Keep it" onConfirm={doCancel} onCancel={() => setAskCancel(null)}>
        {askCancel && <>This cancels <b>{askCancel.package_name}</b> on {askCancel.date} at {askCancel.slot} ({askCancel.booking_id}) and frees the slot. Saathi will confirm in the chat.</>}
      </ConfirmationDialog>
    </div>
  );
}

export function BookingsPage() { return <SessionGate to="bookings" what="your bookings"><Inner /></SessionGate>; }
