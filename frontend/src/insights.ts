// Pure calculations behind the Health Insights dashboard. Inputs are ONLY backend data (lab catalogue, program library,
// this session's bookings). Nothing here invents a measurement; derived numbers are simple arithmetic on catalogue fields.
import type { BookingItem, PackageOption, Program } from "./types";

/** Price per individual test in a package (a catalogue-derived value-for-money figure). */
export const perTest = (p: PackageOption): number => (p.test_count > 0 ? p.price_inr / p.test_count : p.price_inr);

export function median(xs: number[]): number {
  if (xs.length === 0) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
}

export interface CatalogueSummary {
  count: number; medianPrice: number; fastingCount: number; noFastCount: number;
  cheapest: PackageOption; priciest: PackageOption; bestValue: PackageOption; mostTests: PackageOption;
}

export function summarize(pk: PackageOption[]): CatalogueSummary | null {
  if (pk.length === 0) return null;
  const by = (f: (p: PackageOption) => number, dir: 1 | -1) => [...pk].sort((a, b) => dir * (f(a) - f(b)))[0]!;
  const fasting = pk.filter((p) => p.fasting_required).length;
  return {
    count: pk.length, medianPrice: median(pk.map((p) => p.price_inr)), fastingCount: fasting, noFastCount: pk.length - fasting,
    cheapest: by((p) => p.price_inr, 1), priciest: by((p) => p.price_inr, -1), bestValue: by(perTest, 1), mostTests: by((p) => p.test_count, -1),
  };
}

export function categoryCounts(programs: Program[]): [string, number][] {
  const m = new Map<string, number>();
  programs.forEach((p) => m.set(p.category, (m.get(p.category) ?? 0) + 1));
  return [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

const SLOT = /^\s*(\d{1,2}):(\d{2})\s*(AM|PM)\s*$/i;
const clock = (mins: number): string => {
  const h24 = Math.floor(mins / 60) % 24, m = mins % 60;
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return `${String(h12).padStart(2, "0")}:${String(m).padStart(2, "0")} ${h24 < 12 ? "AM" : "PM"}`;
};

/** Latest time to stop eating so a fasting window of `hours` is complete at `slot` (e.g. "10:30 AM"). */
export function lastMeal(slot: string, hours: number): { time: string; previousDay: boolean } | null {
  const m = SLOT.exec(slot);
  if (!m) return null;
  let h = Number(m[1]) % 12; if (m[3]!.toUpperCase() === "PM") h += 12;
  const start = h * 60 + Number(m[2]);
  const t = start - hours * 60;
  return { time: clock(((t % 1440) + 1440) % 1440), previousDay: t < 0 };
}

/** Match a session booking (which carries only a name) to its catalogue package. */
export const packageFor = (b: BookingItem, pk: PackageOption[]): PackageOption | undefined => pk.find((p) => p.name === b.package_name);
