import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api";
import type { ChatMessage, SessionView } from "./types";

const STORE_KEY = "saathi.session"; // sessionStorage: per-tab, cleared when the tab closes

interface Stored { id: string; token: string }
const load = (): Stored | null => {
  try { return JSON.parse(sessionStorage.getItem(STORE_KEY) ?? "null") as Stored | null; } catch { return null; }
};
const save = (s: Stored | null) =>
  s ? sessionStorage.setItem(STORE_KEY, JSON.stringify(s)) : sessionStorage.removeItem(STORE_KEY);

export interface SendError { text: string; message: string }

export function useSession() {
  const [session, setSession] = useState<SessionView | null>(null);
  const [pending, setPending] = useState<ChatMessage | null>(null); // optimistic user bubble (sending / failed)
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(false);
  const [restoring, setRestoring] = useState(() => load() !== null);
  const [notice, setNotice] = useState<string | null>(null); // e.g. "previous session expired"
  const [error, setError] = useState<SendError | null>(null);
  const stored = useRef<Stored | null>(load());

  const clear = useCallback(() => {
    stored.current = null; save(null); setSession(null); setPending(null); setError(null);
  }, []);

  // Resume the session of this tab after a reload.
  useEffect(() => {
    const s = stored.current;
    if (!s) return;
    api.getSession(s.id, s.token)
      .then(setSession)
      .catch((e: unknown) => {
        if (e instanceof ApiError && (e.status === 404 || e.status === 401)) {
          clear(); setNotice("Your previous session expired, so we've reset it. Start a new conversation below.");
        } else {
          setNotice("Couldn't reach the server to restore your session.");
        }
      })
      .finally(() => setRestoring(false));
  }, [clear]);

  const awaiting = session?.status === "awaiting_coordinator";
  // While a coordinator decides, poll so the decision shows up without a manual refresh.
  useEffect(() => {
    if (!awaiting || !stored.current) return;
    const { id, token } = stored.current;
    const t = setInterval(() => { api.getSession(id, token).then(setSession).catch(() => undefined); }, 3000);
    return () => clearInterval(t);
  }, [awaiting]);

  const start = useCallback(async (memberId: string): Promise<boolean> => {
    setStarting(true); setNotice(null); setError(null);
    try {
      const created = await api.createSession(memberId);
      stored.current = { id: created.session.session_id, token: created.session_token };
      save(stored.current); setSession(created.session); setPending(null);
      return true;
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "Couldn't start a session.");
      return false;
    } finally { setStarting(false); }
  }, []);

  const send = useCallback(async (text: string) => {
    const s = stored.current;
    if (!s || busy) return;
    setBusy(true); setError(null);
    setPending({ id: -1, role: "user", kind: "answer", text, at: new Date().toISOString(), trace_id: null,
                 emergency: null, confirmation: null, clientState: "sending" });
    try {
      setSession(await api.send(s.id, s.token, text));
      setPending(null);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, "Something went wrong.");
      if (err.status === 404 || err.status === 401) {
        clear(); setNotice("This session is no longer valid (the server may have restarted). Start a new conversation.");
      } else {
        if (err.status === 409) api.getSession(s.id, s.token).then(setSession).catch(() => undefined);
        setPending((p) => (p ? { ...p, clientState: "failed" } : p));
        setError({ text, message: err.message });
      }
    } finally { setBusy(false); }
  }, [busy, clear]);

  const retry = useCallback(() => { if (error) { const t = error.text; setPending(null); void send(t); } }, [error, send]);
  const dismissError = useCallback(() => { setPending(null); setError(null); }, []);

  const end = useCallback(async () => {
    const s = stored.current;
    clear();
    if (s) await api.deleteSession(s.id, s.token).catch(() => undefined); // best effort; server also expires idle sessions
  }, [clear]);

  const messages: ChatMessage[] = pending ? [...(session?.messages ?? []), pending] : session?.messages ?? [];
  return { session, messages, busy, starting, restoring, notice, setNotice, error, start, send, retry, dismissError, end };
}
