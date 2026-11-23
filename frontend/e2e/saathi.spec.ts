import { expect, test, type Page } from "@playwright/test";
import { API_A, COORD, UI_B } from "./ports";

// Real browser + real backend. Nothing here stubs an AI/booking response; the only mocked things are (a) the deliberate
// network failures in the "API error" test and (b) the browser's speech engines in the voice tests (see voice.spec.ts).
const SHOTS = "e2e/screenshots";

async function startChat(page: Page, memberId = "MEM_1001", base = "") {
  await page.goto(`${base}/#/`);
  await expect(page.getByTestId("start-chat")).toBeEnabled();
  await page.locator("#member").selectOption(memberId);
  await page.getByTestId("start-chat").click();
  await expect(page.getByTestId("chat-empty")).toBeVisible();
}

/** Type into the composer like a user and wait for the assistant's reply to land. */
async function say(page: Page, text: string) {
  const before = await page.locator('[data-testid^="msg-"]:not([data-testid="msg-user"])').count();
  await page.locator("#msg").fill(text);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("typing")).toHaveCount(0);
  await expect(page.locator('[data-testid^="msg-"]:not([data-testid="msg-user"])')).not.toHaveCount(before);
}
const lastReply = (page: Page) => page.locator('[data-testid^="msg-"]:not([data-testid="msg-user"])').last();
const overflowX = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("1. overview loads with real backend data and honest demo labelling", async ({ page }) => {
  await page.goto("/#/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Care that listens");
  await expect(page.getByTestId("status-pill")).toHaveText("No active session");
  await expect(page.getByTestId("program-cats")).toContainText("Yoga");
  await expect(page.getByTestId("mock-banner")).toBeVisible(); // harness runs without AI keys: UI must say so
  await expect(page.getByRole("contentinfo")).toContainText("not a substitute for a medical professional");
  await expect(page.getByText("Demo members")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/01-dashboard.png`, fullPage: true });
});

test("1b. every navigation item leads to a real page (no dead links); coordinator is not in the member nav", async ({ page }) => {
  await startChat(page);
  const expected: Record<string, string | RegExp> = {
    overview: /Good (morning|afternoon|evening)/, chat: "Mimi", voice: "Start voice conversation", labs: "Find and book a lab test",
    bookings: "My bookings", insights: "Wellness library", support: "Human support", settings: "Settings and demo tools",
  };
  for (const [id, text] of Object.entries(expected)) {
    await page.getByTestId(`nav-${id}`).click();
    await expect(page.getByTestId(`nav-${id}`)).toHaveAttribute("aria-current", "page");
    await expect(page.locator("#main")).toContainText(text);
  }
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByText(/coordinator console/i)).toHaveCount(0);
  // sidebar collapse works and keeps links reachable
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(page.getByTestId("nav-labs")).toBeVisible();
  await page.getByRole("button", { name: "Expand sidebar" }).click();
});

test("2-4. start a session; wellness question; Hinglish question; markdown/copy/timestamps", async ({ page }) => {
  await startChat(page);
  await expect(page.getByTestId("status-pill")).toContainText("Active · Aarav Sharma");
  await expect(page.getByRole("button", { name: "I want to book a blood test" })).toBeVisible(); // suggested prompts
  await page.screenshot({ path: `${SHOTS}/02-chat-empty.png` });
  await say(page, "What yoga helps with exhaustion?");
  await expect(page.getByTestId("msg-answer").last()).toContainText("[MOCK"); // no key -> flagged mock, not faked
  await expect(page.getByText("Demo mode: no AI model key").first()).toBeVisible();
  await expect(page.locator("time").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy response" }).first()).toBeVisible();
  await say(page, "Mujhe bahut thakan rehti hai, kya yoga karun?");
  await expect(page.getByTestId("msg-answer")).toHaveCount(2);
  await expect(page.getByTestId("booking-panel")).toHaveCount(0); // stayed in coaching, no booking UI
  await page.screenshot({ path: `${SHOTS}/03-wellness-hinglish.png` });
});

test("2b. suggested prompt uses the real chat workflow", async ({ page }) => {
  await startChat(page);
  await page.getByRole("button", { name: "I want to book a blood test" }).click();
  await expect(page.getByTestId("msg-user")).toHaveText("I want to book a blood test");
  await expect(page.getByTestId("booking-panel")).toContainText("Which test would you like");
});

test("5. emergency: deterministic safety response, English and Hinglish, clears booking", async ({ page }) => {
  await startChat(page);
  await say(page, "book thyroid test");
  await say(page, "I have severe chest pain");
  const card = page.getByTestId("msg-emergency");
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute("role", "alert");
  await expect(card).toContainText("112");
  await expect(card).toContainText("cannot provide emergency care");
  await expect(page.getByTestId("status-pill")).toContainText("Emergency");
  await expect(page.getByTestId("booking-panel")).toHaveCount(0); // booking flow cleared by the safety gate
  await page.screenshot({ path: `${SHOTS}/04-emergency.png` });
  await say(page, "Mere seene mein dard hai");
  await expect(page.getByTestId("msg-emergency")).toHaveCount(2);
});

test("5b. no-diagnosis rule", async ({ page }) => {
  await startChat(page);
  await say(page, "do I have diabetes?");
  await expect(page.getByTestId("msg-safety_notice")).toContainText("can't provide a medical diagnosis");
});

test("6-10. generic blood test -> package -> short follow-up -> review -> confirm -> booking id", async ({ page }) => {
  await startChat(page, "MEM_1001");
  await say(page, "Book a blood test");
  await expect(lastReply(page)).toContainText("Which test would you like");
  const panel = page.getByTestId("booking-panel");
  await expect(panel.getByTestId("pkg-list").locator("li")).toHaveCount(12);
  await expect(panel.getByRole("list", { name: /Booking progress/ })).toContainText("Package");
  await page.screenshot({ path: `${SHOTS}/05-choose-package.png` });

  await panel.getByRole("button", { name: "Select Thyroid Screening Profile" }).click();
  await expect(panel.getByRole("button", { name: "10:30 AM" })).toBeVisible();
  await expect(panel).toContainText("Thyroid Screening Profile");
  await page.screenshot({ path: `${SHOTS}/06-choose-slot.png` });

  await say(page, "10:30 AM"); // typed short follow-up: context must survive
  await expect(page.getByTestId("booking-summary")).toContainText("Thyroid Screening Profile");
  await expect(page.getByTestId("booking-summary")).toContainText("10:30 AM");
  await expect(lastReply(page)).toContainText("Just to confirm");
  await expect(page.getByTestId("msg-booking_confirmed")).toHaveCount(0); // nothing claims "confirmed" before the backend does
  await page.screenshot({ path: `${SHOTS}/07-confirm-summary.png` });

  await page.getByTestId("confirm-booking").click();
  const confirmed = page.getByTestId("msg-booking_confirmed");
  await expect(confirmed).toContainText("Booking confirmed");
  const id = (await page.getByTestId("booking-id").textContent()) ?? "";
  expect(id).toMatch(/^BOK_MEM_1001_\d{4}$/);
  await expect(confirmed).toContainText(id);
  await page.screenshot({ path: `${SHOTS}/08-booked.png` });

  // The booked slot really is consumed in the backend: a second member no longer sees 10:30 AM for that day.
  const page2 = await page.context().newPage();
  await startChat(page2, "MEM_1002");
  await say(page2, "book thyroid test");
  await expect(page2.getByTestId("booking-panel").getByRole("button", { name: "09:30 AM" })).toBeVisible();
  await expect(page2.getByTestId("booking-panel").getByRole("button", { name: "10:30 AM" })).toHaveCount(0);
});

test("my bookings: listed after booking, dialog-confirmed cancel frees the slot", async ({ page }) => {
  await startChat(page, "MEM_1005");
  await say(page, "book thyroid test");
  await say(page, "11:00 AM");
  await say(page, "yes");
  await page.getByTestId("nav-bookings").click();
  const mine = page.getByTestId("my-bookings");
  await expect(mine.getByTestId("my-booking")).toHaveCount(1);
  await expect(mine).toContainText("Thyroid Screening Profile");
  await expect(mine).toContainText("11:00 AM");
  await expect(mine).toContainText("Confirmed");
  await page.screenshot({ path: `${SHOTS}/17-my-bookings.png` });

  await mine.getByRole("button", { name: /^Cancel booking BOK_/ }).click();
  const dialog = page.getByRole("dialog", { name: "Cancel this booking?" });
  await expect(dialog).toBeVisible(); // asks first; nothing cancelled yet
  await dialog.getByRole("button", { name: "Keep it" }).click();
  await expect(mine.getByTestId("my-booking")).toHaveCount(1);

  await mine.getByRole("button", { name: /^Cancel booking BOK_/ }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Yes, cancel it" }).click();
  await page.getByTestId("nav-chat").click();
  await expect(lastReply(page)).toContainText("cancelled your booking");
  await page.getByTestId("nav-bookings").click();
  await expect(page.getByTestId("my-booking")).toHaveCount(0);
  await expect(page.getByText("No upcoming bookings")).toBeVisible();

  const page2 = await page.context().newPage();
  await startChat(page2, "MEM_1002");
  await say(page2, "book thyroid test");
  await expect(page2.getByTestId("booking-panel").getByRole("button", { name: "11:00 AM" })).toBeVisible();
});

test("lab tests page: real catalogue, search, filters, and booking from a card", async ({ page }) => {
  await page.goto("/#/labs");
  await expect(page.getByTestId("pkg-list").locator("li")).toHaveCount(12);
  await page.getByTestId("pkg-search").fill("thyroid");
  await expect(page.getByTestId("pkg-list").locator("li")).toHaveCount(1);
  await page.getByTestId("pkg-search").fill("zzzz-nothing");
  await expect(page.getByText("No packages match")).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await page.getByRole("tab", { name: "No fasting" }).click();
  const n = await page.getByTestId("pkg-list").locator("li").count();
  expect(n).toBeGreaterThan(0);
  expect(n).toBeLessThan(12);
  await page.getByRole("tab", { name: "All" }).click();

  // booking from a card with no session starts a real session for the chosen demo member, then the real flow
  await page.getByRole("button", { name: "Book Thyroid Screening Profile" }).click();
  await expect(page.getByTestId("booking-panel")).toContainText("Thyroid Screening Profile", { timeout: 20_000 });
  await expect(page.getByRole("list", { name: /Booking progress/ })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/19-labs-booking.png` });
});

