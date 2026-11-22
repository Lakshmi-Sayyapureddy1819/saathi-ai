import { describe, expect, it } from "vitest";
import { ApiError } from "../src/api";
import { formatINR, isMockReply, lastBooking, statusLabel, stepIndex } from "../src/format";
import type { ChatMessage, SessionView } from "../src/types";

const msg = (over: Partial<ChatMessage>): ChatMessage => ({
  id: 1, role: "assistant", kind: "answer", text: "hi", at: "2026-01-01T00:00:00", trace_id: null,
  emergency: null, confirmation: null, ...over,
});
const session = (over: Partial<SessionView>): SessionView => ({
  session_id: "s", member: { member_id: "MEM_1001", name: "Aarav", age: 34, language_preference: "hinglish" },
  status: "active", triage_status: "GREEN_NORMAL", messages: [],
  booking: { stage: "idle", package: null, options: [], date_iso: null, date_label: null, slot: null, slots: [], dates: [] },
  handoff: { status: "none", ticket_id: null, note: "" }, bookings: [], ...over,
});

describe("format helpers", () => {
  it("formats rupees with Indian grouping", () => {
    expect(formatINR(2999)).toBe("₹2,999");
    expect(formatINR(125000)).toBe("₹1,25,000");
  });
  it("flags only assistant mock replies", () => {
    expect(isMockReply(msg({ text: "[MOCK:gemini] hello" }))).toBe(true);
    expect(isMockReply(msg({ text: "Real answer" }))).toBe(false);
    expect(isMockReply(msg({ role: "user", text: "[MOCK" }))).toBe(false);
  });
  it("maps booking stage to a step index", () => {
    expect(stepIndex("idle", false)).toBe(-1);
    expect(stepIndex("choosing_package", false)).toBe(0);
    expect(stepIndex("confirming", false)).toBe(2);
    expect(stepIndex("idle", true)).toBe(3);
  });
  it("derives the session status pill", () => {
    expect(statusLabel(null).tone).toBe("idle");
    expect(statusLabel(session({})).label).toBe("Active · Aarav");
    expect(statusLabel(session({ status: "awaiting_coordinator" })).tone).toBe("wait");
    expect(statusLabel(session({ triage_status: "RED_CRISIS" })).tone).toBe("alert");
  });
  it("shows a confirmed booking only until the member sends something newer", () => {
    const booked = msg({ id: 3, kind: "booking_confirmed" });
    expect(lastBooking([msg({ id: 1, role: "user" }), booked])).toBe(booked);
    expect(lastBooking([booked, msg({ id: 4, role: "user" })])).toBeNull();
  });
});

describe("ApiError", () => {
  it("treats status 0 as a network failure", () => {
    expect(new ApiError(0, "x").isNetwork).toBe(true);
    expect(new ApiError(500, "x").isNetwork).toBe(false);
  });
});
