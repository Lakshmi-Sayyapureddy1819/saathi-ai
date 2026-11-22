import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server is pinned to loopback + a fixed port so the backend's CORS allow-list (FRONTEND_ORIGINS) matches.
// VITE_PORT only exists so the e2e harness can run a second UI against a second backend.
const port = Number(process.env.VITE_PORT ?? 5173);

export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port, strictPort: true },
  preview: { host: "127.0.0.1", port, strictPort: true },
  test: { include: ["tests/**/*.test.ts"] },
});
