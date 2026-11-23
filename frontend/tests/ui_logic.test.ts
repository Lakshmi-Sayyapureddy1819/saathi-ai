import { describe, expect, it } from "vitest";
import { parseBlocks, inline } from "../src/components/chat/Markdown";
import { flowPosition } from "../src/components/booking/BookingFlow";
import { needsReview } from "../src/voice";
import { parseRoute, pathOf } from "../src/app/routes";
import { notificationsFor } from "../src/components/shell/Topbar";
import type { BookingView, HandoffView, SessionView } from "../src/types";

const booking = (o: Partial<BookingView> = {}): BookingView => ({
  stage: "idle", package: null, options: [], date_iso: null, date_label: null, slot: null, slots: [], dates: [], ...o,
});
const none: HandoffView = { status: "none", ticket_id: null, note: "" };

describe("markdown", () => {
  it("groups list items and paragraphs", () => {
    const b = parseBlocks("Intro line\n\n- one\n- two\n\n1. a\n2. b");
    expect(b.map((x) => x.t)).toEqual(["p", "ul", "ol"]);
    expect(b[1]).toEqual({ t: "ul", items: ["one", "two"] });
  });
  it("never produces HTML from user/model text (script stays text)", () => {
    const nodes = inline("**bold** <script>alert(1)</script>");
    const flat = JSON.stringify(nodes);
    expect(flat).toContain("<script>alert(1)</script>"); // present only as a string child, React escapes it
    expect(flat).not.toContain("dangerouslySetInnerHTML");
  });
});

describe("flowPosition (6-step booking progress)", () => {
  it("is not started when idle", () => expect(flowPosition(booking(), false, none)).toEqual({ current: -1, result: null }));
  it("package step", () => expect(flowPosition(booking({ stage: "choosing_package" }), false, none).current).toBe(0));
  it("time step once a date is chosen, date step before", () => {
    expect(flowPosition(booking({ stage: "choosing_slot", date_iso: null }), false, none).current).toBe(1);
    expect(flowPosition(booking({ stage: "choosing_slot", date_iso: "2026-11-23" }), false, none).current).toBe(2);
  });
  it("review step while confirming", () => expect(flowPosition(booking({ stage: "confirming" }), false, none).current).toBe(3));
  it("only a backend-confirmed booking reaches result=confirmed", () => {
    expect(flowPosition(booking({ stage: "confirming" }), false, none).result).toBeNull();
    expect(flowPosition(booking(), true, none)).toEqual({ current: 5, result: "confirmed" });
  });
  it("handoff states are never reported as confirmed", () => {
    expect(flowPosition(booking(), false, { status: "pending", ticket_id: "T1", note: "" }).result).toBe("pending");
    expect(flowPosition(booking(), false, { status: "rejected", ticket_id: "T1", note: "" }).result).toBe("rejected");
  });
});

describe("voice booking safety (needsReview)", () => {
  it("does not hold ordinary speech outside a booking", () => expect(needsReview("what yoga helps", 0.4, "idle")).toBe(false));
  it("holds any time-like speech with low or unknown confidence while choosing a slot", () => {
    expect(needsReview("10:30 baje", 0.6, "choosing_slot")).toBe(true);
    expect(needsReview("kal subah 9 baje", null, "choosing_slot")).toBe(true);
    expect(needsReview("10:30 AM", 0.95, "choosing_slot")).toBe(false);
  });
  it("at confirmation only a clear, confident yes goes straight through", () => {
    expect(needsReview("yes confirm", 0.93, "confirming")).toBe(false);
    expect(needsReview("haan ji", 0.9, "confirming")).toBe(false);
    expect(needsReview("yes confirm", 0.5, "confirming")).toBe(true);
    expect(needsReview("yes confirm", null, "confirming")).toBe(true);
    expect(needsReview("maybe", 0.99, "confirming")).toBe(true);
    expect(needsReview("yesterday it was fine", 0.99, "confirming")).toBe(true);
  });
});

