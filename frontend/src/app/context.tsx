import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api";
import { useSession } from "../useSession";
import type { ConfigView, Member, PackageOption } from "../types";
import { goto, type RouteId } from "./routes";

type SessionApi = ReturnType<typeof useSession>;

interface AppValue {
  s: SessionApi;
  cfg: ConfigView | null;
  cfgError: string | null;
  members: Member[];
  membersLoading: boolean;
  maxChars: number;
  memberId: string;
  setMemberId: (id: string) => void;
  /** Start a session for `memberId`, optionally send a first message, then navigate. Everything goes through the real API. */
  begin: (memberId: string, opts?: { first?: string; to?: RouteId }) => Promise<void>;
  /** Send a message from anywhere (navigates to `to`, default chat). */
  ask: (text: string, to?: RouteId) => void;
  bookPackage: (p: PackageOption) => void;
}

const Ctx = createContext<AppValue | null>(null);
export function useApp(): AppValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const s = useSession();
  const [cfg, setCfg] = useState<ConfigView | null>(null);
  const [cfgError, setCfgError] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [membersLoading, setMembersLoading] = useState(true);
  const [memberId, setMemberId] = useState("");

  useEffect(() => {
    api.config().then(setCfg).catch((e: Error) => setCfgError(e.message));
    api.members().then((m) => { setMembers(m); setMemberId((cur) => cur || m[0]?.member_id || ""); }).catch((e: Error) => setCfgError(e.message)).finally(() => setMembersLoading(false));
  }, []);

  const begin = useCallback(async (memberId: string, opts?: { first?: string; to?: RouteId }) => {
    const ok = await s.start(memberId);
    if (!ok) return;
    if (opts?.to) goto(opts.to);
    if (opts?.first) setTimeout(() => void s.send(opts.first!), 0);
  }, [s]);

  const ask = useCallback((text: string, to: RouteId = "chat") => { goto(to); void s.send(text); }, [s]);
  const bookPackage = useCallback((p: PackageOption) => { goto("labs"); void s.send(`Book ${p.name}`); }, [s]);

  const value = useMemo<AppValue>(() => ({
    s, cfg, cfgError, members, membersLoading, maxChars: cfg?.max_message_chars ?? 500, memberId, setMemberId, begin, ask, bookPackage,
  }), [s, cfg, cfgError, members, membersLoading, memberId, begin, ask, bookPackage]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
