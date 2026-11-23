import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, ClipboardList, KeyRound, RefreshCw, XCircle } from "lucide-react";
import { ApiError, api } from "../api";
import { Banner, Button, Card, ConfirmationDialog, EmptyState, Input, StatusBadge } from "../components/ui";
import { Brand } from "../components/shell/Logo";
import type { ApprovalItem } from "../types";

const KEY = "saathi.coordToken";

/**
 * Care-coordinator console. Deliberately NOT part of the member navigation. Auth is the backend's shared
 * COORDINATOR_TOKEN (X-Coordinator-Token); the server rejects every call without it.
 */
export function Coordinator() {
  const [token, setToken] = useState(() => sessionStorage.getItem(KEY) ?? "");
  const [entered, setEntered] = useState(token);
  const [items, setItems] = useState<ApprovalItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [done, setDone] = useState<string | null>(null);
  const [pending, setPending] = useState<{ it: ApprovalItem; approved: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [updated, setUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    try { setItems((await api.approvals(token)).items); setErr(null); setUpdated(new Date()); }
    catch (e) {
      setItems(null);
      setErr(e instanceof ApiError && e.status === 503
        ? "The coordinator console is disabled: set COORDINATOR_TOKEN in the backend environment and restart it."
        : e instanceof ApiError && e.status === 401 ? "That coordinator token is not valid." : (e as Error).message);
    }
  }, [token]);
  useEffect(() => { void refresh(); const t = setInterval(refresh, 3000); return () => clearInterval(t); }, [refresh]);

  const decide = async () => {
    if (!pending) return;
    const { it, approved } = pending; setBusy(true);
    try {
      await api.decide(token, it.session_id, approved, notes[it.session_id] ?? "");
      setDone(`Ticket ${it.ticket_id}: ${approved ? "approved" : "rejected"}.`); setPending(null); await refresh();
    } catch (e) { setErr((e as Error).message); setPending(null); }
    finally { setBusy(false); }
  };

  return (
    <div className="coord-page">
      <header className="coord-top"><Brand /><StatusBadge tone="brand" icon={false}>Care coordinator console</StatusBadge>
        <a className="btn sm ghost push" href="#/"><ArrowLeft size={15} aria-hidden="true" /> Back to Saathi</a></header>
      <main className="coord-main" id="main">
        <h1>Booking approvals</h1>
        <Banner tone="warn"><span>Demo console. Access is a single shared secret, so approvals are <b>not tied to a named coordinator</b> and there is no audit trail. A real deployment needs per-person authentication.</span></Banner>

        {!token || err?.includes("not valid") ? (
          <Card>
            <form onSubmit={(e) => { e.preventDefault(); sessionStorage.setItem(KEY, entered); setToken(entered); }} className="stack-sm">
              <div className="card-title"><KeyRound size={18} aria-hidden="true" />Unlock</div>
              <Input id="ct" label="Coordinator token" type="password" value={entered} onChange={(e) => setEntered(e.target.value)} autoComplete="off" />
              <Button variant="primary" type="submit" disabled={!entered}>Unlock console</Button>
            </form>
          </Card>
        ) : (
          <div className="coord-status"><StatusBadge tone="success">Unlocked</StatusBadge><span className="muted">{updated ? `Live · refreshed ${updated.toLocaleTimeString("en-IN")}` : "Loading…"}</span>
            <Button size="sm" variant="ghost" icon={RefreshCw} onClick={() => void refresh()}>Refresh</Button>
            <Button size="sm" variant="ghost" onClick={() => { sessionStorage.removeItem(KEY); setToken(""); setItems(null); setEntered(""); }}>Lock</Button></div>
        )}

        {err && <Banner tone="err" role="alert" data-testid="coord-error">{err}</Banner>}
        {done && <Banner tone="ok" role="status" data-testid="coord-done">{done}</Banner>}
        {items && items.length === 0 && <EmptyState icon={ClipboardList} title="No requests waiting" text="No bookings are waiting for approval." data-testid="coord-empty" />}

        <div className="stack-sm">
          {items?.map((it) => (
            <Card key={it.session_id} data-testid="approval-item" className="approval">
              <div className="bc-top"><h3>Ticket {it.ticket_id}</h3><StatusBadge tone="warn">Pending</StatusBadge></div>
              <dl className="kv">
                <dt>Member</dt><dd>{it.member_name} ({it.member_id})</dd>
                <dt>Test</dt><dd>{it.package_name ?? "—"}</dd>
                <dt>Requested</dt><dd>{it.date ?? "—"} {it.slot ?? ""}</dd>
                <dt>Received</dt><dd>{new Date(it.requested_at).toLocaleString("en-IN")}</dd>
              </dl>
              <Input label="Note to member (optional)" maxLength={300} value={notes[it.session_id] ?? ""} onChange={(e) => setNotes({ ...notes, [it.session_id]: e.target.value })} style={{ marginTop: 12 }} />
              <div className="row-gap" style={{ marginTop: 12 }}>
                <Button variant="primary" icon={CheckCircle2} onClick={() => setPending({ it, approved: true })}>Approve callback</Button>
                <Button icon={XCircle} onClick={() => setPending({ it, approved: false })}>Reject</Button>
              </div>
            </Card>
          ))}
        </div>
      </main>

      <ConfirmationDialog open={!!pending} title={pending?.approved ? "Approve this request?" : "Reject this request?"} danger={pending ? !pending.approved : false}
        confirmLabel={pending?.approved ? "Yes, approve" : "Yes, reject"} busy={busy} onCancel={() => setPending(null)} onConfirm={() => void decide()}>
        {pending && <>Ticket <b>{pending.it.ticket_id}</b> for {pending.it.member_name}. {pending.approved ? "The member is told a coordinator will call to arrange the test." : "The member is told it could not be completed and may pick another time."} {notes[pending.it.session_id] ? `Note: “${notes[pending.it.session_id]}”.` : ""} This can't be undone.</>}
      </ConfirmationDialog>
    </div>
  );
}
