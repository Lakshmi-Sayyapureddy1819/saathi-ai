import { useMemo, useState } from "react";
import { CalendarClock, Check, Scale, Timer, Utensils } from "lucide-react";
import { formatINR } from "../../format";
import { lastMeal, packageFor, perTest } from "../../insights";
import type { BookingItem, PackageOption } from "../../types";
import { Button, EmptyState } from "../ui";

const SLOTS = ["07:00 AM", "07:30 AM", "08:00 AM", "08:30 AM", "09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", "11:00 AM", "11:30 AM"];

/** Side-by-side comparison of up to three catalogue packages. "Best" is spelled out, never colour-only. */
export function ComparePanel({ packages, onBook, disabled }: { packages: PackageOption[]; onBook: (p: PackageOption) => void; disabled?: boolean }) {
  const [picked, setPicked] = useState<string[]>([]);
  const chosen = useMemo(() => picked.map((id) => packages.find((p) => p.package_id === id)).filter((p): p is PackageOption => !!p), [picked, packages]);
  const toggle = (id: string) => setPicked((l) => (l.includes(id) ? l.filter((x) => x !== id) : l.length >= 3 ? l : [...l, id]));
  const best = (f: (p: PackageOption) => number, dir: 1 | -1) => (chosen.length < 2 ? null : [...chosen].sort((a, b) => dir * (f(a) - f(b)))[0]!.package_id);
  const bPrice = best((p) => p.price_inr, 1), bPer = best(perTest, 1), bTests = best((p) => p.test_count, -1);
  const cell = (p: PackageOption, bestId: string | null, content: string) => <td key={p.package_id}>{content}{bestId === p.package_id && <span className="best"><Check size={12} aria-hidden="true" /> Best</span>}</td>;

  return (
    <section className="card" aria-label="Compare packages" data-testid="compare">
      <div className="card-title"><Scale size={18} aria-hidden="true" />Compare packages</div>
      <p className="muted" style={{ marginBottom: 12 }}>Pick up to three. Figures come straight from the lab catalogue; price per test is price divided by the number of tests.</p>
      <div className="chips" role="group" aria-label="Packages to compare">
        {packages.map((p) => {
          const on = picked.includes(p.package_id);
          return <button key={p.package_id} className={`chip${on ? " active" : ""}`} aria-pressed={on} disabled={!on && picked.length >= 3} onClick={() => toggle(p.package_id)}>{p.name}</button>;
        })}
      </div>
      {chosen.length === 0 ? <EmptyState icon={Scale} title="Nothing selected yet" text="Choose two or three packages above to see them side by side." />
        : (
          <div className="cmp-wrap"><table className="cmp">
            <thead><tr><th scope="col"><span className="sr-only">Measure</span></th>{chosen.map((p) => <th key={p.package_id} scope="col">{p.name}</th>)}</tr></thead>
            <tbody>
              <tr><th scope="row">Price</th>{chosen.map((p) => cell(p, bPrice, formatINR(p.price_inr)))}</tr>
              <tr><th scope="row">Tests included</th>{chosen.map((p) => cell(p, bTests, String(p.test_count)))}</tr>
              <tr><th scope="row">Price per test</th>{chosen.map((p) => cell(p, bPer, formatINR(Math.round(perTest(p)))))}</tr>
              <tr><th scope="row">Fasting</th>{chosen.map((p) => <td key={p.package_id}>{p.fasting_required ? `${p.fasting_hours} hours` : "Not required"}</td>)}</tr>
              <tr><th scope="row"><span className="sr-only">Book</span></th>{chosen.map((p) => <td key={p.package_id}><Button size="sm" variant="primary" disabled={disabled} onClick={() => onBook(p)} aria-label={`Book ${p.name}`}>Book</Button></td>)}</tr>
            </tbody>
          </table></div>
        )}
    </section>
  );
}

/** When to stop eating for a fasting test. Pure arithmetic on the catalogue's fasting hours. */
export function FastingPlanner({ packages }: { packages: PackageOption[] }) {
  const fasting = packages.filter((p) => p.fasting_required);
  const [id, setId] = useState("");
  const [slot, setSlot] = useState("08:00 AM");
  const pkg = fasting.find((p) => p.package_id === id) ?? fasting[0];
  const res = pkg ? lastMeal(slot, pkg.fasting_hours) : null;
  return (
    <section className="card" aria-label="Fasting planner" data-testid="fasting-planner">
      <div className="card-title"><Timer size={18} aria-hidden="true" />Fasting planner</div>
      <p className="muted" style={{ marginBottom: 12 }}>Works out your last meal from the package's fasting hours. Water is generally fine unless your doctor or the lab says otherwise.</p>
      {!pkg ? <EmptyState icon={Utensils} title="No fasting packages" text="The catalogue has no fasting tests right now." /> : (
        <>
          <div className="plan-form">
            <div className="field"><label htmlFor="pl-pkg">Package</label>
              <select id="pl-pkg" className="select" value={pkg.package_id} onChange={(e) => setId(e.target.value)}>
                {fasting.map((p) => <option key={p.package_id} value={p.package_id}>{p.name} ({p.fasting_hours}h)</option>)}</select></div>
            <div className="field"><label htmlFor="pl-slot">Appointment time</label>
              <select id="pl-slot" className="select" value={slot} onChange={(e) => setSlot(e.target.value)}>{SLOTS.map((s) => <option key={s}>{s}</option>)}</select></div>
          </div>
          {res && (
            <div className="plan-out" role="status" data-testid="plan-result">
              <Utensils size={22} aria-hidden="true" />
              <div><span className="muted">Last meal by</span><b className="num">{res.time}</b><span className="muted">{res.previousDay ? "the evening before" : "that morning"} · {pkg.fasting_hours}h fast before {slot}</span></div>
            </div>
          )}
          <p className="help" style={{ marginTop: 8 }}>Real slots are shown when you book. This planner only does the arithmetic.</p>
        </>
      )}
    </section>
  );
}

/** Preparation for the bookings confirmed in this session (read from the booking system + catalogue). */
export function PrepList({ bookings, packages }: { bookings: BookingItem[]; packages: PackageOption[] }) {
  return (
    <section className="card" aria-label="Preparation for your bookings" data-testid="prep-list">
      <div className="card-title"><CalendarClock size={18} aria-hidden="true" />Get ready for your bookings</div>
      {bookings.length === 0 ? <EmptyState icon={CalendarClock} title="No confirmed bookings in this session" text="Once you book a test, your fasting and timing guidance appears here." />
        : <ul className="prep">{bookings.map((b) => {
          const p = packageFor(b, packages);
          const lm = p?.fasting_required ? lastMeal(b.slot, p.fasting_hours) : null;
          return (
            <li key={b.booking_id}>
              <b>{b.package_name}</b><span className="muted">{b.date} · {b.slot} · {b.booking_id}</span>
              <span className="prep-line">{!p ? "Preparation details aren't in the catalogue for this test." : p.fasting_required
                ? <>Fast for <b>{p.fasting_hours} hours</b>{lm ? <>: last meal by <b>{lm.time}</b> {lm.previousDay ? "the evening before" : "that morning"}.</> : "."}</> : "No fasting needed. Eat and drink normally."}</span>
            </li>);
        })}</ul>}
    </section>
  );
}
