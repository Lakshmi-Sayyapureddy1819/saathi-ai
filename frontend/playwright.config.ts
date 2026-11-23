import { defineConfig } from "@playwright/test";
import { API_A, COORD, PORTS, UI_A, UI_B } from "./e2e/ports";

// Two stacks so both normal booking and the human-handoff path run against the REAL backend:
//   A: backend (lab outages off)                 + UI A
//   B: backend (every lab call fails -> handoff) + UI B
// Uses the system's Microsoft Edge (no browser download). Fake mic device + auto-accepted permission prompt are
// browser launch flags; they make getUserMedia work headlessly, they do not fake any speech.
// webServer commands run with cwd = repo root for the backend, so the venv path is relative to that.
const py = process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";
const backend = (port: number, failure: string, origin: string) => ({
  command: `${py} -m uvicorn app.api:app --host 127.0.0.1 --port ${port}`,
  cwd: "..",
  url: `http://127.0.0.1:${port}/api/health`,
  reuseExistingServer: !process.env.CI,
  timeout: 90_000,
  env: { LAB_FAILURE_RATE: failure, COORDINATOR_TOKEN: COORD, FRONTEND_ORIGINS: origin,
         GEMINI_API_KEY: "", OPENAI_API_KEY: "", ALLOW_MOCK_LLM: "1", DATABASE_URL: "sqlite:///:memory:",
         // the e2e suite sends emergency messages: it must never reach the real care-team channels or a real partner
         TELEGRAM_BOT_TOKEN: "", TELEGRAM_CHAT_ID: "", SMTP_HOST: "", ALERT_EMAIL_TO: "", TWILIO_ACCOUNT_SID: "",
         LAB_BACKEND: "simulator", LAB_API_URL: "", LAB_API_KEY: "",
         REDIS_URL: "", UPSTASH_REDIS_REST_URL: "", UPSTASH_REDIS_REST_TOKEN: "", MESSAGES_PER_MINUTE: "300", SESSIONS_PER_MINUTE: "300" },
});
const ui = (port: number, api: number) => ({
  command: "npx vite",
  url: `http://127.0.0.1:${port}`,
  reuseExistingServer: !process.env.CI,
  timeout: 60_000,
  env: { VITE_PORT: String(port), VITE_API_URL: `http://127.0.0.1:${api}` },
});

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [["list"]],
  use: {
    channel: "msedge", headless: true, baseURL: UI_A, trace: "retain-on-failure",
    launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] },
  },
  webServer: [
    backend(PORTS.apiA, "0", UI_A),
    backend(PORTS.apiB, "1", UI_B),
    ui(PORTS.uiA, PORTS.apiA),
    ui(PORTS.uiB, PORTS.apiB),
  ],
});
void API_A;