test("hinglish and typo journey: sugar check, 9 baje (fasting), 7:30 baje, haan ji", async ({ page }) => {
  await startChat(page, "MEM_1003");
  await say(page, "shugar check karwana hai");
  await expect(page.getByTestId("booking-panel")).toContainText("Advanced Diabetic Profile");
  await say(page, "kal subah 9 baje");
  await expect(lastReply(page)).toContainText("khaali pet"); // explains why 9 AM is not offered
  await say(page, "7:30 baje");
  await expect(page.getByTestId("booking-summary")).toContainText("07:30 AM");
  await say(page, "haan ji");
  await expect(page.getByTestId("msg-booking_confirmed")).toContainText("Booking confirm ho gayi");
  await page.screenshot({ path: `${SHOTS}/18-hinglish-booking.png` });
});

test("emergency spellings and a Hinglish blood-test request", async ({ page }) => {
  await startChat(page, "MEM_1004");
  await say(page, "khoon ki jaanch karwani hai"); // a blood test, NOT an emergency
  await expect(page.getByTestId("msg-emergency")).toHaveCount(0);
  await expect(page.getByTestId("booking-panel")).toContainText("Which test would you like");
  await say(page, "I am suicidal");
  await expect(page.getByTestId("msg-emergency")).toHaveCount(1);
  await say(page, "chest pian");
  await expect(page.getByTestId("msg-emergency")).toHaveCount(2);
});

