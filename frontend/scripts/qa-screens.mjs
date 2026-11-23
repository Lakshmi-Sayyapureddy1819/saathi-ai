// Visual QA: drives the REAL UI against a REAL backend and saves screenshots. Usage: node scripts/qa-screens.mjs [baseUrl] [outDir]
import { chromium } from "@playwright/test";
const base = process.argv[2] ?? "http://127.0.0.1:5273";
const out = process.argv[3] ?? "e2e/screenshots/redesign";
const VIEWS = { "1440": [1440, 900], "1280": [1280, 800], "768": [768, 1024], "390": [390, 844] };
const only = process.env.VIEWS?.split(",") ?? Object.keys(VIEWS);
const errors = [];
const SLOT = { 1440: "10:30 AM", 1280: "11:00 AM", 768: "09:30 AM", 390: "09:00 AM" }; // each viewport books a different slot (the backend really consumes slots)
const browser = await chromium.launch({ channel: "msedge", headless: true });
for (const v of only) {
  const [w, h] = VIEWS[v];
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") errors.push(`[${v}] console: ${m.text()}`); });
  page.on("pageerror", (e) => errors.push(`[${v}] pageerror: ${e.message}`));
  page.on("requestfailed", (r) => errors.push(`[${v}] requestfailed: ${r.url()} ${r.failure()?.errorText}`));
  const shot = (n) => page.screenshot({ path: `${out}/${v}-${n}.png`, fullPage: false });
  const say = async (t) => {
    await page.locator("#msg").fill(t); await page.getByRole("button", { name: "Send", exact: true }).click();
    await page.getByTestId("typing").waitFor({ state: "detached", timeout: 20000 }).catch(() => {}); await page.waitForTimeout(400);
  };
  await page.goto(base + "/#/"); await page.waitForTimeout(800); await shot("01-overview-nosession");
  await page.getByTestId("start-chat").first().click(); await page.waitForTimeout(800);
  await page.goto(base + "/#/"); await page.waitForTimeout(600); await shot("02-overview");
  await page.goto(base + "/#/chat"); await page.waitForTimeout(600); await shot("03-chat-empty");
  await say("What yoga helps with exhaustion?"); await shot("04-chat-answer");
  await say("book thyroid test"); await shot("05-chat-booking-slot");
  await say(SLOT[v]); await shot("06-chat-confirm");
  await page.getByTestId("confirm-booking").click({ timeout: 8000 }).catch((e) => errors.push(`[${v}] confirm not available: ${e.message.split(String.fromCharCode(10))[0]}`)); await page.waitForTimeout(1500); await shot("07-chat-booked");
  await say("I have severe chest pain"); await shot("08-chat-emergency");
  for (const r of ["voice", "labs", "bookings", "insights", "support", "settings"]) {
    await page.goto(base + "/#/" + r); await page.waitForTimeout(900); await shot(`10-${r}`);
  }
  await page.goto(base + "/#/coordinator"); await page.waitForTimeout(600); await shot("11-coordinator");
  await ctx.close();
}
await browser.close();
console.log(errors.length ? errors.join("\n") : "NO CONSOLE ERRORS");
