import { expect, test, type Page } from "@playwright/test";

// Voice screen tests. A headless browser has no speech engine, so ONLY the browser's SpeechRecognition / speechSynthesis
// (and, for error cases, getUserMedia) are replaced by test doubles. Everything else is real: the backend, the safety
// gate, the booking flow, the microphone-level meter (Edge launches with a fake audio device, see playwright.config.ts).
const SHOTS = "e2e/screenshots";

function installSpeechDoubles() {
  const w = window as unknown as Record<string, unknown>;
  class FakeRec {
    lang = ""; interimResults = false; continuous = false;
    onresult: ((e: unknown) => void) | null = null; onend: (() => void) | null = null; onerror: ((e: { error: string }) => void) | null = null;
    start() { w.__rec = this; if (w.__recError) setTimeout(() => this.onerror?.({ error: String(w.__recError) }), 0); }
    stop() { setTimeout(() => this.onend?.(), 0); }
    abort() { /* noop */ }
  }
  w.SpeechRecognition = FakeRec;
  w.__heard = (text: string, confidence: number) => {
    const r = w.__rec as FakeRec;
    r.onresult?.({ results: [Object.assign([{ transcript: text, confidence }], { isFinal: true })] });
  };
  w.__spoken = [] as string[];
  const synth = {
    speak(u: { text: string; onstart?: () => void; onend?: () => void }) {
      (w.__spoken as string[]).push(u.text);
      setTimeout(() => u.onstart?.(), 0);
      // real engines (Chrome/Edge local voices) emit one boundary event per word; the double mimics that
      if (w.__boundaries) { const words = u.text.split(/s+/); words.forEach((word, i) => setTimeout(() => (u as unknown as { onboundary?: (e: unknown) => void }).onboundary?.({ name: "word", charLength: word.length }), 120 + i * 140)); }
      setTimeout(() => u.onend?.(), 2500);
    },
    cancel() { /* noop */ },
  };
  Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
}

const heard = (page: Page, text: string, confidence: number) =>
  page.evaluate(([t, c]) => (window as unknown as { __heard: (a: string, b: number) => void }).__heard(t as string, c as number), [text, confidence]);
const badge = (page: Page) => page.getByTestId("voice-state-badge");

async function openVoice(page: Page, member = "MEM_1002") {
  await page.goto("/#/");
  await expect(page.getByTestId("start-chat")).toBeEnabled();
  await page.locator("#member").selectOption(member);
  await page.getByTestId("start-chat").click();
  await expect(page.getByTestId("chat-empty")).toBeVisible();
  await page.getByTestId("nav-voice").click();
  await expect(badge(page)).toHaveText("Ready to listen");
}

test("voice: idle -> connecting -> listening -> thinking -> speaking -> listening, with real transcript and real mic level meter", async ({ page }) => {
  await page.addInitScript(installSpeechDoubles);
  await openVoice(page);
  await expect(page.getByTestId("voice-state-label")).toContainText("Namaste! How can I help you today?");
  await page.screenshot({ path: `${SHOTS}/v1-voice-idle.png` });

  // slow the real backend a little so the Thinking state is observable
  await page.route("**/api/sessions/*/messages", async (route) => { await new Promise((r) => setTimeout(r, 1500)); await route.continue(); });

  await page.getByTestId("voice-start").click();
  await expect(badge(page)).toHaveText("Listening");
  await expect(page.getByTestId("voice-orb")).toHaveClass(/has-level/); // real AnalyserNode on the (fake-device) microphone
  await expect(page.getByTestId("voice-live")).toContainText("Listening");
  await page.screenshot({ path: `${SHOTS}/v2-voice-listening.png` });

  await heard(page, "What yoga helps with exhaustion?", 0.93);
  await expect(badge(page)).toHaveText("Thinking");
  await page.screenshot({ path: `${SHOTS}/v3-voice-thinking.png` });
  await expect(badge(page)).toHaveText("Speaking", { timeout: 15_000 });
  await page.screenshot({ path: `${SHOTS}/v4-voice-speaking.png` });
  await expect(page.getByTestId("voice-transcript")).toContainText("What yoga helps with exhaustion?");
  await expect(page.getByTestId("voice-transcript")).toContainText("[MOCK"); // real backend reply, labelled as demo
  const spoken = await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken);
  expect(spoken.join(" ")).toContain("MOCK"); // the reply text is what gets handed to the speaker

  await expect(badge(page)).toHaveText("Listening", { timeout: 15_000 }); // hands-free loop resumes after speaking
});

