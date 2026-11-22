import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import type { ApprovalItem } from "../types";

const KEY = "saathi.coordToken";

/** Care-coordinator console. Uses a shared secret (COORDINATOR_TOKEN on the server), NOT per-person login. */
export function Coordinator() {
  const [token, setToken] = useState(() => sessionStorage.getItem(KEY) ?? "");
  const [entered, setEntered] = useState(token);
  const [items, setItems] = useState<ApprovalItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [done, setDone] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    try { setItems((await api.approvals(token)).items); setErr(null); }
    catch (e) {
      setItems(null);
      setErr(e instanceof ApiError && e.status === 503
        ? "The coordinator console is disabled: set COORDINATOR_TOKEN in the backend environment and restart it."
        : e instanceof ApiError && e.status === 401 ? "That coordinator token is not valid." : (e as Error).message);
    }
  }, [token]);

  useEffect(() => { void refresh(); const t = setInterval(refresh, 3000); return () => clearInterval(t); }, [refresh]);

  const decide = async (it: ApprovalItem, approved: boolean) => {
    try {
      await api.decide(token, it.session_id, approved, notes[it.session_id] ?? "");
      setDone(`Ticket ${it.ticket_id}: ${approved ? "approved" : "rejected"}.`); await refresh();
    } catch (e) { setErr((e as Error).message); }
  };

  return (
    <main className="dash coord">
      <h1>Care coordinator console</h1>
      <div className="banner warn">Demo console. Access is a single shared secret, so approvals are <b>not tied to a
        named coordinator</b> and there is no audit trail. A real deployment needs per-person authentication.</div>
      <form className="card" onSubmit={(e) => { e.preventDefault(); sessionStorage.setItem(KEY, entered); setToken(entered); }}>
        <label htmlFor="ct">Coordinator token</label>
        <input id="ct" type="password" value={entered} onChange={(e) => setEntered(e.target.value)} autoComplete="off" />
        <button className="btn primary" type="submit" disabled={!entered}>Unlock</button>
      </form>
      {err && <div className="banner err" role="alert" data-testid="coord-error">{err}</div>}
      {done && <div className="banner info" role="status" data-testid="coord-done">{done}</div>}
      {items && items.length === 0 && <p className="muted" data-testid="coord-empty">No bookings are waiting for approval.</p>}
      {items?.map((it) => (
        <article key={it.session_id} className="card" data-testid="approval-item">
          <h3>Ticket {it.ticket_id}</h3>
          <dl className="kv">
            <dt>Member</dt><dd>{it.member_name} ({it.member_id})</dd>
            <dt>Test</dt><dd>{it.package_name ?? "—"}</dd>
            <dt>Requested</dt><dd>{it.date ?? "—"} {it.slot ?? ""}</dd>
          </dl>
          <label htmlFor={`n-${it.session_id}`}>Note to member (optional)</label>
          <input id={`n-${it.session_id}`} maxLength={300} value={notes[it.session_id] ?? ""}
            onChange={(e) => setNotes({ ...notes, [it.session_id]: e.target.value })} />
          <div className="actions">
            <button className="btn primary" onClick={() => decide(it, true)}>Approve callback</button>
            <button className="btn" onClick={() => decide(it, false)}>Reject</button>
          </div>
        </article>
      ))}
      <p><a href="#/">← Back to Saathi</a></p>
    </main>
  );
}
