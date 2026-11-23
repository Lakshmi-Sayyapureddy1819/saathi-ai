import { useCallback, useEffect, useMemo, useState } from "react";
import { FlaskConical, RefreshCw, SearchX } from "lucide-react";
import { api } from "../api";
import { useApp } from "../app/context";
import { BookingWizard } from "../components/booking/BookingWizard";
import { PackageCard } from "../components/booking/BookingFlow";
import { StartCard } from "../components/SessionGate";
import { Banner, Button, Card, EmptyState, PageHeader, SearchBar, Skeleton, Tabs } from "../components/ui";
import type { PackageOption } from "../types";

type Filter = "all" | "fasting" | "nofast";

export function LabsPage() {
  const { s, begin, memberId } = useApp();
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [list, setList] = useState<PackageOption[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const load = useCallback(() => { setList(null); setErr(null); setNonce((n) => n + 1); }, []);
  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api.packages(q).then((r) => { if (live) setList(r); }).catch((e: Error) => { if (live) setErr(e.message); });
    }, q ? 200 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [q, nonce]);

  const shown = useMemo(() => (list ?? []).filter((p) => filter === "all" || (filter === "fasting" ? p.fasting_required : !p.fasting_required)), [list, filter]);
  const session = s.session;
  const paused = session?.status === "awaiting_coordinator";
  const inFlow = !!session && (session.booking.stage !== "idle" || session.handoff.status !== "none" || session.bookings.length > 0 && session.messages.at(-1)?.kind === "booking_confirmed");

  const book = (p: PackageOption) => {
    if (session) void s.send(`Book ${p.name}`);
    else if (memberId) void begin(memberId, { first: `Book ${p.name}`, to: "labs" });
  };
  const busy = s.busy || paused || s.starting;

  return (
    <div className="stack">
      <PageHeader eyebrow="Lab tests" title="Find and book a lab test" subtitle="Prices and fasting requirements come straight from the lab catalogue. Time slots are live and shown once you choose a test." />

      {!session && <div className="grid-2 gate-inline"><Banner tone="info">You can browse without signing in. To book, Saathi needs a member profile: pick one on the right (demo members), or just press Book on a test.</Banner><StartCard compact title="Choose who you are" to="labs" /></div>}

      {session && inFlow && (
        <Card className="wizard-card" data-testid="booking-panel">
          <div className="card-title"><FlaskConical size={18} aria-hidden="true" />Your booking</div>
          <BookingWizard session={session} busy={s.busy} paused={!!paused} onSend={(t) => void s.send(t)} />
        </Card>
      )}
      {session && !inFlow && (
        <Banner tone="info" data-testid="no-booking">No booking in progress. Choose a test below to begin. Booking is a 6-step flow: package, date, time, review, confirm, result.</Banner>
      )}

      <div className="toolbar">
        <SearchBar label="Search tests and packages" value={q} onChange={setQ} data-testid="pkg-search" />
        <Tabs label="Filter by fasting" value={filter} onChange={setFilter}
          tabs={[{ id: "all", label: "All" }, { id: "fasting", label: "Fasting required" }, { id: "nofast", label: "No fasting" }]} />
      </div>

      {err ? (
        <EmptyState icon={RefreshCw} title="Couldn't load the catalogue" text={err} action={<Button onClick={load} icon={RefreshCw}>Try again</Button>} role="alert" />
      ) : list === null ? (
        <ul className="pkg-grid" aria-busy="true" aria-label="Loading packages">{Array.from({ length: 6 }, (_, i) => <li key={i} className="pkg-card"><Skeleton w={44} h={44} /><div className="pkg-body"><Skeleton h={16} w="70%" /><Skeleton h={12} w="40%" style={{ marginTop: 8 }} /></div></li>)}</ul>
      ) : shown.length === 0 ? (
        <EmptyState icon={SearchX} title="No packages match" text={q ? `Nothing matches “${q}” with this filter. Try a different word such as “thyroid”, “sugar” or “vitamin”.` : "No packages in this filter."} action={<Button onClick={() => { setQ(""); setFilter("all"); }}>Clear filters</Button>} />
      ) : (
        <ul className="pkg-grid" data-testid="pkg-list">{shown.map((p) => <PackageCard key={p.package_id} p={p} actionLabel="Book" disabled={busy} onPick={book} />)}</ul>
      )}
    </div>
  );
}