test("voice: interrupt, mute/unmute, end, return to chat", async ({ page }) => {
  await page.addInitScript(installSpeechDoubles);
  await openVoice(page);
  await page.getByTestId("voice-start").click();
  await expect(badge(page)).toHaveText("Listening");
  await heard(page, "namaste", 0.95);
  await expect(badge(page)).toHaveText("Speaking", { timeout: 15_000 });
  await page.getByTestId("voice-interrupt").click();
  await expect(badge(page)).toHaveText("Interrupted");
  await page.screenshot({ path: `${SHOTS}/v5-voice-interrupted.png` });
  await expect(badge(page)).toHaveText("Listening", { timeout: 10_000 });

  await page.getByTestId("voice-mute").click();
  await expect(page.getByTestId("voice-mute")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".vs-status")).toContainText("Microphone muted. Unmute to continue.");
  await expect(badge(page)).toHaveText("Ready to listen");
  await page.getByTestId("voice-mute").click();
  await expect(badge(page)).toHaveText("Listening", { timeout: 5_000 });

  await page.getByTestId("voice-end").click();
  await expect(badge(page)).toHaveText("Conversation ended");
  await expect(page.getByTestId("voice-start")).toContainText("Start a new voice conversation");
  await page.screenshot({ path: `${SHOTS}/v6-voice-ended.png` });
  await page.getByTestId("voice-to-chat").click();
  await expect(page.locator("#main")).toContainText("Saathi");
  await expect(page.locator("#msg")).toBeVisible();
});

test("voice booking safety: uncertain time is held for confirmation, readback needs explicit confirm, real result shown", async ({ page }) => {
  await page.addInitScript(installSpeechDoubles);
  await openVoice(page, "MEM_1002");
  await page.getByTestId("voice-start").click();
  await expect(badge(page)).toHaveText("Listening");

  await heard(page, "book thyroid test", 0.95);
  await expect(page.getByTestId("voice-transcript")).toContainText("Available slots", { timeout: 15_000 });
  await expect(badge(page)).toHaveText("Listening", { timeout: 15_000 });

  // low-confidence time: NOT sent. The user must confirm what was heard.
  const before = await page.getByTestId("msg-user").count();
  await heard(page, "9 baje", 0.55);
  await expect(page.getByTestId("voice-review")).toContainText("I heard: “9 baje”. Is that correct?");
  await expect(badge(page)).toHaveText("Processing");
  await page.screenshot({ path: `${SHOTS}/v7-voice-review.png` });
  await expect(page.getByTestId("msg-user")).toHaveCount(before); // nothing was sent to the backend
  await page.getByTestId("voice-review-no").click();
  await expect(page.getByTestId("voice-review")).toHaveCount(0);
  await expect(badge(page)).toHaveText("Listening", { timeout: 10_000 });

  await heard(page, "09:00 AM", 0.96); // clear, confident
  await expect(page.getByTestId("voice-readback")).toContainText("Thyroid Screening Profile", { timeout: 15_000 });
  await expect(page.getByTestId("voice-readback")).toContainText("09:00 AM");
  await expect(page.getByTestId("msg-booking_confirmed")).toHaveCount(0); // read back, not yet booked
  await page.screenshot({ path: `${SHOTS}/v8-voice-readback.png` });
  await expect(badge(page)).toHaveText("Listening", { timeout: 15_000 });

  // an unclear "yes" is held, not treated as consent
  await heard(page, "yes confirm", 0.4);
  await expect(page.getByTestId("voice-review")).toBeVisible();
  await expect(page.getByTestId("msg-booking_confirmed")).toHaveCount(0);
  await page.getByTestId("voice-review-no").click();

  // explicit tap on Confirm -> backend books -> real confirmation with id
  await page.getByTestId("voice-confirm").click();
  await expect(page.getByTestId("msg-booking_confirmed")).toContainText(/BOK_MEM_1002_\d{4}/, { timeout: 15_000 });
});

