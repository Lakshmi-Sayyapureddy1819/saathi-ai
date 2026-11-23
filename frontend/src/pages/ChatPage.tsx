import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown, BookOpen, Database, FlaskConical, History, MessageCircle, MessageSquarePlus, ShieldCheck, Sparkles, Stethoscope, Waves } from "lucide-react";
import { useApp } from "../app/context";
import { goto } from "../app/routes";
import { SessionGate } from "../components/SessionGate";
import { BookingWizard } from "../components/booking/BookingWizard";
import { ChatComposer } from "../components/chat/ChatComposer";
import { MimiAvatar, type MimiState } from "../components/mimi/MimiAvatar";
import { ChatMessage } from "../components/chat/ChatMessage";
import { Banner, Button, ConfirmationDialog, Drawer, IconButton, StatusBadge } from "../components/ui";
import { statusLabel } from "../format";
import type { GroundingModeName } from "../types";

const PROMPTS: { icon: typeof Sparkles; label: string; text: string }[] = [
  { icon: Sparkles, label: "Help me understand my wellness routine", text: "Help me understand my wellness routine" },
  { icon: FlaskConical, label: "I want to book a blood test", text: "I want to book a blood test" },
  { icon: Stethoscope, label: "Can you explain this lab package?", text: "Can you explain the Thyroid Screening Profile lab package?" },
  { icon: Waves, label: "I need help with relaxation", text: "I need help with relaxation" },
];

const MODES: { id: GroundingModeName; short: string; name: string; icon: typeof BookOpen; blurb: string; prompts: string[] }[] = [
  { id: "mode_a_rag", short: "A", name: "Library search", icon: BookOpen,
    blurb: "Agentic RAG: Mimi decides what to look up in the wellness library, searches (and re-searches), and cites the documents she used.",
    prompts: ["Tell me about Kapalbhati", "Mujhe garmi mein kya khana chahiye?", "What is Viparita Karani?", "What is my blood group?"] },
  { id: "mode_b_facts", short: "B", name: "My records", icon: Database,
    blurb: "No retrieval: Mimi calls backend tools (profile, bookings, schedule, catalogue) and answers only from those facts, otherwise \"I don't have that information\".",
    prompts: ["What programs am I enrolled in?", "Which lab tests have I already booked?", "Do I have a checkup due soon?", "Tell me about Kapalbhati"] },
];

function ModeSwitch({ mode, onChange, disabled }: { mode: GroundingModeName; onChange: (m: GroundingModeName) => void; disabled: boolean }) {
  return (
    <div className="mode-switch" role="radiogroup" aria-label="Answer mode" data-testid="mode-switch">
      {MODES.map((m) => { const I = m.icon; const on = m.id === mode; return (
        <button key={m.id} role="radio" aria-checked={on} className={on ? "on" : ""} disabled={disabled} title={m.blurb}
          data-testid={`mode-${m.id}`} onClick={() => { if (!on) onChange(m.id); }}>
          <I size={14} aria-hidden="true" /><b>{m.short}</b><span>{m.name}</span>
        </button>); })}
    </div>
  );
}

function History_({ onNew }: { onNew: () => void }) {
  const { s } = useApp();
  const first = s.messages.find((m) => m.role === "user");
  return (
    <div className="hist">
      <Button variant="primary" icon={MessageSquarePlus} block onClick={onNew} data-testid="new-conversation">New conversation</Button>
      <h3 className="label hist-h">This session</h3>
      <div className="hist-item active" aria-current="true">
        <MessageCircle size={16} aria-hidden="true" />
        <div><b>{first ? (first.text.length > 34 ? `${first.text.slice(0, 34)}…` : first.text) : "New conversation"}</b>
          <span className="muted">{s.messages.filter((m) => m.role === "user").length} message(s) · active</span></div>
      </div>
      <p className="help hist-note">Past conversations aren't stored in this build. Sessions live in server memory and end when you end the session, so there is nothing to search yet.</p>
    </div>
  );
}

