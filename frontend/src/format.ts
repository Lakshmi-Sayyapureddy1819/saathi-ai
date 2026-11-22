import type { BookingStage, ChatMessage, SessionView } from "./types";

export const formatINR = (n: number): string => `₹${n.toLocaleString("en-IN")}`;

export const isMockReply = (m: ChatMessage): boolean => m.role === "assistant" && m.text.startsWith("[MOCK");

export const STEPS: { stage: BookingStage | "booked"; label: string }[] = [
  { stage: "choosing_package", label: "Test" },
  { stage: "choosing_slot", label: "Time" },
  { stage: "confirming", label: "Confirm" },
  { stage: "booked", label: "Booked" },
];

/** Index of the active step (0-3) or -1 when no booking is in progress. */
export function stepIndex(stage: BookingStage, justBooked: boolean): number {
  if (justBooked) return 3;
  return STEPS.findIndex((s) => s.stage === stage);
}

export type StatusTone = "idle" | "ok" | "wait" | "alert";
export function statusLabel(s: SessionView | null): { label: string; tone: StatusTone } {
  if (!s) return { label: "No active session", tone: "idle" };
  if (s.status === "awaiting_coordinator") return { label: "Waiting for care coordinator", tone: "wait" };
  if (s.triage_status === "RED_CRISIS") return { label: "Emergency guidance shown", tone: "alert" };
  return { label: `Active · ${s.member.name}`, tone: "ok" };
}

/** The tool-confirmed booking message, but only while nothing newer from the member has happened since. */
export function lastBooking(messages: ChatMessage[]): ChatMessage | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === "user") return null;
    if (m.kind === "booking_confirmed") return m;
  }
  return null;
}
