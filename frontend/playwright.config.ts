import { defineConfig } from "@playwright/test";

// Two stacks so both normal booking and the human-handoff path run against the REAL backend:
//   A: backend :8000 (lab outages off)  + UI :5173
//   B: backend :8001 (every lab call fails -> coordinator handoff) + UI :5174
// Uses the system's Microsoft Edge (no browser download). COORD is a throw-away test value.
const COORD = "e2e-coordinator-token";
// webServer commands run with cwd = repo root, so the venv path is relative to that.
const py = process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";
const backend = (port: number, failure: string, origin: string) => ({
  command: `${py} -m uvicorn app.api:app --host 127.0.0.1 --port ${port}`,
  cwd: "..",
  url: `http://127.0.0.1:${port}/api/health`,
  reuseExistingServer: !process.env.CI,
  timeout: 90_000,
  env: { LAB_FAILURE_RATE: failure, COORDINATOR_TOKEN: COORD, FRONTEND_ORIGINS: origin,
         GEMINI_API_KEY: "", OPENAI_API_KEY: "", MESSAGES_PER_MINUTE: "300", SESSIONS_PER_MINUTE: "300" },
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
  use: { channel: "msedge", headless: true, baseURL: "http://127.0.0.1:5173", trace: "retain-on-failure" },
  webServer: [
    backend(8000, "0", "http://127.0.0.1:5173"),
    backend(8001, "1", "http://127.0.0.1:5174"),
    ui(5173, 8000),
    ui(5174, 8001),
  ],
});
