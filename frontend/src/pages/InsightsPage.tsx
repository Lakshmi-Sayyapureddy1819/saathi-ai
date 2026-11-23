import { useEffect, useMemo, useState } from "react";
import { BookOpen, CalendarCheck, HeartPulse, Layers, RefreshCw, SearchX, Tag, TrendingDown, Trophy, Utensils } from "lucide-react";
import { api } from "../api";
import { useApp } from "../app/context";
import { BarChart, ChartCard, Meter, Stat, type BarRow } from "../components/insights/Charts";
import { ComparePanel, FastingPlanner, PrepList } from "../components/insights/Tools";
import { Banner, Button, Card, EmptyState, PageHeader, SearchBar, Skeleton, Tabs } from "../components/ui";
import { formatINR } from "../format";
import { categoryCounts, perTest, summarize } from "../insights";
import type { PackageOption, Program } from "../types";

type Tab = "dashboard" | "plan" | "library";

export function InsightsPage() {
  const { s, ask, bookPackage } = useApp();
  const [tab, setTab] = useState<Tab>("dashboard");
  const [packages, setPackages] = useState<PackageOption[] | null>(null);
  const [programs, setPrograms] = useState<Program[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("All");

  const load = () => {
    setErr(null); setPackages(null); setPrograms(null);
    api.packages("").then(setPackages).catch((e: Error) => setErr(e.message));
    api.programs().then(setPrograms).catch((e: Error) => setErr(e.message));
  };
  useEffect(load, []);

  const sum = useMemo(() => (packages ? summarize(packages) : null), [packages]);
  const cats = useMemo(() => categoryCounts(programs ?? []), [programs]);
  const session = s.session;
  const busy = s.busy || session?.status === "awaiting_coordinator";

  const tip = (p: PackageOption) => <><b>{p.name}</b><span>{formatINR(p.price_inr)} · {p.test_count} tests</span><span>{formatINR(Math.round(perTest(p)))} per test</span><span>{p.fasting_required ? `Fasting ${p.fasting_hours}h` : "No fasting"}</span></>;
  const valueRows: BarRow[] = useMemo(() => [...(packages ?? [])].sort((a, b) => perTest(a) - perTest(b))
    .map((p) => ({ id: p.package_id, label: p.name, value: perTest(p), text: formatINR(Math.round(perTest(p))), tip: tip(p) })), [packages]);
  const priceRows: BarRow[] = useMemo(() => [...(packages ?? [])].sort((a, b) => b.price_inr - a.price_inr)
    .map((p) => ({ id: p.package_id, label: p.name, value: p.price_inr, text: formatINR(p.price_inr), series: p.fasting_required ? "b" as const : "a" as const, tip: tip(p) })), [packages]);
  const catRows: BarRow[] = cats.map(([c, n]) => ({ id: c, label: c, value: n, text: String(n) }));

  const libCats = ["All", ...cats.map(([c]) => c)];
  const shown = (programs ?? []).filter((p) => (cat === "All" || p.category === cat) && p.title.toLowerCase().includes(q.toLowerCase()));
  const grouped = useMemo(() => { const m = new Map<string, Program[]>(); shown.forEach((p) => m.set(p.category, [...(m.get(p.category) ?? []), p])); return [...m.entries()]; }, [shown]);

  return (
    <div className="stack">
      <PageHeader eyebrow="Health insights" title="Insights & planning"
        subtitle="Practical numbers from the real lab catalogue and program library, plus tools to compare tests and prepare for them." />
      <Banner tone="info">Everything here is calculated from data the backend actually holds: the lab catalogue, the program library and your bookings in this session. No personal health measurements are stored, so none are shown. General information only, never a diagnosis.</Banner>

      <Tabs label="Insights sections" value={tab} onChange={setTab} tabs={[{ id: "dashboard", label: "Dashboard" }, { id: "plan", label: "Compare & plan" }, { id: "library", label: "Wellness library" }]} />

      {err && <EmptyState icon={RefreshCw} title="Couldn't load the data" text={err} action={<Button icon={RefreshCw} onClick={load}>Try again</Button>} role="alert" />}

      {!err && tab === "dashboard" && (
        <div className="stack" data-testid="insights-dashboard">
          <div className="stat-row">
            {sum ? (<>
              <Stat icon={Layers} label="Lab packages" value={sum.count} hint={`${sum.noFastCount} need no fasting`} />
              <Stat icon={Tag} label="Median price" value={sum.medianPrice} format={(n) => formatINR(Math.round(n))} hint={`${formatINR(sum.cheapest.price_inr)} to ${formatINR(sum.priciest.price_inr)}`} tone="warm" />
              <Stat icon={Utensils} label="Need fasting" value={sum.fastingCount} hint={`${Math.round((sum.fastingCount / sum.count) * 100)}% of packages`} tone="calm" />
              <Stat icon={session ? CalendarCheck : BookOpen} label={session ? "Your bookings" : "Programs"} value={session ? session.bookings.length : (programs?.length ?? 0)}
                hint={session ? "confirmed this session" : "in the library"} />
            </>) : [0, 1, 2, 3].map((i) => <div key={i} className="stat"><Skeleton h={14} w="50%" /><Skeleton h={30} w="40%" style={{ marginTop: 10 }} /></div>)}
          </div>

          <div className="grid-2">
            {packages ? (
              <ChartCard title="Best value: price per test" subtitle="Package price divided by the number of tests. Lower is better value." testId="chart-value"
                table={{ head: ["Package", "Price per test", "Price", "Tests"], body: [...packages].sort((a, b) => perTest(a) - perTest(b)).map((p) => [p.name, formatINR(Math.round(perTest(p))), formatINR(p.price_inr), String(p.test_count)]) }}>
                <BarChart rows={valueRows} label="Price per test by package" />
              </ChartCard>
            ) : <Card><Skeleton h={240} /></Card>}
            {packages ? (
              <ChartCard title="Package price" subtitle="Colour shows whether the test needs fasting." testId="chart-price"
                legend={[{ label: "No fasting", series: "a" }, { label: "Fasting required", series: "b" }]}
                table={{ head: ["Package", "Price", "Fasting"], body: [...packages].sort((a, b) => b.price_inr - a.price_inr).map((p) => [p.name, formatINR(p.price_inr), p.fasting_required ? `${p.fasting_hours} hours` : "No"]) }}>
                <BarChart rows={priceRows} label="Package price, with fasting requirement" />
              </ChartCard>
            ) : <Card><Skeleton h={240} /></Card>}
          </div>

          <div className="grid-2">
            <Card data-testid="highlights">
              <div className="card-title"><Trophy size={18} aria-hidden="true" />Catalogue highlights</div>
              {sum ? (
                <ul className="hl">
                  {[
                    { k: "Best value per test", p: sum.bestValue, v: `${formatINR(Math.round(perTest(sum.bestValue)))} per test`, icon: TrendingDown },
                    { k: "Lowest price", p: sum.cheapest, v: formatINR(sum.cheapest.price_inr), icon: Tag },
                    { k: "Most tests", p: sum.mostTests, v: `${sum.mostTests.test_count} tests`, icon: Layers },
                    { k: "Highest price", p: sum.priciest, v: formatINR(sum.priciest.price_inr), icon: Trophy },
                  ].map((h) => { const I = h.icon; return (
                    <li key={h.k}><span className="qa-ic"><I size={17} aria-hidden="true" /></span>
                      <div><span className="muted">{h.k}</span><b>{h.p.name}</b><span className="num">{h.v}</span></div>
                      <Button size="sm" variant="soft" disabled={!session || busy} onClick={() => bookPackage(h.p)} aria-label={`Book ${h.p.name}`}>Book</Button></li>); })}
                </ul>) : <Skeleton h={180} />}
              {sum && <div style={{ marginTop: 16 }}><Meter part={sum.fastingCount} whole={sum.count} label="Packages that need fasting" /></div>}
            </Card>
            {programs ? (
              <ChartCard title="Wellness program coverage" subtitle="How many programs the library has in each category." testId="chart-programs"
                table={{ head: ["Category", "Programs"], body: cats.map(([c, n]) => [c, String(n)]) }}>
                {catRows.length ? <BarChart rows={catRows} label="Programs per category" /> : <p className="muted">The program library is empty.</p>}
              </ChartCard>
            ) : <Card><Skeleton h={200} /></Card>}
          </div>

          {packages && <PrepList bookings={session?.bookings ?? []} packages={packages} />}
        </div>
      )}

      {!err && tab === "plan" && (
        <div className="stack" data-testid="insights-plan">
          {packages ? (<>
            <ComparePanel packages={packages} disabled={!session || busy} onBook={bookPackage} />
            <div className="grid-2"><FastingPlanner packages={packages} /><PrepList bookings={session?.bookings ?? []} packages={packages} /></div>
          </>) : <Card><Skeleton h={200} /></Card>}
          {!session && <p className="help">Booking buttons are available once you start a session from the Overview.</p>}
        </div>
      )}

      {!err && tab === "library" && (
        <div className="stack" data-testid="insights-library">
          <div className="toolbar">
            <SearchBar label="Search programs" value={q} onChange={setQ} />
            <div className="chips" role="group" aria-label="Category">
              {libCats.map((c) => <button key={c} className={`chip${cat === c ? " active" : ""}`} aria-pressed={cat === c} onClick={() => setCat(c)}>{c}</button>)}
            </div>
          </div>
          {programs === null ? <div className="grid-3">{Array.from({ length: 6 }, (_, i) => <Card key={i}><Skeleton h={18} w="60%" /><Skeleton h={12} w="35%" style={{ marginTop: 10 }} /></Card>)}</div>
            : shown.length === 0 ? <EmptyState icon={SearchX} title="No programs match" text="Try a different word or choose All." />
              : grouped.map(([c, items]) => (
                <section key={c} aria-label={c} className="stack-sm">
                  <h2 className="sec-title"><BookOpen size={18} aria-hidden="true" /> {c} <span className="muted num">{items.length}</span></h2>
                  <div className="grid-3">
                    {items.map((p) => (
                      <Card key={p.doc_id} interactive className="program">
                        <h3>{p.title}</h3>
                        <Button size="sm" variant="soft" icon={HeartPulse} disabled={!session || s.busy} onClick={() => ask(`Tell me about ${p.title}`)}
                          title={session ? undefined : "Start a session from the Overview to ask Saathi"}>Ask Saathi about this</Button>
                      </Card>
                    ))}
                  </div>
                </section>))}
        </div>
      )}
    </div>
  );
}
