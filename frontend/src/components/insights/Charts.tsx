import { useEffect, useRef, useState, type ReactNode } from "react";
import { BarChart3, Table2, type LucideIcon } from "lucide-react";

/* Charts are plain HTML/CSS so they stay accessible, responsive and light. Palette validated with the dataviz skill's
   validate_palette.js: indigo + orange pass all hard gates (adjacent CVD dE 9.2, normal-vision dE 27.6). */

export interface BarRow { id: string; label: string; value: number; text: string; series?: "a" | "b"; tip?: ReactNode }

export function BarChart({ rows, label, max }: { rows: BarRow[]; label: string; max?: number }) {
  const [active, setActive] = useState<string | null>(null);
  const top = max ?? Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="vbars" aria-label={label}>
      {rows.map((r, i) => (
        <li key={r.id} className={`vbar${active === r.id ? " on" : ""}`} tabIndex={0}
          onMouseEnter={() => setActive(r.id)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(r.id)} onBlur={() => setActive(null)}>
          <span className="vb-label" title={r.label}>{r.label}</span>
          <span className="vb-track"><i className={`vb-fill ${r.series ?? "a"}`} style={{ width: `${Math.max(2, (r.value / top) * 100)}%`, animationDelay: `${i * 35}ms` }} /></span>
          <span className="vb-val num">{r.text}</span>
          {active === r.id && r.tip && <div className="vb-tip" role="tooltip">{r.tip}</div>}
        </li>
      ))}
    </ul>
  );
}

export interface LegendItem { label: string; series: "a" | "b" }

/** A chart with a title, optional legend (always shown for 2+ series) and a Chart/Table switch so no information is chart-only. */
export function ChartCard({ title, subtitle, legend, table, children, testId }: {
  title: string; subtitle?: string; legend?: LegendItem[]; table: { head: string[]; body: string[][] }; children: ReactNode; testId?: string;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <section className="card chart-card" aria-label={title} data-testid={testId}>
      <header className="cc-head">
        <div><h3>{title}</h3>{subtitle && <p className="muted">{subtitle}</p>}</div>
        <div className="cc-switch" role="group" aria-label={`${title}: view`}>
          <button aria-pressed={view === "chart"} onClick={() => setView("chart")} title="Chart view"><BarChart3 size={15} aria-hidden="true" /><span className="sr-only">Chart</span></button>
          <button aria-pressed={view === "table"} onClick={() => setView("table")} title="Table view"><Table2 size={15} aria-hidden="true" /><span className="sr-only">Table</span></button>
        </div>
      </header>
      {legend && legend.length > 1 && (
        <ul className="cc-legend" aria-label="Legend">{legend.map((l) => <li key={l.label}><i className={`sw ${l.series}`} />{l.label}</li>)}</ul>
      )}
      {view === "chart" ? children : (
        <div className="cc-table"><table><thead><tr>{table.head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
          <tbody>{table.body.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table></div>
      )}
    </section>
  );
}

const reduced = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Headline number with a short count-up (instant under reduced motion). */
export function Stat({ icon: Icon, label, value, format = (n) => String(Math.round(n)), hint, tone = "brand" }: {
  icon: LucideIcon; label: string; value: number; format?: (n: number) => string; hint?: ReactNode; tone?: "brand" | "warm" | "calm";
}) {
  const [shown, setShown] = useState(reduced() ? value : 0);
  const from = useRef(0);
  useEffect(() => {
    if (reduced()) { setShown(value); return; }
    const start = performance.now(), a = from.current, dur = 700; let id = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / dur), e = 1 - Math.pow(1 - t, 3);
      setShown(a + (value - a) * e);
      if (t < 1) id = requestAnimationFrame(tick); else from.current = value;
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [value]);
  return (
    <div className={`stat ${tone}`} data-testid="stat">
      <span className="stat-ic"><Icon size={19} aria-hidden="true" /></span>
      <span className="stat-label">{label}</span>
      <b className="stat-val num" aria-label={`${label}: ${format(value)}`}>{format(shown)}</b>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}

/** A single ratio against its whole (e.g. fasting packages out of all packages). */
export function Meter({ part, whole, label }: { part: number; whole: number; label: string }) {
  const pct = whole > 0 ? (part / whole) * 100 : 0;
  return (
    <div className="meter" role="img" aria-label={`${label}: ${part} of ${whole}`}>
      <div className="meter-track"><i style={{ width: `${pct}%` }} /></div>
      <div className="meter-cap"><span>{label}</span><b className="num">{part} of {whole}</b></div>
    </div>
  );
}
