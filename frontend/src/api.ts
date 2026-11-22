import type {
  ApprovalItem, ConfigView, Member, PackageOption, Program, SessionCreated, SessionView,
} from "./types";

export const API_URL: string = (import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
  /** status 0 = the request never reached the server (offline, server down, blocked). */
  get isNetwork(): boolean { return this.status === 0; }
}

async function request<T>(path: string, init: RequestInit = {}, headers: Record<string, string> = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...headers },
    });
  } catch {
    throw new ApiError(0, "Can't reach the Saathi server. Check that the backend is running.");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) detail = "That input isn't valid. Please check it and try again.";
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const bearer = (token: string) => ({ Authorization: `Bearer ${token}` });

export const api = {
  config: () => request<ConfigView>("/api/config"),
  members: () => request<Member[]>("/api/members"),
  programs: () => request<Program[]>("/api/programs"),
  packages: (q = "") => request<PackageOption[]>(`/api/packages?q=${encodeURIComponent(q)}`),
  createSession: (memberId: string) =>
    request<SessionCreated>("/api/sessions", { method: "POST", body: JSON.stringify({ member_id: memberId }) }),
  getSession: (id: string, token: string) =>
    request<SessionView>(`/api/sessions/${id}`, {}, bearer(token)),
  send: (id: string, token: string, text: string) =>
    request<SessionView>(`/api/sessions/${id}/messages`, { method: "POST", body: JSON.stringify({ text }) }, bearer(token)),
  deleteSession: (id: string, token: string) =>
    request<{ deleted: boolean }>(`/api/sessions/${id}`, { method: "DELETE" }, bearer(token)),
  approvals: (coordToken: string) =>
    request<{ items: ApprovalItem[] }>("/api/coordinator/approvals", {}, { "X-Coordinator-Token": coordToken }),
  decide: (coordToken: string, sessionId: string, approved: boolean, note: string) =>
    request<ApprovalItem>(`/api/coordinator/approvals/${sessionId}`,
      { method: "POST", body: JSON.stringify({ approved, note }) }, { "X-Coordinator-Token": coordToken }),
};