function Inner() {
  const { s, maxChars, begin } = useApp();
  const session = s.session!;
  const st = statusLabel(session);
  const paused = session.status === "awaiting_coordinator";
  const log = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);
  const [histOpen, setHistOpen] = useState(false);
  const [confirmNew, setConfirmNew] = useState(false);
  const [dictating, setDictating] = useState(false); // user is speaking into the composer

  const scrollDown = useCallback((smooth = true) => { const el = log.current; if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" }); }, []);
  useEffect(() => { if (atBottom) scrollDown(); }, [s.messages.length, s.busy, session.booking.stage, session.handoff.status, atBottom, scrollDown]);
  const onScroll = () => { const el = log.current; if (el) setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80); };

  const newConversation = async () => {
    setConfirmNew(false); setHistOpen(false);
    const id = session.member.member_id;
    await s.end();
    await begin(id);
  };
  const requestNew = () => (s.messages.length > 0 ? setConfirmNew(true) : undefined);
  const mode: GroundingModeName = session.grounding_mode ?? "mode_a_rag";
  const modeInfo = MODES.find((m) => m.id === mode)!;
  const showWizard = session.booking.stage !== "idle" || session.handoff.status !== "none";
  const tone = st.tone === "ok" ? "success" : st.tone === "wait" ? "warn" : st.tone === "alert" ? "danger" : "neutral";

  return (
    <div className="chat-layout">
      <aside className="chat-hist card" aria-label="Conversations"><History_ onNew={requestNew} /></aside>

      <section className="chat-main" aria-label="Conversation">
        <header className="chat-head">
          <div className="ch-title">
            <MimiAvatar size={46} state={s.busy ? "thinking" : s.error ? "error" : dictating ? "listening" : "idle"} />
            <div><b>Mimi</b><span className="muted">Your wellness &amp; lab booking companion</span></div>
          </div>
          <div className="ch-actions">
            <ModeSwitch mode={mode} onChange={(m) => void s.setGrounding(m)} disabled={s.busy || paused} />
            <StatusBadge tone={tone}>{paused ? "Paused for coordinator" : session.triage_status === "RED_CRISIS" ? "Emergency guidance shown" : "Online"}</StatusBadge>
            <IconButton icon={History} label="Conversations" className="only-mobile" onClick={() => setHistOpen(true)} />
            <IconButton icon={MessageSquarePlus} label="New conversation" bordered onClick={requestNew} disabled={s.messages.length === 0} />
          </div>
        </header>

        <div className="chat-log" ref={log} onScroll={onScroll} role="log" aria-live="polite" aria-relevant="additions" aria-label="Messages" data-testid="chat-log">
          {!s.messages.some((m) => m.role !== "system") && (
            <motion.div className="chat-empty" data-testid="chat-empty" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <MimiAvatar size={132} state={dictating ? "listening" : "idle"} className="ce-mimi mimi-hero" />
              <h2>Namaste, {session.member.name.split(" ")[0]}. How can I help today?</h2>
              <p className="muted">Ask about yoga, sleep, diet and stress, or book a lab test. You can write in English, Hindi or Hinglish.</p>
              <div className="prompt-grid">
                {PROMPTS.map((p) => { const I = p.icon; return (
                  <button key={p.label} className="prompt" disabled={s.busy || paused} onClick={() => void s.send(p.text)}><I size={18} aria-hidden="true" /><span>{p.label}</span></button>); })}
              </div>
              <p className="muted demo-label" data-testid="demo-prompts-label">Try these in <b>{modeInfo.name}</b> mode (switch the mode at the top to compare):</p>
              <div className="prompt-grid">
                {modeInfo.prompts.map((t) => (
                  <button key={t} className="prompt" data-testid="mode-prompt" disabled={s.busy || paused} onClick={() => void s.send(t)}><modeInfo.icon size={18} aria-hidden="true" /><span>{t}</span></button>))}
              </div>
            </motion.div>
          )}
          {s.messages.map((m, i) => {
            // only the newest assistant message animates; older ones stay still to keep the page light
            const latest = m.role === "assistant" && !s.messages.slice(i + 1).some((x) => x.role === "assistant");
            const mood: MimiState | undefined = latest ? (m.kind === "booking_confirmed" ? "success" : "idle") : undefined;
            return <ChatMessage key={`${m.id}-${i}`} m={m} onRetry={s.retry} onDismiss={s.dismissError} mood={mood} />;
          })}

          <AnimatePresence>
            {s.busy && (
              <motion.div className="msg assistant" data-testid="typing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <MimiAvatar size={40} state="thinking" />
                <div className="bubble assistant typing" role="status" aria-label="Mimi is typing"><i /><i /><i /></div>
              </motion.div>
            )}
          </AnimatePresence>

          {showWizard && (
            <div className="inline-wizard" data-testid="booking-panel">
              <BookingWizard session={session} busy={s.busy} paused={paused} onSend={(t) => void s.send(t)} />
            </div>
          )}
        </div>

        <AnimatePresence>
          {!atBottom && (
            <motion.button className="to-latest" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} onClick={() => scrollDown()} aria-label="Scroll to latest message">
              <ArrowDown size={16} aria-hidden="true" /> Latest
            </motion.button>
          )}
        </AnimatePresence>

        {s.error && (
          <div className="banner err send-error" role="alert" data-testid="send-error">
            <div className="grow"><b>Message not sent.</b> {s.error.message} Your text is kept; try again, or check your connection first.</div>
            <Button size="sm" onClick={s.retry}>Retry</Button><Button size="sm" variant="ghost" onClick={s.dismissError}>Dismiss</Button>
          </div>
        )}
        <ChatComposer onListening={setDictating} busy={s.busy} paused={paused} maxChars={maxChars} onSend={(t) => void s.send(t)} />
      </section>

      <aside className="chat-ctx" aria-label="Conversation context">
        <div className="card" data-testid="mode-card">
          <div className="card-title"><modeInfo.icon size={18} aria-hidden="true" />Answer mode: {modeInfo.short} · {modeInfo.name}</div>
          <p className="muted">{modeInfo.blurb}</p>
        </div>
        <div className="card">
          <div className="card-title"><ShieldCheck size={18} aria-hidden="true" />Safety</div>
          <p className="muted">Every message passes a fixed safety check before any AI model sees it. Red-flag symptoms trigger emergency guidance instead of a chat answer.</p>
        </div>
        <div className="card">
          <div className="card-title"><FlaskConical size={18} aria-hidden="true" />Bookings</div>
          <p className="muted">{session.bookings.length ? `${session.bookings.length} confirmed in this session.` : "No confirmed bookings in this session."}</p>
          <Button size="sm" variant="soft" style={{ marginTop: 10 }} onClick={() => goto("labs")}>Open lab tests</Button>
        </div>
        {paused && <Banner tone="warn">Messaging is paused while a care coordinator reviews your request.</Banner>}
      </aside>

      <Drawer open={histOpen} onClose={() => setHistOpen(false)} title="Conversations"><History_ onNew={requestNew} /></Drawer>
      <ConfirmationDialog open={confirmNew} title="Start a new conversation?" confirmLabel="Clear and start new" danger onConfirm={() => void newConversation()} onCancel={() => setConfirmNew(false)}>
        This ends the current conversation and clears it from the server. Confirmed bookings stay in the booking system, but they will no longer be listed here.
      </ConfirmationDialog>
    </div>
  );
}

export function ChatPage() {
  return <SessionGate to="chat" what="Mimi, the chat assistant"><Inner /></SessionGate>;
}
