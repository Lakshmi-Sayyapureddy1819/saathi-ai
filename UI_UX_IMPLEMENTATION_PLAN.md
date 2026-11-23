# Saathi Care — UI/UX Implementation Plan

## What the backend actually offers (drives every honest-state decision)
| Capability | Backend reality | UI treatment |
|---|---|---|
| Chat | `POST /api/sessions/{id}/messages` returns the full `SessionView` (no streaming) | Typing indicator while the request is in flight; no fake token streaming |
| Conversation history | One in-memory session per browser tab; no list endpoint | Sidebar shows the current conversation only + honest note |
| Citations | No citation field on messages | No citation card is invented |
| Bookings | `session.bookings` (confirmed, cancellable), `handoff` (pending/approved/rejected) | Tabs Upcoming / Pending approval / Completed / Cancelled; the last two show honest "not tracked" empty states |
| Booking flow | Conversational (`booking.stage`, options, dates, slots) | Stepper + pickers that send the same messages a typed chat would |
| Voice | Browser Web Speech API (real STT/TTS) -> same `/messages` endpoint | Orb states are driven by real recogniser/synth/network state; amplitude only from a real mic `AnalyserNode`, otherwise no level display |
| Auth | Demo member picker; coordinator uses `X-Coordinator-Token` | Preserved; coordinator console never linked from user nav |

## Architecture
- Hash routes (existing pattern, no router dependency): `#/` overview, `#/chat`, `#/voice`, `#/labs`, `#/bookings`, `#/insights`, `#/support`, `#/settings`, `#/coordinator`.
- `useSession` stays the single owner of session state and API calls (unchanged contracts). Pages receive it via props/context.
- Design system: `src/design/*.css` (tokens, base, components) + `src/components/ui/*` (typed primitives).
- New deps: `lucide-react` (requested), `@fontsource-variable/manrope` (self-hosted font, no external request). `framer-motion` already present.

## Phases
1. Inspect + plan (this file)
2. Design tokens, UI primitives, app shell (sidebar, topbar, mobile bottom nav)
3. Overview + navigation + member gate
4. Chat workspace (markdown, special message cards, retry/copy, prompts)
5. Voice assistant (orb, 9 states, transcript, readback, low-confidence guard)
6. Lab discovery + 6-step booking
7. Bookings page, support page, coordinator console
8. Responsive + motion polish, reduced motion
9. Tests (tsc, vitest, pytest, Playwright), screenshots, README/TESTDEMO

## Safety invariants (must not regress)
- Emergency cards always `role="alert"`, always show helplines from backend payload.
- UI never shows "confirmed" until a `booking_confirmed` message with a `confirmation` object arrives.
- Voice: transcripts under a confidence threshold during a booking are shown for confirmation before being sent; booking confirmation always needs an explicit user action/utterance.
- Coordinator actions only on `#/coordinator` behind the token.

## Status (implemented and verified)
- tsc clean; 22 vitest tests; `npm run build` OK; 391 backend tests; 32 Playwright tests (Edge, real backends A/B) all passing.
- Screenshots: `frontend/e2e/screenshots/` (test run) and `frontend/e2e/screenshots/redesign/` (`node scripts/qa-screens.mjs`, 4 viewports).
- Still simulated/not available: sign-in (demo members), conversation history, citations, streaming, completed/cancelled booking history; automated voice tests stub the browser speech engines only.
