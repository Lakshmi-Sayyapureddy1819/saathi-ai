import { memo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, BookOpen, Check, CheckCircle2, Copy, Database, HeartHandshake, OctagonAlert, Phone, RotateCcw, Trash2 } from "lucide-react";
import { isMockReply } from "../../format";
import type { ChatMessage as Msg, Citation, GroundingView } from "../../types";
import { IconButton, StatusBadge, useToast } from "../ui";
import { MimiAvatar, type MimiState } from "../mimi/MimiAvatar";
import { Markdown } from "./Markdown";

const time = (iso: string): string => new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
const enter = { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.22, ease: [0.22, 0.8, 0.24, 1] as [number, number, number, number] } };

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  const toast = useToast();
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setDone(true); window.setTimeout(() => setDone(false), 1500); }
    catch { toast("Couldn't copy. Select the text and copy it manually.", "err"); }
  };
  return <IconButton small icon={done ? Check : Copy} label={done ? "Copied" : "Copy response"} onClick={() => void copy()} />;
}

/** The answer text without the inline [SOURCE_ID] markers: the verified sources are shown as chips instead. */
export const stripCites = (text: string, cites: Citation[] = []): string => {
  let t = text;
  for (const c of cites) t = t.split(`[${c.source_id}]`).join("");
  return t.replace(/[ 	]+([.,;:!?])/g, "$1").replace(/[ 	]{2,}/g, " ").trim();
};

const MODE_LABEL = { mode_a_rag: "Library search (agentic RAG)", mode_b_facts: "Your records (no retrieval)" } as const;

function Sources({ cites, grounding }: { cites: Citation[]; grounding?: GroundingView | null }) {
  if (!cites.length) return null;
  const consulted = cites.every((c) => !c.cited);
  return (
    <div className="sources" data-testid="msg-sources">
      <span className="sources-label">{consulted ? "Sources consulted" : "Sources"}</span>
      {cites.map((c) => (
        <span key={c.source_id} className={`chip static source-chip${c.cited ? "" : " consulted"}`} title={c.source_id}
          data-testid="source-chip">
          {c.kind === "document" ? <BookOpen size={13} aria-hidden="true" /> : <Database size={13} aria-hidden="true" />}
          {c.title}
        </span>
      ))}
      {grounding && (
        <details className="how" data-testid="how-answered">
          <summary>How I answered</summary>
          <ul>
            <li>{MODE_LABEL[grounding.mode]}</li>
            {grounding.mode === "mode_a_rag" && grounding.search_queries.length > 0 && (
              <li>Searched ({grounding.retriever}): {grounding.search_queries.map((q) => `"${q}"`).join(", ")}</li>
            )}
            {grounding.mode === "mode_b_facts" && grounding.tools_called.length > 0 && (
              <li>Looked up: {grounding.tools_called.map((t) => t.replace(/^get_/, "").replace(/_/g, " ")).join(", ")}</li>
            )}
            <li>{grounding.decided_by === "llm" ? "The AI chose what to look up" : "Standard lookup rules"}</li>
          </ul>
        </details>
      )}
    </div>
  );
}

interface Props { m: Msg; onRetry: () => void; onDismiss: () => void; mood?: MimiState }

