import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, ArrowLeft, Ear, Info, MessageCircle, ShieldCheck } from "lucide-react";
import { useApp } from "../app/context";
import { goto } from "../app/routes";
import { SessionGate } from "../components/SessionGate";
import { BookingStepper, BookingSummary, flowPosition } from "../components/booking/BookingFlow";
import { ChatMessage } from "../components/chat/ChatMessage";
import { MimiAvatar } from "../components/mimi/MimiAvatar";
import { mimiFromVoice } from "../components/mimi/mimiState";
import { VoiceControls } from "../components/voice/VoiceControls";
import { VoiceOrb } from "../components/voice/VoiceOrb";
import { Button, StatusBadge } from "../components/ui";
import { lastBooking } from "../format";
import type { VoiceLang } from "../voice";
import { ERROR_COPY, STATE_COPY, useVoiceAssistant, type VoiceUiState } from "../voiceAssistant";

const TRY_SAYING = ["Namaste Saathi", "Mujhe thyroid test book karna hai", "Kal subah 10:30 baje", "Haan, confirm kar do"];

const TONE: Record<VoiceUiState, "brand" | "info" | "warn" | "danger" | "success" | "neutral"> = {
  idle: "neutral", connecting: "info", listening: "success", processing: "info", thinking: "info", speaking: "brand", interrupted: "warn", error: "danger", ended: "neutral",
};

