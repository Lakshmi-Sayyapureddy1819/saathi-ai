import { describe, expect, it } from "vitest";
import { toSpeakable } from "../src/voice";

describe("toSpeakable", () => {
  it("spells booking ids digit by digit so ASR/TTS round trips are unambiguous", () => {
    expect(toSpeakable("Your booking BK-1234 is confirmed")).toContain("1 2 3 4");
  });
  it("strips markdown and emoji", () => {
    expect(toSpeakable("**Booked** ✅ done")).toBe("Booked done");
  });
});
