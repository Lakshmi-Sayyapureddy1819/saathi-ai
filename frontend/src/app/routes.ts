import { useEffect, useState } from "react";
import { Activity, CalendarCheck, FlaskConical, HeartHandshake, LayoutDashboard, MessageCircle, Mic, Phone, Settings, type LucideIcon } from "lucide-react";

export type RouteId = "overview" | "chat" | "voice" | "reminder" | "labs" | "bookings" | "insights" | "support" | "settings" | "coordinator";

export interface NavItem { id: RouteId; label: string; icon: LucideIcon; path: string; mobile: boolean }

export const NAV: NavItem[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard, path: "#/", mobile: true },
  { id: "chat", label: "Chat with Mimi", icon: MessageCircle, path: "#/chat", mobile: true },
  { id: "voice", label: "Talk to Mimi", icon: Mic, path: "#/voice", mobile: true },
  { id: "reminder", label: "Reminder call", icon: Phone, path: "#/reminder", mobile: false },
  { id: "labs", label: "Lab Tests", icon: FlaskConical, path: "#/labs", mobile: true },
  { id: "bookings", label: "My Bookings", icon: CalendarCheck, path: "#/bookings", mobile: true },
  { id: "insights", label: "Health Insights", icon: Activity, path: "#/insights", mobile: false },
  { id: "support", label: "Care Team", icon: HeartHandshake, path: "#/support", mobile: false },
  { id: "settings", label: "Settings", icon: Settings, path: "#/settings", mobile: false },
];

export const TITLES: Record<RouteId, string> = {
  overview: "Overview", chat: "Chat with Mimi", voice: "Talk to Mimi", reminder: "Reminder call", labs: "Lab Tests", bookings: "My Bookings",
  insights: "Health Insights", support: "Care Team", settings: "Settings", coordinator: "Coordinator Console",
};

export function parseRoute(hash: string): RouteId {
  const seg = hash.replace(/^#\/?/, "").split(/[/?]/)[0] ?? "";
  if (seg === "") return "overview";
  return (Object.keys(TITLES) as RouteId[]).includes(seg as RouteId) ? (seg as RouteId) : "overview";
}

export const pathOf = (id: RouteId): string => (id === "overview" ? "#/" : `#/${id}`);

export function useRoute(): RouteId {
  const [r, setR] = useState<RouteId>(() => parseRoute(location.hash));
  useEffect(() => {
    const f = () => setR(parseRoute(location.hash));
    addEventListener("hashchange", f);
    return () => removeEventListener("hashchange", f);
  }, []);
  return r;
}

export const goto = (id: RouteId): void => { location.hash = pathOf(id); };
