import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { UI_B } from "./ports";

// Incident-drill screenshots (docs/incident_drill/). Run after `python -m evaluations.incident_drill`, which writes
// docs/incident_drill/report.html (eval diff + trace waterfalls). The UI shot uses the REAL backend on :8001 whose
// partner-lab API fails on every call (see playwright.config.ts), i.e. the member's view of incident A.
const OUT = resolve("..", "docs", "incident_drill");
const REPORT = resolve(OUT, "report.html");


test.skip(!existsSync(REPORT), "run `python -m evaluations.incident_drill` first");

test("drill 1: eval diff + trace waterfall, incident A (lab API down)", async ({ page }) => {
  await page.setViewportSize({ width: 1180, height: 900 });
  await page.goto(pathToFileURL(REPORT).href + "#a");
  await expect(page.locator("h2#a")).toBeVisible();
  await page.locator("h2#a").scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(OUT, "01-incident-A-eval-diff-and-trace.png"), fullPage: true,
                          clip: await sectionClip(page, "h2#a", "h2#b") });
});

test("drill 2: eval diff + trace waterfall, incident B (bad prompt)", async ({ page }) => {
  await page.setViewportSize({ width: 1180, height: 900 });
  await page.goto(pathToFileURL(REPORT).href);
  await page.screenshot({ path: resolve(OUT, "02-incident-B-eval-diff-and-trace.png"), fullPage: true,
                          clip: await sectionClip(page, "h2#b", "h2#c") });
});

test("drill 3: what the member sees during incident A (handoff, never a false 'booked')", async ({ page }) => {
  await page.goto(`${UI_B}/#/`);
  await expect(page.getByTestId("start-chat")).toBeEnabled();
  await page.locator("#member").selectOption("MEM_1001");
  await page.getByTestId("start-chat").click();
  for (const text of ["book thyroid test", "9:30 am"]) {
    await page.locator("#msg").fill(text);
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByTestId("typing")).toHaveCount(0);
  }
  await page.getByTestId("confirm-booking").click();
  await expect(page.getByTestId("handoff-status")).toContainText("Awaiting coordinator review", { timeout: 30_000 });
  await expect(page.getByTestId("msg-booking_confirmed")).toHaveCount(0);
  await page.screenshot({ path: resolve(OUT, "03-incident-A-member-view-handoff.png") });
});

test("drill 4: eval diff + trace waterfall, incident C (stale backend record)", async ({ page }) => {
  await page.setViewportSize({ width: 1180, height: 900 });
  await page.goto(pathToFileURL(REPORT).href + "#c");
  await expect(page.locator("h2#c")).toBeVisible();
  await page.locator("h2#c").scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(OUT, "04-incident-C-stale-record.png"), fullPage: true,
                          clip: await sectionClip(page, "h2#c", null) });
});

/** Page rectangle from the top of `from` to the top of `to` (or the end of the page). */
async function sectionClip(page: import("@playwright/test").Page, from: string, to: string | null) {
  return page.evaluate(([f, t]) => {
    const a = document.querySelector(f as string)!.getBoundingClientRect();
    const end = t ? document.querySelector(t as string)!.getBoundingClientRect().top + window.scrollY : document.documentElement.scrollHeight;
    const y = a.top + window.scrollY;
    return { x: 0, y, width: 1180, height: Math.min(end - y, 2400) };
  }, [from, to]);
}
