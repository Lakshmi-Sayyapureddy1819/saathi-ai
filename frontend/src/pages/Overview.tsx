import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, AudioLines, BookOpen, CalendarCheck, FlaskConical, HeartHandshake, MessageCircle, Sparkles } from "lucide-react";
import { api } from "../api";
import { useApp } from "../app/context";
import { goto, type RouteId } from "../app/routes";
import { Banner, Button, Card, EmptyState, Skeleton, StatusBadge } from "../components/ui";
import { MimiAvatar } from "../components/mimi/MimiAvatar";
import { StartCard } from "../components/SessionGate";
import { BookingCard } from "../components/booking/BookingCard";
import type { Program } from "../types";

const container = { hidden: {}, show: { transition: { staggerChildren: 0.05 } } };
const item = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { duration: 0.25 } } };

const greeting = (): string => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };

const ACTIONS: { id: RouteId; label: string; hint: string; icon: typeof Sparkles }[] = [
  { id: "voice", label: "Talk to Mimi", hint: "Hands-free voice", icon: AudioLines },
  { id: "chat", label: "Start a chat", hint: "Ask anything wellness", icon: MessageCircle },
  { id: "labs", label: "Book a lab test", hint: "Pick package and slot", icon: FlaskConical },
  { id: "bookings", label: "View bookings", hint: "Status and details", icon: CalendarCheck },
  { id: "support", label: "Care support", hint: "Reach a coordinator", icon: HeartHandshake },
];