describe("routes", () => {
  it("parses known hashes and falls back to overview", () => {
    expect(parseRoute("")).toBe("overview");
    expect(parseRoute("#/")).toBe("overview");
    expect(parseRoute("#/voice")).toBe("voice");
    expect(parseRoute("#/coordinator")).toBe("coordinator");
    expect(parseRoute("#/nonsense")).toBe("overview");
    expect(pathOf("labs")).toBe("#/labs");
  });
});

describe("notifications are derived from real session state only", () => {
  const base = { session_id: "s", member: { member_id: "MEM_1001", name: "A", age: 1, language_preference: "en" }, status: "active", triage_status: "GREEN_NORMAL", messages: [], booking: booking(), handoff: none, bookings: [] } as SessionView;
  it("is empty for a fresh session and for no session", () => {
    expect(notificationsFor(base)).toEqual([]);
    expect(notificationsFor(null)).toEqual([]);
  });
  it("reports emergency, pending handoff and bookings", () => {
    const s = { ...base, triage_status: "RED_CRISIS", handoff: { status: "pending", ticket_id: "T9", note: "" }, bookings: [{ booking_id: "B", package_name: "P", date: "d", slot: "s" }] } as SessionView;
    expect(notificationsFor(s).map((n) => n.id).sort()).toEqual(["b", "emg", "h"]);
  });
});

import { mimiFromVoice } from "../src/components/mimi/mimiState";
describe("Mimi expression follows the real voice lifecycle", () => {
  it("maps each voice state", () => {
    expect(mimiFromVoice("idle", false)).toBe("idle");
    expect(mimiFromVoice("listening", false)).toBe("listening");
    expect(mimiFromVoice("interrupted", false)).toBe("listening");
    expect(mimiFromVoice("processing", false)).toBe("thinking");
    expect(mimiFromVoice("thinking", false)).toBe("thinking");
    expect(mimiFromVoice("speaking", false)).toBe("speaking");
    expect(mimiFromVoice("error", false)).toBe("error");
  });
  it("celebrates only when not speaking; errors always win; speech is never cut by a celebration", () => {
    expect(mimiFromVoice("idle", true)).toBe("success");
    expect(mimiFromVoice("speaking", true)).toBe("speaking");
    expect(mimiFromVoice("error", true)).toBe("error");
  });
});

import { lastMeal, median, perTest, summarize, categoryCounts } from "../src/insights";
const pk = (id: string, price: number, tests: number, fast = 0) => ({ package_id: id, name: id, price_inr: price, test_count: tests, fasting_required: fast > 0, fasting_hours: fast });
describe("insights calculations (pure arithmetic on catalogue data)", () => {
  it("median handles odd, even and empty", () => { expect(median([3, 1, 2])).toBe(2); expect(median([1, 2, 3, 10])).toBe(2.5); expect(median([])).toBe(0); });
  it("per-test price and summary picks the right extremes", () => {
    const s = summarize([pk("A", 600, 3, 0), pk("B", 3000, 60, 12), pk("C", 1000, 2, 10)])!;
    expect(perTest(pk("A", 600, 3))).toBe(200);
    expect(s.count).toBe(3); expect(s.fastingCount).toBe(2); expect(s.noFastCount).toBe(1);
    expect(s.cheapest.package_id).toBe("A"); expect(s.priciest.package_id).toBe("B");
    expect(s.bestValue.package_id).toBe("B"); expect(s.mostTests.package_id).toBe("B"); expect(s.medianPrice).toBe(1000);
    expect(summarize([])).toBeNull();
  });
  it("counts programs per category, largest first", () => {
    expect(categoryCounts([{ doc_id: "1", title: "a", category: "Yoga" }, { doc_id: "2", title: "b", category: "Diet" }, { doc_id: "3", title: "c", category: "Yoga" }])).toEqual([["Yoga", 2], ["Diet", 1]]);
  });
  it("last meal: same morning vs evening before, and unparseable slots", () => {
    expect(lastMeal("10:30 AM", 8)).toEqual({ time: "02:30 AM", previousDay: false });
    expect(lastMeal("08:00 AM", 12)).toEqual({ time: "08:00 PM", previousDay: true });
    expect(lastMeal("07:30 AM", 10)).toEqual({ time: "09:30 PM", previousDay: true });
    expect(lastMeal("soon", 8)).toBeNull();
  });
});