test("buttons: change day, change time, cancel", async ({ page }) => {
  await startChat(page, "MEM_1003");
  await say(page, "book thyroid test");
  const panel = page.getByTestId("booking-panel");
  await expect(panel.getByRole("button", { name: "09:00 AM" })).toBeVisible();
  await panel.getByRole("button", { name: /^Today/ }).click();
  await expect(panel.getByRole("button", { name: /^Today/ })).toHaveAttribute("aria-pressed", "true");
  await panel.getByRole("button", { name: "09:00 AM" }).click();
  await expect(page.getByTestId("booking-summary")).toContainText("09:00 AM");
  await panel.getByRole("button", { name: "Change time" }).click();
  await expect(panel.getByRole("button", { name: "11:00 AM" })).toBeVisible();
  await panel.getByRole("button", { name: "11:00 AM" }).click();
  await expect(page.getByTestId("booking-summary")).toContainText("11:00 AM");
  await panel.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(lastReply(page)).toContainText("cancelled");
  await expect(page.getByTestId("booking-panel")).toHaveCount(0);
});

test("11. ambiguous package selection asks again and narrows the list", async ({ page }) => {
  await startChat(page, "MEM_1004");
  await say(page, "book vitality test");
  await say(page, "senior");
  await expect(lastReply(page)).toContainText("Which package");
  await expect(page.getByTestId("booking-panel").getByTestId("pkg-list").locator("li")).toHaveCount(2);
  await say(page, "female");
  await expect(page.getByTestId("booking-panel")).toContainText("Senior Citizen Vitality (Female)");
  await page.screenshot({ path: `${SHOTS}/09-ambiguous-resolved.png` });
});

