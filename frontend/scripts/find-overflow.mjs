import { chromium } from "@playwright/test";
const [base, route, w] = [process.argv[2], process.argv[3], Number(process.argv[4] ?? 390)];
const b = await chromium.launch({ channel: "msedge" });
const p = await (await b.newContext({ viewport: { width: w, height: 844 } })).newPage();
await p.goto(base + "/#/"); await p.locator("#member").waitFor(); await p.waitForTimeout(500); await p.getByTestId("start-chat").click(); await p.waitForTimeout(500);
await p.goto(base + "/#/" + route); await p.waitForTimeout(700);
console.log(await p.evaluate((w) => [...document.querySelectorAll("*")].filter((e) => e.getBoundingClientRect().right > w + 0.5 && getComputedStyle(e).position !== "fixed").slice(0, 8).map((e) => `${e.tagName}.${e.className} right=${Math.round(e.getBoundingClientRect().right)}`).join("\n"), w));
await b.close();