test("voice errors: permission denied, no microphone, unsupported browser, server unreachable, speech service error", async ({ page, browser }) => {
  test.setTimeout(150_000); // five sub-scenarios, each with its own browser context
  // permission denied
  await page.addInitScript(installSpeechDoubles);
  await page.addInitScript(() => { navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException("denied", "NotAllowedError")); });
  await openVoice(page);
  await page.getByTestId("voice-start").click();
  await expect(page.getByTestId("voice-error")).toContainText("Microphone access was blocked");
  await expect(page.getByTestId("voice-error")).toContainText("allow the microphone"); // says how to recover
  await expect(page.getByTestId("voice-error")).toHaveAttribute("role", "alert");
  await expect(badge(page)).toHaveText("Something went wrong");
  await expect(page.getByTestId("voice-start")).toContainText("Try again");
  await page.screenshot({ path: `${SHOTS}/v9-voice-error-denied.png` });

  // no microphone device
  const ctx2 = await browser.newContext();
  const p2 = await ctx2.newPage();
  await p2.addInitScript(installSpeechDoubles);
  await p2.addInitScript(() => { navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException("none", "NotFoundError")); });
  await openVoice(p2);
  await p2.getByTestId("voice-start").click();
  await expect(p2.getByTestId("voice-error")).toContainText("No microphone found");
  await ctx2.close();

  // unsupported browser (no speech recognition at all)
  const ctx3 = await browser.newContext();
  const p3 = await ctx3.newPage();
  await p3.addInitScript(() => {
    Object.defineProperty(window, "SpeechRecognition", { value: undefined, configurable: true });
    Object.defineProperty(window, "webkitSpeechRecognition", { value: undefined, configurable: true });
  });
  await openVoice(p3);
  await expect(p3.getByTestId("voice-unsupported")).toContainText("Voice isn't available in this browser");
  await p3.getByTestId("voice-start").click();
  await expect(p3.getByTestId("voice-error")).toContainText("isn't supported in this browser");
  await p3.screenshot({ path: `${SHOTS}/v10-voice-unsupported.png` });
  await ctx3.close();

  // Saathi server unreachable on connect, then recovery with "Try again"
  const ctx4 = await browser.newContext();
  const p4 = await ctx4.newPage();
  await p4.addInitScript(installSpeechDoubles);
  await openVoice(p4);
  await p4.route("**/api/config", (r) => r.abort());
  await p4.getByTestId("voice-start").click();
  await expect(p4.getByTestId("voice-error")).toContainText("Can't reach the speech or Saathi service");
  await p4.unroute("**/api/config");
  await p4.getByTestId("voice-start").click();
  await expect(badge(p4)).toHaveText("Listening");
  await ctx4.close();

  // browser speech service error (e.g. offline) while listening
  const ctx5 = await browser.newContext();
  const p5 = await ctx5.newPage();
  await p5.addInitScript(installSpeechDoubles);
  await p5.addInitScript(() => { (window as unknown as Record<string, unknown>).__recError = "network"; });
  await openVoice(p5);
  await p5.getByTestId("voice-start").click();
  await expect(p5.getByTestId("voice-error")).toContainText("Can't reach the speech or Saathi service");
  await ctx5.close();
});

test("voice: emergency speech gets deterministic emergency guidance and does not auto-listen again", async ({ page }) => {
  await page.addInitScript(installSpeechDoubles);
  await openVoice(page);
  await page.getByTestId("voice-start").click();
  await expect(badge(page)).toHaveText("Listening");
  await heard(page, "I have severe chest pain", 0.9);
  await expect(page.getByTestId("msg-emergency")).toContainText("112", { timeout: 15_000 });
  await expect(page.getByTestId("msg-emergency")).toHaveAttribute("role", "alert");
  await expect(badge(page)).toHaveText("Speaking");
  await expect(badge(page)).toHaveText("Ready to listen", { timeout: 15_000 }); // halted after emergency, user chooses
  await expect(page.locator(".vs-status")).toContainText("Emergency guidance was shown");
  await page.screenshot({ path: `${SHOTS}/v11-voice-emergency.png` });
});

test("voice: reduced motion disables orb animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(installSpeechDoubles);
  await openVoice(page);
  const dur = await page.locator(".orb .core").evaluate((el) => getComputedStyle(el).animationDuration);
  expect(parseFloat(dur)).toBeLessThan(0.01);
});

test("voice orb: state follows the voice lifecycle; Mimi is shown inside the orb", async ({ page }) => {
  await page.addInitScript(installSpeechDoubles);
  await openVoice(page);
  const orb = page.getByTestId("voice-orb");
  await expect(orb).toHaveAttribute("data-state", "idle");
  await expect(page.getByTestId("voice-orb").getByTestId("mimi")).toBeVisible();
  await page.getByTestId("voice-start").click();
  await expect(orb).toHaveAttribute("data-state", "listening");
  await expect(orb.getByTestId("mimi")).toHaveAttribute("data-state", "listening");
  await page.route("**/api/sessions/*/messages", async (route) => { await new Promise((r) => setTimeout(r, 1200)); await route.continue(); });
  await heard(page, "namaste", 0.95);
  await expect(orb).toHaveAttribute("data-state", "thinking");
  await expect(orb).toHaveAttribute("data-state", "speaking", { timeout: 15_000 });
  await page.screenshot({ path: `${SHOTS}/m1-voice-speaking.png` });
  await page.getByTestId("voice-end").click();
});

test("voice orb: error state when the microphone is denied; Mimi still appears beside chat replies", async ({ page }) => {
  await page.addInitScript(installSpeechDoubles);
  await page.addInitScript(() => { navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException("denied", "NotAllowedError")); });
  await openVoice(page);
  await page.getByTestId("voice-start").click();
  await expect(page.getByTestId("voice-orb")).toHaveAttribute("data-state", "error");
  await page.screenshot({ path: `${SHOTS}/m2-voice-error.png` });
  await page.getByTestId("nav-chat").click();
  await page.locator("#msg").fill("hello");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("msg-answer")).toBeVisible();
  await expect(page.locator(".msg.assistant .mimi").first()).toBeVisible();
});