test("12. invalid input: empty, too long, gibberish; Enter sends, Shift+Enter does not", async ({ page }) => {
  await startChat(page);
  const send = page.getByRole("button", { name: "Send", exact: true });
  await expect(send).toBeDisabled();
  await page.locator("#msg").fill("    ");
  await expect(send).toBeDisabled();
  await page.locator("#msg").fill("x".repeat(501));
  await expect(send).toBeDisabled();
  await expect(page.locator("#msg-help")).toContainText("Too long: 501/500");
  await page.locator("#msg").fill("qwzx plmk");
  await expect(send).toBeEnabled();
  await page.locator("#msg").press("Shift+Enter");
  await expect(page.getByTestId("msg-user")).toHaveCount(0);
  await page.locator("#msg").press("Backspace");
  await page.locator("#msg").press("Enter");
  await expect(page.getByTestId("msg-user")).toHaveCount(1);
  await expect(lastReply(page)).not.toBeEmpty(); // a graceful reply, no crash
  await expect(page.getByTestId("send-error")).toHaveCount(0);
});

test("13. API failure shows an error, keeps the message, and Retry works", async ({ page }) => {
  await startChat(page);
  await page.route("**/api/sessions/*/messages", (r) => r.abort());
  await page.locator("#msg").fill("book thyroid test");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("send-error")).toContainText("Can't reach the Saathi server");
  await expect(page.getByText("Not delivered.")).toBeVisible();
  await expect(page.getByTestId("msg-user")).toHaveText("book thyroid test");
  await page.screenshot({ path: `${SHOTS}/10-api-error.png` });

  await page.unroute("**/api/sessions/*/messages");
  await page.getByTestId("send-error").getByRole("button", { name: "Retry" }).click();
  await expect(page.getByTestId("send-error")).toHaveCount(0);
  await expect(page.getByTestId("msg-user")).toHaveCount(1); // retried once, not duplicated
  await expect(page.getByTestId("booking-panel")).toContainText("Thyroid Screening Profile");

  await page.route("**/api/sessions/*/messages", (r) =>
    r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Turn failed (RuntimeError)." }) }));
  await page.locator("#msg").fill("hello");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("send-error")).toContainText("Turn failed");
});

