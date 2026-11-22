import { FormEvent, useEffect, useRef, useState } from "react";
import { isMockReply } from "../format";
import type { ChatMessage } from "../types";

interface Props {
  messages: ChatMessage[];
  busy: boolean;
  paused: boolean; // awaiting coordinator: input disabled
  maxChars: number;
  error: { text: string; message: string } | null;
  onSend: (text: string) => void;
  onRetry: () => void;
  onDismissError: () => void;
}

const SUGGESTIONS: { label: string; text: string }[] = [
  { label: "Yoga for exhaustion", text: "What yoga helps with exhaustion?" },
  { label: "Hinglish: thakan", text: "Mujhe bahut thakan rehti hai, kya yoga karun?" },
  { label: "Book a blood test", text: "Book a blood test" },
  { label: "Book a thyroid test", text: "I want to book a thyroid test" },
];

function Bubble({ m, onRetry, onDismiss }: { m: ChatMessage; onRetry: () => void; onDismiss: () => void }) {
  if (m.role === "user") {
    return (
      <div className={`row user${m.clientState === "failed" ? " failed" : ""}`}>
        <div className="bubble user" data-testid="msg-user">{m.text}</div>
        {m.clientState === "sending" && <span className="meta">Sending…</span>}
        {m.clientState === "failed" && (
          <span className="meta err">
            Not delivered.{" "}
            <button className="link" onClick={onRetry}>Retry</button>{" · "}
            <button className="link" onClick={onDismiss}>Discard</button>
          </span>
        )}
      </div>
    );
  }
  if (m.role === "system" || m.kind === "handoff_resolved") {
    return <div className="notice-row"><div className="system-note" data-testid="msg-system">{m.text}</div></div>;
  }
  if (m.kind === "emergency") {
    return (
      <div className="row assistant">
        <div className="card emergency" role="alert" data-testid="msg-emergency">
          <strong>🚨 Please get emergency help now</strong>
          <p>{m.emergency?.message ?? m.text}</p>
          <ul>
            {Object.entries(m.emergency?.helplines ?? {}).map(([name, number]) => (
              <li key={name}>{name}: <a href={`tel:${number.replace(/[^\d+]/g, "")}`}>{number}</a></li>
            ))}
          </ul>
          <small>Saathi is an AI assistant and cannot provide emergency care. Call a local emergency number or go to the nearest hospital.</small>
        </div>
      </div>
    );
  }
  const cls = m.kind === "safety_notice" ? "card safety" : m.kind === "booking_confirmed" ? "card success"
    : m.kind === "handoff" ? "card handoff" : "bubble assistant";
  return (
    <div className="row assistant">
      <div className="avatar" aria-hidden="true">S</div>
      <div className={cls} data-testid={`msg-${m.kind}`}>
        {m.kind === "safety_notice" && <strong>Health safety notice</strong>}
        {m.kind === "booking_confirmed" && <strong>✅ Booked</strong>}
        {m.kind === "handoff" && <strong>🤝 Care coordinator needed</strong>}
        <p>{m.text}</p>
        {m.confirmation && (
          <dl className="kv">
            <dt>Booking ID</dt><dd data-testid="booking-id">{m.confirmation.booking_id}</dd>
            <dt>Test</dt><dd>{m.confirmation.package_name}</dd>
            <dt>When</dt><dd>{m.confirmation.date} · {m.confirmation.slot}</dd>
          </dl>
        )}
        {isMockReply(m) && <small className="badge">Demo mode: no AI model key is configured on the server</small>}
      </div>
    </div>
  );
}

export function Chat({ messages, busy, paused, maxChars, error, onSend, onRetry, onDismissError }: Props) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView?.({ block: "end" }); }, [messages.length, busy]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || busy || paused || text.length > maxChars) return;
    onSend(text); setDraft("");
  };
  const tooLong = draft.trim().length > maxChars;

  return (
    <section className="chat" aria-label="Conversation">
      <div className="log" role="log" aria-live="polite" aria-relevant="additions" data-testid="chat-log">
        {messages.length === 0 && (
          <div className="empty" data-testid="chat-empty">
            <h3>How can I help today?</h3>
            <p>Ask about yoga, diet and lifestyle, or book a lab test. Try one of these:</p>
            <div className="chips">
              {SUGGESTIONS.map((s) => (
                <button key={s.label} className="chip" disabled={busy || paused} onClick={() => onSend(s.text)}>{s.label}</button>
              ))}
            </div>
            <p className="hint">Safety check: <button className="chip danger" disabled={busy || paused}
              onClick={() => onSend("I have severe chest pain")}>Say "I have chest pain"</button></p>
          </div>
        )}
        {messages.map((m, i) => <Bubble key={`${m.id}-${i}`} m={m} onRetry={onRetry} onDismiss={onDismissError} />)}
        {busy && (
          <div className="row assistant" data-testid="typing">
            <div className="avatar" aria-hidden="true">S</div>
            <div className="bubble assistant typing" aria-label="Saathi is typing"><i /><i /><i /></div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && (
        <div className="error-bar" role="alert" data-testid="send-error">
          <span>{error.message}</span>
          <span><button className="btn small" onClick={onRetry}>Retry</button>
            <button className="btn small ghost" onClick={onDismissError}>Dismiss</button></span>
        </div>
      )}

      <form className="composer" onSubmit={submit}>
        <label htmlFor="msg" className="sr-only">Message Saathi</label>
        <input id="msg" value={draft} onChange={(e) => setDraft(e.target.value)} autoComplete="off"
          placeholder={paused ? "Waiting for a care coordinator…" : "Type your message (English or Hinglish)"}
          disabled={paused} aria-invalid={tooLong} aria-describedby="msg-help" />
        <button className="btn primary" type="submit" disabled={busy || paused || !draft.trim() || tooLong}>Send</button>
        <div id="msg-help" className={`help${tooLong ? " err" : ""}`}>
          {tooLong ? `Too long: ${draft.trim().length}/${maxChars} characters.` : "Saathi doesn't diagnose conditions or replace a doctor."}
        </div>
      </form>
    </section>
  );
}
