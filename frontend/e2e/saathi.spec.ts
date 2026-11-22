import { expect, test, type Page } from "@playwright/test";

// Real browser + real backend. Nothing here stubs an AI/booking response; the only mocked thing is the
// deliberate network failure in the "API error" test.
const SHOTS = "e2e/screenshots";
const COORD = "e2e-coordinator-token";
const UI_B = "http://127.0.0.1:5174"; // UI wired to the backend whose lab API always fails

async function startChat(page: Page, memberId = "MEM_1001", base = "") {
  await page.goto(`${base}/`);
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

test("1. dashboard loads with real catalogue data from the backend", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Care that listens");
  await expect(page.getByTestId("status-pill")).toHaveText("No active session");
  await expect(page.getByTestId("session-status")).toContainText("no active session");
  await expect(page.getByTestId("pkg-list").locator("li")).toHaveCount(12);
  await expect(page.getByTestId("program-cats")).toContainText("Yoga");
  await expect(page.getByTestId("mock-banner")).toBeVisible(); // harness runs without AI keys: UI must say so
  await expect(page.getByRole("contentinfo")).toContainText("not a substitute for a medical professional");
  await page.screenshot({ path: `${SHOTS}/01-dashboard.png`, fullPage: true });
});

test("2. start a session; 3. wellness question; 4. Hinglish question", async ({ page }) => {
  await startChat(page);
  await expect(page.getByTestId("status-pill")).toContainText("Active · Aarav Sharma");
  await page.screenshot({ path: `${SHOTS}/02-chat-empty.png` });
  await say(page, "What yoga helps with exhaustion?");
  await expect(lastReply(page)).not.toBeEmpty();
  await expect(page.getByTestId("msg-answer").last()).toContainText("[MOCK"); // no key -> flagged mock, not faked
  await expect(page.getByText("Demo mode: no AI model key").first()).toBeVisible();
  await say(page, "Mujhe bahut thakan rehti hai, kya yoga karun?");
  await expect(page.getByTestId("msg-answer")).toHaveCount(2);
  await expect(page.getByTestId("booking-panel")).toContainText("No booking in progress"); // stayed in coaching
  await page.screenshot({ path: `${SHOTS}/03-wellness-hinglish.png` });
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
  await expect(page.getByTestId("booking-panel")).toContainText("No booking in progress");
  await page.screenshot({ path: `${SHOTS}/04-emergency.png` });
  await say(page, "Mere seene mein dard hai");
  await expect(page.getByTestId("msg-emergency")).toHaveCount(2);
});

test("5b. no-diagnosis rule", async ({ page }) => {
  await startChat(page);
  await say(page, "do I have diabetes?");
  await expect(page.getByTestId("msg-safety_notice")).toContainText("can't provide a medical diagnosis");
});

test("6-10. generic blood test -> package -> short follow-ups -> confirm -> booking id", async ({ page }) => {
  await startChat(page, "MEM_1001");
  await say(page, "Book a blood test");
  await expect(lastReply(page)).toContainText("Which test would you like");
  const panel = page.getByTestId("booking-panel");
  await expect(panel).toContainText("Which test would you like?");
  await expect(panel.getByTestId("pkg-list").locator("li")).toHaveCount(12);
  await page.screenshot({ path: `${SHOTS}/05-choose-package.png` });

  await panel.getByTestId("pkg-search").fill("thyroid");
  await expect(panel.getByTestId("pkg-list").locator("li")).toHaveCount(1);
  await panel.getByRole("button", { name: "Select Thyroid Screening Profile" }).click();
  await expect(panel.getByRole("button", { name: "10:30 AM" })).toBeVisible();
  await expect(panel).toContainText("Thyroid Screening Profile");
  await page.screenshot({ path: `${SHOTS}/06-choose-slot.png` });

  await say(page, "10:30 AM"); // short follow-up typed by hand: context must survive
  await expect(page.getByTestId("booking-summary")).toContainText("Thyroid Screening Profile");
  await expect(page.getByTestId("booking-summary")).toContainText("10:30 AM");
  await expect(lastReply(page)).toContainText("Just to confirm");
  await page.screenshot({ path: `${SHOTS}/07-confirm-summary.png` });

  await say(page, "yes confirm");
  const confirmed = page.getByTestId("msg-booking_confirmed");
  await expect(confirmed).toContainText("Booking confirmed");
  const id = (await page.getByTestId("booking-id").textContent()) ?? "";
  expect(id).toMatch(/^BOK_MEM_1001_\d{4}$/);
  await expect(confirmed).toContainText(id); // the id in the card is the one inside the backend's own sentence
  await expect(page.getByTestId("panel-confirmation")).toContainText(id);
  await page.screenshot({ path: `${SHOTS}/08-booked.png` });

  // The booked slot really is consumed in the backend: a second member no longer sees 10:30 AM for that day.
  const page2 = await page.context().newPage();
  await startChat(page2, "MEM_1002");
  await say(page2, "book thyroid test");
  await expect(page2.getByTestId("booking-panel").getByRole("button", { name: "09:30 AM" })).toBeVisible();
  await expect(page2.getByTestId("booking-panel").getByRole("button", { name: "10:30 AM" })).toHaveCount(0);
});

