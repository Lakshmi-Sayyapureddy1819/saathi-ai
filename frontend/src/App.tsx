import { useEffect, useState } from "react";
import { api } from "./api";
import { BookingPanel } from "./components/BookingPanel";
import { Chat } from "./components/Chat";
import { Coordinator } from "./components/Coordinator";
import { Dashboard } from "./components/Dashboard";
import { PackageBrowser } from "./components/PackageBrowser";
import { lastBooking, statusLabel } from "./format";
import { useSession } from "./useSession";

const useHash = () => {
  const [h, setH] = useState(location.hash);
  useEffect(() => { const f = () => setH(location.hash); addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
  return h;
};

export default function App() {
  const hash = useHash();
  const s = useSession();
  const [tab, setTab] = useState<"chat" | "booking">("chat");
  const [maxChars, setMaxChars] = useState(500);
  useEffect(() => { api.config().then((c) => setMaxChars(c.max_message_chars)).catch(() => undefined); }, []);

  const status = statusLabel(s.session);
  const paused = s.session?.status === "awaiting_coordinator";

  // Starting from a package button: create the session, then send the real chat message.
  const startAndSend = async (memberId: string, first?: string) => {
    if (await s.start(memberId) && first) {
      // `send` reads the freshly stored session; defer one tick so state has settled.
      setTimeout(() => void s.send(first), 0);
    }
  };

  return (
    <div className="app">
      <header className="top">
        <a className="brand" href="#/" aria-label="Saathi Care AI home"><span className="logo" aria-hidden="true">+</span> Saathi Care AI</a>
        <div className="top-right">
          <span className={`pill ${status.tone}`} role="status" data-testid="status-pill">{status.label}</span>
          {s.session && <button className="btn small ghost" onClick={() => void s.end()} data-testid="end-session">End session</button>}
          {s.session && <button className="btn small" onClick={() => void s.end()} data-testid="new-session">New session</button>}
        </div>
      </header>

      {hash === "#/coordinator" ? <Coordinator /> : s.restoring ? (
        <main className="dash"><p className="muted">Restoring your session…</p></main>
      ) : !s.session ? (
        <Dashboard starting={s.starting} notice={s.notice} onDismissNotice={() => s.setNotice(null)} onStart={startAndSend} />
      ) : (
        <main className="workspace">
          <div className="tabs" role="tablist" aria-label="View">
            <button role="tab" aria-selected={tab === "chat"} onClick={() => setTab("chat")}>Chat</button>
            <button role="tab" aria-selected={tab === "booking"} onClick={() => setTab("booking")}
              data-testid="tab-booking">Booking &amp; tests</button>
          </div>
          <div className={`pane chat-pane${tab === "chat" ? " show" : ""}`}>
            <Chat messages={s.messages} busy={s.busy} paused={paused} maxChars={maxChars} error={s.error}
              onSend={(t) => void s.send(t)} onRetry={s.retry} onDismissError={s.dismissError} />
          </div>
          <div className={`pane side-pane${tab === "booking" ? " show" : ""}`}>
            <BookingPanel booking={s.session.booking} handoff={s.session.handoff} confirmed={lastBooking(s.session.messages)} bookings={s.session.bookings}
              busy={s.busy} paused={paused} onSend={(t) => { setTab("chat"); void s.send(t); }} />
            <details className="card catalogue">
              <summary>Browse all lab packages</summary>
              <PackageBrowser actionLabel="Book" disabled={s.busy || paused} onPick={(p) => { setTab("chat"); void s.send(`Book ${p.name}`); }} />
            </details>
          </div>
        </main>
      )}

      <footer className="foot" role="contentinfo">
        Saathi is an AI wellness assistant. It does not diagnose and is not a substitute for a medical professional.
        In an emergency call <b>112</b> (India) or your local emergency number.{" "}
        <a href="#/coordinator">Coordinator console</a>
      </footer>
    </div>
  );
}
