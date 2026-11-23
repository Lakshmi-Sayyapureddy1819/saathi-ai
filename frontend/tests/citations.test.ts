import { describe, expect, it } from "vitest";
import { stripCites } from "../src/components/chat/ChatMessage";
import { toSpeakable } from "../src/voice";
import type { Citation } from "../src/types";

const c = (id: string): Citation => ({ source_id: id, title: id, kind: "document", cited: true });

describe("citations in the UI", () => {
  it("removes verified [ID] markers from the visible answer and tidies spacing", () => {
    expect(stripCites("Start slowly [PROG_Y_001]. Then rest [PROG_Y_002].", [c("PROG_Y_001"), c("PROG_Y_002")]))
      .toBe("Start slowly. Then rest.");
  });
  it("leaves unrelated bracketed text alone", () => {
    expect(stripCites("Take a break [optional] [PROG_Y_001]", [c("PROG_Y_001")])).toBe("Take a break [optional]");
  });
  it("never reads citation markers aloud", () => {
    expect(toSpeakable("Kapalbhati is a breathing practice [PROG_P_002]. Also [bookings].")).not.toMatch(/PROG|bookings|\[/);
  });
});
