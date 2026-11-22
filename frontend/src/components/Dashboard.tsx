import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { ConfigView, Member, PackageOption, Program } from "../types";
import { PackageBrowser } from "./PackageBrowser";

interface Props {
  starting: boolean;
  notice: string | null;
  onDismissNotice: () => void;
  onStart: (memberId: string, firstMessage?: string) => void;
}

const SERVICES = [
  { icon: "🧘", title: "Wellness coaching", text: "Yoga, pranayama, diet and lifestyle guidance grounded in our program library." },
  { icon: "🔬", title: "Lab test booking", text: "Search packages, pick a time, review a summary and confirm before anything is booked." },
  { icon: "🛡️", title: "Safety first", text: "Red-flag symptoms trigger fixed emergency guidance in code, never an AI guess. No diagnoses." },
  { icon: "🤝", title: "Human support", text: "If a booking fails, a care coordinator is brought in and you can see the status." },
];

export function Dashboard({ starting, notice, onDismissNotice, onStart }: Props) {
  const [members, setMembers] = useState<Member[]>([]);
  const [memberId, setMemberId] = useState("");
  const [programs, setPrograms] = useState<Program[]>([]);
  const [cfg, setCfg] = useState<ConfigView | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.members(), api.programs(), api.config()])
      .then(([m, p, c]) => { setMembers(m); setMemberId(m[0]?.member_id ?? ""); setPrograms(p); setCfg(c); })
      .catch((e: Error) => setLoadErr(e.message));
  }, []);

  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    programs.forEach((p) => counts.set(p.category, (counts.get(p.category) ?? 0) + 1));
    return [...counts.entries()];
  }, [programs]);

  const startBooking = (p: PackageOption) => memberId && onStart(memberId, `Book ${p.name}`);

  return (
    <main className="dash">
      {notice && <div className="banner warn" role="status" data-testid="notice">{notice}
        <button className="link" onClick={onDismissNotice}>Dismiss</button></div>}
      {loadErr && <div className="banner err" role="alert" data-testid="load-error">{loadErr}{" "}
        <button className="link" onClick={() => location.reload()}>Reload</button></div>}
      {cfg && !cfg.llm_configured && (
        <div className="banner info" data-testid="mock-banner">
          <span>Demo mode: no AI model key is configured on the server, so wellness answers appear as <code>[MOCK]</code> text.
          Booking, safety and routing don't use an AI model and work normally.</span>
        </div>
      )}

      <section className="hero">
        <div>
          <p className="eyebrow">Your wellness companion</p>
          <h1>Care that listens, in English and Hinglish.</h1>
          <p className="lead">Ask about yoga, diet and sleep, or book a lab test in a few taps. Saathi is an AI assistant: it
            doesn't diagnose conditions and isn't a substitute for a doctor.</p>
        </div>
        <form className="start card" onSubmit={(e) => { e.preventDefault(); if (memberId) onStart(memberId); }}>
          <h2>Start a conversation</h2>
          <label htmlFor="member">Demo member</label>
          <select id="member" value={memberId} onChange={(e) => setMemberId(e.target.value)} disabled={members.length === 0}>
            {members.map((m) => <option key={m.member_id} value={m.member_id}>{m.name} · {m.age} · {m.language_preference}</option>)}
          </select>
          <button className="btn primary big" type="submit" disabled={starting || !memberId} data-testid="start-chat">
            {starting ? "Starting…" : "Start conversation"}
          </button>
          <p className="muted status-line" data-testid="session-status">Session status: no active session</p>
        </form>
      </section>

      <section aria-labelledby="svc"><h2 id="svc">What Saathi can do</h2>
        <div className="grid4">
          {SERVICES.map((s) => (
            <article key={s.title} className="card service"><div className="icon" aria-hidden="true">{s.icon}</div>
              <h3>{s.title}</h3><p>{s.text}</p></article>
          ))}
        </div>
      </section>

      <section aria-labelledby="labs"><h2 id="labs">Lab packages</h2>
        <PackageBrowser actionLabel="Book" disabled={starting || !memberId} onPick={startBooking} />
      </section>

      {categories.length > 0 && (
        <section aria-labelledby="progs"><h2 id="progs">Program library</h2>
          <div className="chips" data-testid="program-cats">
            {categories.map(([c, n]) => <span key={c} className="chip static">{c} · {n}</span>)}
          </div>
        </section>
      )}
    </main>
  );
}