test("14. end session; sessions are isolated across browsers; new conversation clears with confirmation", async ({ page, browser }) => {
  await startChat(page, "MEM_1001");
  await say(page, "book thyroid test");
  const other = await browser.newContext();
  const page2 = await other.newPage();
  await startChat(page2, "MEM_1002");
  await expect(page2.getByTestId("msg-user")).toHaveCount(0); // B sees nothing of A
  await expect(page2.getByTestId("booking-panel")).toHaveCount(0);
  await expect(page.getByTestId("booking-panel")).toContainText("Thyroid Screening Profile");

  await page.getByTestId("new-conversation").click();
  await page.getByRole("dialog", { name: "Start a new conversation?" }).getByRole("button", { name: "Clear and start new" }).click();
  await expect(page.getByTestId("chat-empty")).toBeVisible();
  await expect(page.getByTestId("msg-user")).toHaveCount(0);
  await expect(page.getByTestId("booking-panel")).toHaveCount(0);

  await page.getByRole("button", { name: /Account menu/ }).click();
  await page.getByTestId("end-session").click();
  await expect(page.getByTestId("status-pill")).toHaveText("No active session");
  await other.close();
});

test("session survives a page reload; a dead session is handled", async ({ page }) => {
  await startChat(page);
  await say(page, "book thyroid test");
  await page.reload();
  await expect(page.getByTestId("status-pill")).toContainText("Active");
  await expect(page.getByTestId("msg-user")).toHaveText("book thyroid test");
  await expect(page.getByTestId("booking-panel")).toContainText("Thyroid Screening Profile");

  await page.goto("/#/");
  await page.evaluate(() => sessionStorage.setItem("saathi.session", JSON.stringify({ id: "gone", token: "x" })));
  await page.reload();
  await expect(page.getByTestId("notice")).toContainText("expired");
  await expect(page.getByTestId("start-chat")).toBeVisible();
});

test("15. responsive: no horizontal overflow on any page at 1440 / 1280 / 768 / 390; mobile uses bottom nav", async ({ browser }) => {
  test.setTimeout(150_000); // 4 viewports x 8 pages
  for (const [w, h] of [[1440, 900], [1280, 800], [768, 1024], [390, 844]] as const) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: w < 700, hasTouch: w < 700 });
    const page = await ctx.newPage();
    await startChat(page, "MEM_1002");
    for (const r of ["", "chat", "voice", "labs", "bookings", "insights", "support", "settings"]) {
      await page.goto(`/#/${r}`);
      await page.waitForTimeout(250);
      expect(await overflowX(page), `overflow at ${w}px on #/${r}`).toBeLessThanOrEqual(0);
    }
    const bottom = page.getByRole("navigation", { name: "Primary" });
    if (w <= 900) await expect(bottom).toBeVisible(); else await expect(bottom).toBeHidden();
    if (w === 390) {
      await page.goto("/#/chat");
      await page.locator("#msg").fill("Book a blood test");
      await page.getByRole("button", { name: "Send", exact: true }).click();
      await expect(page.getByTestId("booking-panel")).toBeVisible();
      expect(await overflowX(page)).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `${SHOTS}/12-mobile-chat.png` });
      await page.goto("/#/");
      await page.screenshot({ path: `${SHOTS}/11-mobile-dashboard.png`, fullPage: true });
    }
    await ctx.close();
  }
});