function Inner() {
  const { s } = useApp();
  const session = s.session!;
  const paused = session.status === "awaiting_coordinator";
  const [lang, setLang] = useState<VoiceLang>("en-IN");
  const va = useVoiceAssistant({ session, busy: s.busy, paused, lang, send: (t, ch) => s.send(t, ch) });
  const copy = STATE_COPY[va.state];
  const transcriptList = useRef<HTMLDivElement>(null);
  const turns = va.phase === "off" ? [] : session.messages.slice(va.startIndex);
  // scroll only the transcript list, never the whole side column (that would hide the readback card)
  useEffect(() => { const el = transcriptList.current; if (el) el.scrollTop = el.scrollHeight; }, [turns.length]);

  const confirmed = lastBooking(session.messages);
  const pos = flowPosition(session.booking, confirmed !== null, session.handoff);
  const confirming = session.booking.stage === "confirming" && !paused;
  // Mimi celebrates for a few seconds when a booking becomes confirmed during this voice session.
  const [celebrate, setCelebrate] = useState(false);
  const wasConfirmed = useRef(confirmed !== null);
  useEffect(() => {
    const now = confirmed !== null;
    if (now && !wasConfirmed.current) { setCelebrate(true); const t = setTimeout(() => setCelebrate(false), 4000); wasConfirmed.current = now; return () => clearTimeout(t); }
    wasConfirmed.current = now;
  }, [confirmed]);
  const err = va.errorKind ? ERROR_COPY[va.errorKind] : null;
  const heard = va.interim;
  const active = va.phase === "on";

  return (
    <div className="voice-layout">
      <section className={`voice-stage vs-${va.state}`} aria-label="Voice conversation">
        <div className="vs-top">
          <Button variant="ghost" size="sm" icon={ArrowLeft} className="on-dark ghost-dark" onClick={() => { va.end(); goto("chat"); }} data-testid="voice-to-chat">Return to chat</Button>
          <label className="vs-lang"><span className="sr-only">Voice language</span>
            <select value={lang} onChange={(e) => setLang(e.target.value as VoiceLang)} disabled={active} aria-label="Voice language">
              <option value="en-IN">English / Hinglish (en-IN)</option>
              <option value="hi-IN">Hindi (hi-IN)</option>
            </select>
          </label>
        </div>

        <div className="vs-center">
          <VoiceOrb state={va.state} level={va.level} levelAvailable={va.levelAvailable}>
            <MimiAvatar size={200} state={mimiFromVoice(va.state, celebrate)} level={va.level} mouth={va.mouth} />
          </VoiceOrb>
          <motion.div key={va.state} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }} className="vs-status">
            <StatusBadge tone={TONE[va.state]} icon={false} data-testid="voice-state-badge">{copy.label}</StatusBadge>
            <h2 data-testid="voice-state-label">{va.phase === "off" ? "Namaste! How can I help you today?" : copy.label}</h2>
            <p>{va.note ?? copy.hint}</p>
          </motion.div>
          {/* The single, polite live region screen readers rely on for state changes. */}
          <div className="sr-only" role="status" aria-live="polite" data-testid="voice-live">{copy.label}. {va.note ?? copy.hint}</div>

          <AnimatePresence>
            {active && heard && va.state === "listening" && (
              <motion.p className="vs-heard" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="voice-heard">
                <Ear size={15} aria-hidden="true" /> Hearing: “{heard}”
              </motion.p>
            )}
          </AnimatePresence>
        </div>

        <VoiceControls state={va.state} phase={va.phase} muted={va.muted} listening={va.listening}
          onStart={() => void va.start()} onEnd={va.end} onMute={va.toggleMute} onInterrupt={va.interrupt} onMic={va.micTap} />

        <p className="vs-foot">
          {active && va.levelAvailable ? "Orb reacts to your live microphone level." : active ? "Live microphone level isn't available here, so the orb shows state only." : "State-driven visuals. Nothing is simulated."}
          {va.ttfaMs !== null && active ? ` · last reply started in ${va.ttfaMs} ms` : ""}
        </p>
      </section>

      <aside className="voice-side" aria-label="Transcript and details">
        {err && (
          <div className="banner err" role="alert" data-testid="voice-error">
            <AlertTriangle size={17} aria-hidden="true" />
            <div className="grow"><b>{err.title}.</b> {err.fix}</div>
          </div>
        )}
        {!va.supported && va.phase === "off" && (
          <div className="banner warn" data-testid="voice-unsupported"><Info size={17} aria-hidden="true" /><div className="grow"><b>Voice isn't available in this browser.</b> Saathi voice uses the browser's built-in speech recognition (Chrome or Edge). You can still use the text chat.<div style={{ marginTop: 8 }}><Button size="sm" icon={MessageCircle} onClick={() => goto("chat")}>Open text chat</Button></div></div></div>
        )}

        {va.review && (
          <div className="review-card" role="alertdialog" aria-labelledby="rv-t" data-testid="voice-review">
            <b id="rv-t">I heard: “{va.review.text}”. Is that correct?</b>
            <p className="help">{va.review.confidence !== null ? `Recognition confidence ${Math.round(va.review.confidence * 100)}%. ` : ""}Because this is part of a booking, I won't act on it until you confirm.</p>
            <div className="row-gap"><Button variant="primary" onClick={va.confirmReview} data-testid="voice-review-yes">Yes, send it</Button><Button onClick={va.discardReview} data-testid="voice-review-no">No, say it again</Button></div>
          </div>
        )}

        {confirming && (
          <div className="readback" data-testid="voice-readback">
            <div className="card-title"><ShieldCheck size={18} aria-hidden="true" />Please confirm these details</div>
            <BookingSummary booking={session.booking} />
            <p className="help" style={{ margin: "10px 0" }}>Say “yes, confirm” or tap the button. Nothing is booked until you do. Anything else, say “change time” or “cancel”.</p>
            <Button variant="primary" block disabled={s.busy} loading={s.busy} onClick={() => void s.send("yes, confirm", "voice")} data-testid="voice-confirm">Confirm booking</Button>
          </div>
        )}
        {pos.current >= 0 && !confirming && <div className="card"><BookingStepper current={pos.current} result={pos.result} /></div>}

        <div className="card transcript" data-testid="voice-transcript">
          <div className="card-title"><MessageCircle size={18} aria-hidden="true" />Transcript</div>
          {turns.length === 0
            ? <p className="muted">{va.phase === "off" ? "Start a voice conversation and everything you say and everything the assistant replies will appear here, word for word." : "Waiting for you to speak…"}</p>
            : <div className="t-list" ref={transcriptList}>{turns.map((m, i) => <ChatMessage key={`${m.id}-${i}`} m={m} onRetry={s.retry} onDismiss={s.dismissError} />)}</div>}
        </div>

        <div className="card flat">
          <div className="card-title"><Info size={17} aria-hidden="true" />How voice works</div>
          <ul className="plain">
            <li><b>Real, not simulated:</b> speech-to-text and text-to-speech use your browser's built-in engines. Your browser vendor may process the audio.</li>
            <li>Every sentence goes through the same safety check and booking flow as typed chat.</li>
            <li>Booking details are read back and need an explicit “yes”. Uncertain times and numbers are double-checked first.</li>
          </ul>
          <p className="label" style={{ margin: "12px 0 6px" }}>Try saying</p>
          <div className="chips">{TRY_SAYING.map((t) => <span key={t} className="chip static">{t}</span>)}</div>
        </div>
      </aside>
    </div>
  );
}

export function VoicePage() {
  return <SessionGate to="voice" what="the voice assistant"><Inner /></SessionGate>;
}