test("my bookings: listed after booking, two-step cancel frees the slot", async ({ page }) => {
  await startChat(page, "MEM_1005");
  await say(page, "book thyroid test");
  await say(page, "11:00 AM");
  await say(page, "yes");
  const mine = page.getByTestId("my-bookings");
  await expect(mine.getByTestId("my-booking")).toHaveCount(1);
  await expect(mine).toContainText("Thyroid Screening Profile");
  await expect(mine).toContainText("11:00 AM");
  await page.screenshot({ path: `${SHOTS}/17-my-bookings.png` });

  await mine.getByRole("button", { name: /^Cancel booking BOK_/ }).click();
  await expect(mine).toContainText("Keep it"); // asks first; nothing cancelled yet
  await mine.getByRole("button", { name: "Keep it" }).click();
  await expect(mine.getByTestId("my-booking")).toHaveCount(1);

  await mine.getByRole("button", { name: /^Cancel booking BOK_/ }).click();
  await mine.getByRole("button", { name: "Yes, cancel it" }).click();
  await expect(lastReply(page)).toContainText("cancelled your booking");
  await expect(page.getByTestId("my-bookings")).toHaveCount(0);

  // the slot is genuinely free again: a new session for another member is offered 11:00 AM
  const page2 = await page.context().newPage();
  await startChat(page2, "MEM_1002");
  await say(page2, "book thyroid test");
  await expect(page2.getByTestId("booking-panel").getByRole("button", { name: "11:00 AM" })).toBeVisible();
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

test("buttons: change time, change day, cancel", async ({ page }) => {
  await startChat(page, "MEM_1003");
  await page.getByTestId("booking-panel").getByRole("button", { name: "Book Thyroid Screening Profile" }).click();
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
  await expect(panel).toContainText("No booking in progress");
});

test("11. ambiguous package selection asks again and narrows the list", async ({ page }) => {
  await startChat(page, "MEM_1004");
  await say(page, "book vitality test");
  await say(page, "senior");
  await expect(lastReply(page)).toContainText("Which package");
  const rows = page.getByTestId("booking-panel").getByTestId("pkg-list").locator("li");
  await expect(rows).toHaveCount(2);
  await say(page, "female");
  await expect(page.getByTestId("booking-panel")).toContainText("Senior Citizen Vitality (Female)");
  await page.screenshot({ path: `${SHOTS}/09-ambiguous-resolved.png` });
});

test("12. invalid input: empty, too long, gibberish", async ({ page }) => {
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
  await send.click();
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

test("14. end session / new session; sessions are isolated across browsers", async ({ page, browser }) => {
  await startChat(page, "MEM_1001");
  await say(page, "book thyroid test");
  const other = await browser.newContext();
  const page2 = await other.newPage();
  await startChat(page2, "MEM_1002");
  await expect(page2.getByTestId("msg-user")).toHaveCount(0); // B sees nothing of A
  await expect(page2.getByTestId("booking-panel")).toContainText("No booking in progress");
  await expect(page.getByTestId("booking-panel")).toContainText("Thyroid Screening Profile");

  await page.getByTestId("new-session").click(); // clears A
  await expect(page.getByTestId("status-pill")).toHaveText("No active session");
  await startChat(page, "MEM_1001");
  await expect(page.getByTestId("msg-user")).toHaveCount(0);
  await expect(page.getByTestId("booking-panel")).toContainText("No booking in progress");
  await other.close();
});

test("session survives a page reload; a dead session is handled", async ({ page }) => {
  await startChat(page);
  await say(page, "book thyroid test");
  await page.reload();
  await expect(page.getByTestId("status-pill")).toContainText("Active");
  await expect(page.getByTestId("msg-user")).toHaveText("book thyroid test");
  await expect(page.getByTestId("booking-panel")).toContainText("Thyroid Screening Profile");

  await page.evaluate(() => sessionStorage.setItem("saathi.session", JSON.stringify({ id: "gone", token: "x" })));
  await page.reload();
  await expect(page.getByTestId("notice")).toContainText("expired");
  await expect(page.getByTestId("start-chat")).toBeVisible();
});

test("15. mobile layout", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  await page.goto("/");
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(await overflow()).toBeLessThanOrEqual(0);
  await page.screenshot({ path: `${SHOTS}/11-mobile-dashboard.png`, fullPage: true });
  await page.getByTestId("start-chat").click();
  await expect(page.getByRole("tab", { name: "Chat" })).toBeVisible();
  await page.locator("#msg").fill("Book a blood test");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("msg-answer")).toBeVisible();
  expect(await overflow()).toBeLessThanOrEqual(0);
  await page.screenshot({ path: `${SHOTS}/12-mobile-chat.png` });
  await page.getByTestId("tab-booking").click();
  await expect(page.getByTestId("booking-panel")).toBeVisible();
  expect(await overflow()).toBeLessThanOrEqual(0);
  await page.screenshot({ path: `${SHOTS}/13-mobile-booking.png` });
  await ctx.close();
});

// ---------------- human handoff (backend B: every partner-lab call fails) ----------------
async function toHandoff(page: Page, member: string) {
  await startChat(page, member, UI_B);
  await say(page, "book thyroid test");
  await say(page, "9:30 am");
  await page.locator("#msg").fill("yes confirm");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("handoff-status")).toContainText("Waiting for a care coordinator", { timeout: 30_000 });
  return (await page.getByTestId("ticket-id").textContent()) ?? "";
}

test("16. handoff: pending state, paused input, coordinator approves, member sees it", async ({ page, context }) => {
  const ticket = await toHandoff(page, "MEM_1003");
  expect(ticket).toMatch(/^CARE_\d{5}$/);
  await expect(page.getByTestId("status-pill")).toHaveText("Waiting for care coordinator");
  await expect(page.locator("#msg")).toBeDisabled();
  await expect(page.getByTestId("msg-handoff")).toContainText("coordinator");
  await expect(page.getByTestId("msg-booking_confirmed")).toHaveCount(0); // never claims success
  // Regression: a stale "Confirm booking" summary must not sit next to a pending handoff.
  await expect(page.getByTestId("requested-booking")).toContainText("Requested (not booked)");
  await expect(page.getByTestId("booking-summary")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Confirm booking" })).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/14-handoff-pending.png` });

  const coord = await context.newPage();
  await coord.goto(`${UI_B}/#/coordinator`);
  await coord.locator("#ct").fill(COORD);
  await coord.getByRole("button", { name: "Unlock" }).click();
  const item = coord.getByTestId("approval-item").filter({ hasText: ticket });
  await expect(item).toBeVisible();
  await expect(item).not.toContainText("book thyroid test"); // coordinator never sees message text
  await coord.screenshot({ path: `${SHOTS}/15-coordinator.png` });
  await item.getByRole("button", { name: "Approve callback" }).click();
  await expect(coord.getByTestId("coord-done")).toContainText(`Ticket ${ticket}: approved`);

  await expect(page.getByTestId("handoff-status")).toContainText(`Coordinator approved ticket ${ticket}`, { timeout: 15_000 });
  await expect(page.getByTestId("status-pill")).toContainText("Active");
  await expect(page.locator("#msg")).toBeEnabled();
  await page.screenshot({ path: `${SHOTS}/16-handoff-approved.png` });
});

test("17. handoff rejection lets the member choose another time", async ({ page, context }) => {
  const ticket = await toHandoff(page, "MEM_1004");
  const coord = await context.newPage();
  await coord.goto(`${UI_B}/#/coordinator`);
  await coord.locator("#ct").fill(COORD);
  await coord.getByRole("button", { name: "Unlock" }).click();
  const item = coord.getByTestId("approval-item").filter({ hasText: ticket });
  await item.getByLabel("Note to member").fill("Lab is closed today.");
  await item.getByRole("button", { name: "Reject" }).click();
  await expect(page.getByTestId("handoff-status")).toContainText("couldn't complete", { timeout: 15_000 });
  await expect(page.getByTestId("handoff-status")).toContainText("Lab is closed today.");
  await expect(page.locator("#msg")).toBeEnabled();
  await expect(page.getByTestId("booking-panel").getByRole("button", { name: "10:00 AM" })).toBeVisible();
});

test("18. coordinator console rejects a wrong token", async ({ page }) => {
  await page.goto("/#/coordinator");
  await page.locator("#ct").fill("not-the-token");
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByTestId("coord-error")).toContainText("not valid");
  await expect(page.getByTestId("approval-item")).toHaveCount(0);
});
