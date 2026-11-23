import { expect, test } from "@playwright/test";

// UI rendering of verified citations. The harness backend has no AI key (coach replies are [MOCK]), so there is no real
// cited answer to show. This test lets the REAL backend handle the turn, then adds the `citations` / `grounding` fields
// the server sends for a grounded answer (shape: app/api_schemas.py) to that real response. It tests the rendering only;
// server-side verification is covered by tests/test_citations.py.
test("19. a grounded answer shows verified source chips, hides raw [IDs], and explains how it was answered", async ({ page }) => {
  await page.route("**/api/sessions/*/messages", async (route) => {
    if (route.request().method() !== "POST") return route.fallback(); // let the CORS preflight through untouched
    const res = await route.fetch();
    const body = await res.json();
    const last = body.messages[body.messages.length - 1];
    last.text = "Kapalbhati is a forceful breathing practice [PROG_P_002]. Start with a few gentle rounds [PROG_P_002].";
    last.kind = "answer";
    last.citations = [{ source_id: "PROG_P_002", title: "Kapalbhati Pranayama", kind: "document", cited: true }];
    last.grounding = { mode: "mode_a_rag", retriever: "lexical", search_queries: ["kapalbhati breathing"], tools_called: [],
                       agent_steps: 2, decided_by: "llm" };
    await route.fulfill({ response: res, json: body });
  });
  await page.goto("/#/");
  await expect(page.getByTestId("start-chat")).toBeEnabled();
  await page.locator("#member").selectOption("MEM_1001");
  await page.getByTestId("start-chat").click();
  await expect(page.getByTestId("chat-empty")).toBeVisible();
  await page.locator("#msg").fill("Tell me about Kapalbhati");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const answer = page.getByTestId("msg-answer").last();
  await expect(answer).toContainText("forceful breathing practice");
  await expect(answer).not.toContainText("PROG_P_002");                       // raw marker hidden
  await expect(page.getByTestId("source-chip").last()).toContainText("Kapalbhati Pranayama");
  await page.getByTestId("how-answered").last().locator("summary").click();
  await expect(page.getByTestId("how-answered").last()).toContainText("kapalbhati breathing");
  await page.screenshot({ path: "e2e/screenshots/19-citations.png" });
});

test("20. both grounding modes are switchable in the chat for the demo (A: library search, B: my records)", async ({ page }) => {
  await page.goto("/#/");
  await expect(page.getByTestId("start-chat")).toBeEnabled();
  await page.locator("#member").selectOption("MEM_1001");
  await page.getByTestId("start-chat").click();
  await expect(page.getByTestId("chat-empty")).toBeVisible();

  // Mode A is the default: library prompts + explanation card.
  await expect(page.getByTestId("mode-mode_a_rag")).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("mode-card")).toContainText("Library search");
  await expect(page.getByTestId("demo-prompts-label")).toContainText("Library search");
  await expect(page.getByTestId("mode-prompt").first()).toContainText("Kapalbhati");
  await page.screenshot({ path: "e2e/screenshots/20-mode-a-library.png" });

  // Switch to Mode B: the server records it, a notice lands in the transcript, prompts and card change.
  await page.getByTestId("mode-mode_b_facts").click();
  await expect(page.getByTestId("mode-mode_b_facts")).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("mode-card")).toContainText("My records");
  await expect(page.getByTestId("msg-system").last()).toContainText("Mode B");
  await expect(page.getByTestId("mode-prompt").first()).toContainText("enrolled");

  // Ask a member-data question; the real backend handles the turn, we add the grounding fields the server sends in
  // Mode B (rendering test only, see the note on test 19).
  await page.route("**/api/sessions/*/messages", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const res = await route.fetch();
    const body = await res.json();
    const last = body.messages[body.messages.length - 1];
    last.kind = "answer";
    last.text = "You have booked the Thyroid Screening Profile [bookings].";
    last.citations = [{ source_id: "bookings", title: "Your bookings", kind: "backend_fact", cited: true }];
    last.grounding = { mode: "mode_b_facts", retriever: "", search_queries: [], tools_called: ["get_member_profile", "get_bookings"],
                       agent_steps: 0, decided_by: "llm" };
    await route.fulfill({ response: res, json: body });
  });
  await page.getByTestId("mode-prompt").nth(1).click();
  await expect(page.getByTestId("source-chip").last()).toContainText("Your bookings");
  await page.getByTestId("how-answered").last().locator("summary").click();
  await expect(page.getByTestId("how-answered").last()).toContainText("Looked up: member profile, bookings");
  await expect(page.getByTestId("how-answered").last()).toContainText("no retrieval");
  await page.screenshot({ path: "e2e/screenshots/21-mode-b-records.png" });

  // Switch back to A.
  await page.getByTestId("mode-mode_a_rag").click();
  await expect(page.getByTestId("mode-card")).toContainText("Library search");
});