export function Overview() {
  const { s, cfg, cfgError, begin, memberId } = useApp();
  const [programs, setPrograms] = useState<Program[] | null>(null);
  useEffect(() => { api.programs().then(setPrograms).catch(() => setPrograms([])); }, []);
  const categories = useMemo(() => {
    const m = new Map<string, number>();
    (programs ?? []).forEach((p) => m.set(p.category, (m.get(p.category) ?? 0) + 1));
    return [...m.entries()];
  }, [programs]);

  const session = s.session;
  const first = session?.member.name.split(" ")[0];
  const go = (id: RouteId) => { if (session) goto(id); else if (memberId) void begin(memberId, { to: id }); };
  const today = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });
  const userMsgs = (session?.messages ?? []).filter((m) => m.role === "user").slice(-3).reverse();
  const handoffMsgs = (session?.messages ?? []).filter((m) => m.kind === "handoff" || m.kind === "handoff_resolved").slice(-2).reverse();

  return (
    <motion.div className="stack" variants={container} initial="hidden" animate="show">
      {s.notice && <Banner tone="warn" data-testid="notice" action={<button className="link-btn" onClick={() => s.setNotice(null)}>Dismiss</button>}>{s.notice}</Banner>}
      {cfgError && <Banner tone="err" role="alert" data-testid="load-error" action={<button className="link-btn" onClick={() => location.reload()}>Reload</button>}>{cfgError}</Banner>}
      {cfg && !cfg.llm_configured && (
        <Banner tone="info" data-testid="mock-banner">
          <b>Demo mode.</b> No AI model key is configured on the server, so wellness answers appear as <code>[MOCK]</code> text.
          Booking, safety and routing do not use an AI model and work normally.
        </Banner>
      )}

      <motion.section variants={item} className="welcome">
        <div>
          <p className="eyebrow">{today}</p>
          <h1 className="display">{session ? `${greeting()}, ${first}.` : "Care that listens, in English and Hinglish."}</h1>
          <p className="lead">{session ? "How are you feeling today? Ask about yoga, sleep and diet, or book a lab test. I'm here to help, not to diagnose." : "Ask about yoga, diet and sleep, or book a lab test. Saathi is an AI assistant, not a doctor."}</p>
          <div className="row-gap">
            <Button variant="primary" size="lg" icon={MessageCircle} onClick={() => go("chat")} disabled={!session && !memberId}>Start a conversation</Button>
            <Button size="lg" icon={AudioLines} onClick={() => go("voice")} disabled={!session && !memberId}>Talk to Mimi</Button>
          </div>
        </div>
        {!session && <StartCard compact title="Choose who you are" />}
      </motion.section>

      <motion.section variants={item} aria-labelledby="qa">
        <h2 id="qa" className="sec-title">Quick actions</h2>
        <div className="qa-grid">
          {ACTIONS.map((a) => { const I = a.icon; return (
            <button key={a.id} className="qa" onClick={() => go(a.id)} disabled={!session && !memberId}>
              <span className="qa-ic"><I size={20} aria-hidden="true" /></span><b>{a.label}</b><span className="muted">{a.hint}</span>
            </button>); })}
        </div>
      </motion.section>

      <div className="grid-2">
        <motion.section variants={item} className="assistant-card" aria-label="Saathi assistant">
          <MimiAvatar size={120} state="idle" />
          <div className="ac-body">
            <StatusBadge tone={cfg ? "success" : cfgError ? "danger" : "neutral"}>{cfg ? "Available now" : cfgError ? "Server unreachable" : "Checking…"}</StatusBadge>
            <h2>Your Saathi assistant</h2>
            <p>{cfg?.llm_configured === false ? "Running with sample responses (no AI model key on the server). Safety, booking and routing are fully live." : "Ask in English, Hindi or Hinglish. Every message passes a fixed safety check first."}</p>
            <div className="row-gap">
              <Button variant="soft" icon={AudioLines} onClick={() => go("voice")} disabled={!session && !memberId} className="on-dark">Start voice conversation</Button>
              <Button variant="ghost" icon={MessageCircle} onClick={() => go("chat")} disabled={!session && !memberId} className="on-dark ghost-dark">Start text conversation</Button>
            </div>
          </div>
        </motion.section>

        <motion.section variants={item} aria-label="Booking overview">
          <Card>
            <div className="card-title"><CalendarCheck size={18} aria-hidden="true" />Upcoming bookings
              <button className="link-btn push" onClick={() => goto("bookings")}>View all</button></div>
            {!session ? <EmptyState icon={CalendarCheck} title="No session yet" text="Start a session to see bookings made in it." />
              : session.bookings.length === 0 && session.handoff.status === "none"
                ? <EmptyState icon={CalendarCheck} title="No bookings yet" text="Bookings you confirm with Saathi appear here, straight from the booking system."
                  action={<Button size="sm" variant="soft" onClick={() => goto("labs")}>Book a lab test</Button>} />
                : <div className="stack-sm">
                  {session.handoff.status !== "none" && session.booking.package && <BookingCard kind="handoff" handoff={session.handoff} name={session.booking.package.name} date={session.booking.date_label ?? ""} slot={session.booking.slot ?? ""} compact />}
                  {session.bookings.slice(0, 3).map((b) => <BookingCard key={b.booking_id} kind="confirmed" booking={b} compact />)}
                </div>}
          </Card>
        </motion.section>
      </div>

      <div className="grid-2">
        <motion.section variants={item} aria-label="Recent activity">
          <Card>
            <div className="card-title"><Sparkles size={18} aria-hidden="true" />Recent activity</div>
            {!session || (userMsgs.length === 0 && handoffMsgs.length === 0 && session.bookings.length === 0)
              ? <EmptyState icon={MessageCircle} title="Nothing yet" text="Your conversation, booking and care-team updates will show here." />
              : <ul className="activity">
                {userMsgs.map((m) => <li key={`m${m.id}`}><MessageCircle size={16} aria-hidden="true" /><span>You asked: “{m.text.length > 70 ? `${m.text.slice(0, 70)}…` : m.text}”</span></li>)}
                {session.bookings.map((b) => <li key={b.booking_id}><CalendarCheck size={16} aria-hidden="true" /><span>Booking {b.booking_id} confirmed for {b.date}, {b.slot}</span></li>)}
                {handoffMsgs.map((m) => <li key={`h${m.id}`}><HeartHandshake size={16} aria-hidden="true" /><span>{m.kind === "handoff" ? "Care coordinator requested" : "Coordinator update"}: {m.text.slice(0, 80)}</span></li>)}
              </ul>}
          </Card>
        </motion.section>

        <motion.section variants={item} aria-label="Wellness library">
          <Card>
            <div className="card-title"><BookOpen size={18} aria-hidden="true" />Wellness library<StatusBadge tone="info" icon={false}>Educational</StatusBadge></div>
            <p className="muted" style={{ marginBottom: 12 }}>Program content Saathi draws on. General education only, never a diagnosis. We don't show personal health measurements because none are stored.</p>
            {programs === null ? <div className="stack-sm"><Skeleton h={28} /><Skeleton h={28} w="70%" /></div>
              : categories.length === 0 ? <p className="muted">The program library is unavailable right now.</p>
                : <div className="chips" data-testid="program-cats">{categories.map(([c, n]) => <span key={c} className="chip static">{c} · {n}</span>)}</div>}
            <Button variant="ghost" size="sm" icon={ArrowRight} onClick={() => goto("insights")} style={{ marginTop: 12 }}>Explore insights</Button>
          </Card>
        </motion.section>
      </div>
    </motion.div>
  );
}