export const ChatMessage = memo(function ChatMessage({ m, onRetry, onDismiss, mood }: Props) {
  if (m.role === "user") {
    const failed = m.clientState === "failed";
    return (
      <motion.div className={`msg user${failed ? " failed" : ""}`} {...enter}>
        <div className="bubble user" data-testid="msg-user">{m.text}</div>
        <div className="msg-meta">
          {m.clientState === "sending" && <span>Sending…</span>}
          {failed && <span className="err" role="alert"><AlertTriangle size={13} aria-hidden="true" /> Not delivered.{" "}
            <button className="link-btn" onClick={onRetry}><RotateCcw size={12} aria-hidden="true" /> Retry</button>{" · "}
            <button className="link-btn" onClick={onDismiss}><Trash2 size={12} aria-hidden="true" /> Discard</button></span>}
          {!m.clientState && <time dateTime={m.at}>{time(m.at)}</time>}
        </div>
      </motion.div>
    );
  }

  if (m.role === "system" || m.kind === "handoff_resolved") {
    const resolved = m.kind === "handoff_resolved";
    return (
      <motion.div className="msg-notice" {...enter}>
        <div className={`card-msg ${resolved ? "info" : "neutral"}`} data-testid="msg-system" role={resolved ? "status" : undefined}>
          {resolved && <div className="cm-head"><HeartHandshake size={17} aria-hidden="true" /><b>Coordinator decision</b><StatusBadge tone="info" icon={false}>Care team</StatusBadge></div>}
          <p>{m.text}</p>
        </div>
      </motion.div>
    );
  }

  if (m.kind === "emergency") {
    return (
      <motion.div className="msg assistant" {...enter}>
        <div className="card-msg emergency" role="alert" data-testid="msg-emergency">
          <div className="cm-head"><OctagonAlert size={20} aria-hidden="true" /><b>Please get emergency help now</b><StatusBadge tone="danger">Urgent</StatusBadge></div>
          <p>{m.emergency?.message ?? m.text}</p>
          <ul className="helplines">
            {Object.entries(m.emergency?.helplines ?? {}).map(([name, number]) => (
              <li key={name}><Phone size={15} aria-hidden="true" />{name}: <a href={`tel:${number.replace(/[^\d+]/g, "")}`}>{number}</a></li>
            ))}
          </ul>
          <small>Saathi is an AI assistant and cannot provide emergency care. Call a local emergency number or go to the nearest hospital.</small>
        </div>
      </motion.div>
    );
  }

  const copyable = m.kind === "answer" || m.kind === "safety_notice";
  return (
    <motion.div className="msg assistant" {...enter}>
      <MimiAvatar size={40} state={mood ?? "idle"} still={!mood} />
      <div className="msg-col">
        {m.kind === "safety_notice" && (
          <div className="card-msg warn" data-testid="msg-safety_notice">
            <div className="cm-head"><AlertTriangle size={18} aria-hidden="true" /><b>Health safety notice</b></div>
            <Markdown text={m.text} />
          </div>
        )}
        {m.kind === "booking_confirmed" && (
          <div className="card-msg ok" data-testid="msg-booking_confirmed">
            <div className="cm-head"><CheckCircle2 size={18} aria-hidden="true" /><b>Booking confirmed</b><StatusBadge tone="success">Confirmed</StatusBadge></div>
            <Markdown text={m.text} />
            {m.confirmation && (
              <dl className="kv">
                <dt>Booking ID</dt><dd className="num" data-testid="booking-id">{m.confirmation.booking_id}</dd>
                <dt>Test</dt><dd>{m.confirmation.package_name}</dd>
                <dt>When</dt><dd>{m.confirmation.date} · {m.confirmation.slot}</dd>
              </dl>
            )}
          </div>
        )}
        {m.kind === "handoff" && (
          <div className="card-msg wait" data-testid="msg-handoff">
            <div className="cm-head"><HeartHandshake size={18} aria-hidden="true" /><b>Care coordinator needed</b><StatusBadge tone="warn">Awaiting review</StatusBadge></div>
            <Markdown text={m.text} />
          </div>
        )}
        {m.kind === "answer" && <div className="bubble assistant" data-testid="msg-answer"><Markdown text={stripCites(m.text, m.citations)} /></div>}
        {m.kind === "answer" && <Sources cites={m.citations ?? []} grounding={m.grounding} />}
        <div className="msg-meta">
          <time dateTime={m.at}>{time(m.at)}</time>
          {copyable && <CopyButton text={m.text} />}
          {isMockReply(m) && <StatusBadge tone="info" icon={false}>Demo mode: no AI model key is configured on the server</StatusBadge>}
        </div>
      </div>
    </motion.div>
  );
});