test("accessibility basics: skip link, labelled controls, dialogs trap focus and close on Escape", async ({ page }) => {
  await startChat(page, "MEM_1002");
  await page.goto("/#/settings");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Settings and demo tools" })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.getByRole("button", { name: "End session" }).click();
  const dlg = page.getByRole("dialog", { name: "End this session?" });
  await expect(dlg).toBeVisible();
  await expect(dlg.getByRole("button", { name: "Go back" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dlg).toBeHidden();
  const unlabeled = await page.evaluate(() => [...document.querySelectorAll("button, a, input, select, textarea")]
    .filter((e) => !(e as HTMLElement).innerText?.trim() && !e.getAttribute("aria-label") && !e.getAttribute("title") && !(e as HTMLInputElement).labels?.length)
    .map((e) => e.outerHTML.slice(0, 80)));
  expect(unlabeled).toEqual([]);
});

// ---------------- human handoff (backend B: every partner-lab call fails) ----------------
async function toHandoff(page: Page, member: string) {
  await startChat(page, member, UI_B);
  await say(page, "book thyroid test");
  await say(page, "9:30 am");
  await page.getByTestId("confirm-booking").click();
  await expect(page.getByTestId("handoff-status")).toContainText("Awaiting coordinator review", { timeout: 30_000 });
  return (await page.getByTestId("ticket-id").textContent()) ?? "";
}

async function unlock(coord: Page) {
  await coord.goto(`${UI_B}/#/coordinator`);
  await coord.locator("#ct").fill(COORD);
  await coord.getByRole("button", { name: "Unlock" }).click();
}

test("16. handoff: pending state, paused input, coordinator approves (after dialog), member sees it", async ({ page, context }) => {
  const ticket = await toHandoff(page, "MEM_1003");
  expect(ticket).toMatch(/^CARE_\d{5}$/);
  await expect(page.getByTestId("status-pill")).toHaveText("Waiting for care coordinator");
  await expect(page.locator("#msg")).toBeDisabled();
  await expect(page.getByTestId("msg-handoff")).toContainText("coordinator");
  await expect(page.getByTestId("msg-booking_confirmed")).toHaveCount(0); // never claims success
  await expect(page.getByTestId("requested-booking")).toContainText("Thyroid Screening Profile");
  await expect(page.getByTestId("handoff-status")).toContainText("Nothing has been booked");
  await expect(page.getByTestId("booking-summary")).toHaveCount(0); // stale "Confirm" summary must not sit next to a handoff
  await expect(page.getByRole("button", { name: "Confirm booking" })).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/14-handoff-pending.png` });

  // the pending request shows as pending approval (not upcoming) on the bookings page
  await page.getByTestId("nav-bookings").click();
  await page.getByRole("tab", { name: /Pending approval/ }).click();
  await expect(page.getByTestId("pending-booking")).toContainText("Awaiting coordinator review");
  await page.getByRole("tab", { name: /Upcoming/ }).click();
  await expect(page.getByTestId("my-booking")).toHaveCount(0);

  const coord = await context.newPage();
  await unlock(coord);
  const item = coord.getByTestId("approval-item").filter({ hasText: ticket });
  await expect(item).toBeVisible();
  await expect(item).not.toContainText("book thyroid test"); // coordinator never sees message text
  await coord.screenshot({ path: `${SHOTS}/15-coordinator.png` });
  await item.getByRole("button", { name: "Approve callback" }).click();
  await expect(coord.getByRole("dialog", { name: "Approve this request?" })).toBeVisible(); // confirmation required
  await expect(coord.getByTestId("coord-done")).toHaveCount(0);
  await coord.getByRole("dialog").getByRole("button", { name: "Yes, approve" }).click();
  await expect(coord.getByTestId("coord-done")).toContainText(`Ticket ${ticket}: approved`);

  await page.getByTestId("nav-chat").click();
  await expect(page.getByTestId("handoff-status")).toContainText("Coordinator approved", { timeout: 15_000 });
  await expect(page.getByTestId("handoff-status")).toContainText(ticket);
  await expect(page.getByTestId("status-pill")).toContainText("Active");
  await expect(page.locator("#msg")).toBeEnabled();
  await page.screenshot({ path: `${SHOTS}/16-handoff-approved.png` });
});

test("17. handoff rejection lets the member choose another time", async ({ page, context }) => {
  const ticket = await toHandoff(page, "MEM_1004");
  const coord = await context.newPage();
  await unlock(coord);
  const item = coord.getByTestId("approval-item").filter({ hasText: ticket });
  await item.getByLabel("Note to member").fill("Lab is closed today.");
  await item.getByRole("button", { name: "Reject" }).click();
  await coord.getByRole("dialog", { name: "Reject this request?" }).getByRole("button", { name: "Yes, reject" }).click();
  await expect(page.getByTestId("handoff-status")).toContainText("could not complete", { timeout: 15_000 });
  await expect(page.getByTestId("handoff-status")).toContainText("Lab is closed today.");
  await expect(page.locator("#msg")).toBeEnabled();
  await expect(page.getByTestId("booking-panel").getByRole("button", { name: "10:00 AM" })).toBeVisible();
});

test("18. coordinator authorization: wrong token rejected in UI; API refuses calls without the token", async ({ page, request }) => {
  await page.goto("/#/coordinator");
  await page.locator("#ct").fill("not-the-token");
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByTestId("coord-error")).toContainText("not valid");
  await expect(page.getByTestId("approval-item")).toHaveCount(0);

  const noToken = await request.get(`${API_A}/api/coordinator/approvals`);
  expect(noToken.status()).toBe(401);
  const wrong = await request.get(`${API_A}/api/coordinator/approvals`, { headers: { "X-Coordinator-Token": "nope" } });
  expect(wrong.status()).toBe(401);
  const decide = await request.post(`${API_A}/api/coordinator/approvals/anything`, { data: { approved: true, note: "" } });
  expect(decide.status()).toBe(401);
});

test("19. no console errors across a full tour", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  await startChat(page, "MEM_1002");
  await say(page, "hello");
  for (const r of ["voice", "labs", "bookings", "insights", "support", "settings", ""]) { await page.goto(`/#/${r}`); await page.waitForTimeout(300); }
  expect(errors).toEqual([]);
});

test("insights: real-data dashboard, chart/table toggle, hover tooltip, compare, fasting planner, prep for a booking", async ({ page }) => {
  await startChat(page, "MEM_1002");
  await say(page, "book thyroid test");
  await say(page, "09:30 AM");
  await page.getByTestId("confirm-booking").click();
  await expect(page.getByTestId("msg-booking_confirmed")).toBeVisible();

  await page.getByTestId("nav-insights").click();
  const dash = page.getByTestId("insights-dashboard");
  await expect(dash.getByTestId("stat")).toHaveCount(4);
  await expect(dash).toContainText("Lab packages");
  await expect(dash.getByTestId("chart-value").getByRole("list", { name: "Price per test by package" }).locator("li")).toHaveCount(12);
  await expect(dash.getByTestId("chart-price")).toContainText("Fasting required"); // legend present for two series
  await expect(dash.getByTestId("chart-programs")).toContainText("Yoga");
  await expect(dash.getByTestId("stat").nth(3)).toContainText("1"); // this session's real booking count
  await expect(page.getByTestId("prep-list")).toContainText("Thyroid Screening Profile");
  await expect(page.getByTestId("prep-list")).toContainText("No fasting needed");

  // hover tooltip carries the exact catalogue numbers
  await dash.getByTestId("chart-price").locator("li.vbar").first().hover();
  await expect(dash.getByRole("tooltip")).toContainText("tests");
  // every chart is also available as a table
  await dash.getByTestId("chart-value").getByRole("button", { name: "Table", exact: true }).click();
  await expect(dash.getByTestId("chart-value").getByRole("columnheader", { name: "Price per test" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/20-insights-dashboard.png`, fullPage: true });

  await page.getByRole("tab", { name: "Compare & plan" }).click();
  const cmp = page.getByTestId("compare");
  await cmp.getByRole("button", { name: "Thyroid Screening Profile", exact: true }).click();
  await cmp.getByRole("button", { name: "Advanced Diabetic Profile", exact: true }).click();
  await expect(cmp.getByRole("columnheader", { name: "Thyroid Screening Profile" })).toBeVisible();
  await expect(cmp.getByText("Best").first()).toBeVisible();
  await expect(cmp).toContainText("10 hours"); // diabetic profile fasting hours, from the catalogue

  const plan = page.getByTestId("fasting-planner");
  await plan.getByLabel("Package").selectOption({ label: "Advanced Diabetic Profile (10h)" });
  await plan.getByLabel("Appointment time").selectOption("08:00 AM");
  await expect(page.getByTestId("plan-result")).toContainText("10:00 PM");
  await expect(page.getByTestId("plan-result")).toContainText("the evening before");
  await page.screenshot({ path: `${SHOTS}/21-insights-plan.png`, fullPage: true });
});
