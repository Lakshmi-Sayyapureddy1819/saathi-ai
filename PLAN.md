# Saathi Care AI - Architectural Plan

> **Status note.** The brief asks for `PLAN.md` as the first commit. It was not: the repository already had history when
> this file was rewritten, so that requirement is not met and is not faked. This version describes what is actually
> built (ADK 2.x Workflow with a human-approval pause), not the first sketch (a plain DAG with a regex-only router).

## 1. Problem
A yoga and wellness company serves hundreds of thousands of members over chat, WhatsApp-style messaging and phone calls
in English, Hindi and Hinglish. One assistant must (a) answer program questions grounded only in the company's data,
(b) recommend and book lab tests, (c) never diagnose, (d) escalate red-flag symptoms immediately, and (e) let each step
run on a different model, because at millions of conversations a month cost matters as much as quality.

The design tension: LLMs are good at fluent, empathetic wording and bad at guarantees. Safety and money-moving actions
need guarantees, so they are code; the LLM is confined to wording.

## 2. Users
- **Member** - wants a quick booking, an answer about a practice, or help with a symptom. Needs a safe, short, correct reply.
- **Care coordinator (human in the loop)** - receives a ticket when a booking cannot be completed or when an emergency is flagged, and approves or rejects the callback.
- **AI engineer / on-call** - needs every turn traceable (`trace_id` on every node, tool and model call) and every behaviour covered by an eval.

## 3. Workflow graph (Google ADK 2.x `Workflow`, `app/workflow/adk_graph.py`)

Chat and voice enter through the **same** workflow; only the channel adapter at the edge differs
(`app/api.py` for chat/UI, `app/channels/voice_agent.py` for voice).

```mermaid
flowchart TD
    CH["Channel adapter<br/>chat (FastAPI / React UI) or voice (STT in, TTS out)"] --> SG

    SG["safety_gate<br/>CODE: regex red flags (EN / Hindi / Hinglish)<br/>+ no-diagnosis rule"]
    SG -- "RED_CRISIS" --> EM["emergency<br/>CODE: helplines + SMS alert (mock)<br/>clears any booking draft. No LLM."]
    SG -- "YELLOW_WARNING (asks for a diagnosis)" --> Y(["canned no-diagnosis reply<br/>CODE, turn ends"])
    SG -- "GREEN_NORMAL" --> IR

    IR["intent_router<br/>CODE first: keyword + session-context rules<br/>LLM second: only if no rule decides<br/>(output validated against a closed set)"]
    IR -- "node_program_coach" --> PC
    IR -- "node_lab_booking" --> LB

    PC["program_coach<br/>LLM: wording only, from retrieved facts<br/>Mode A: retrieval + citations<br/>Mode B: member / catalogue facts from tools<br/>semantic cache for Mode A only"]
    LB["lab_booking<br/>CODE state machine: package -> slot -> read-back -> explicit yes -> book_test<br/>tools: search_packages, check_slots, book_test (15% simulated failure, 3 retries)"]

    LB -- "retries exhausted" --> HR
    HR["handoff_request<br/>ADK RequestInput: workflow PAUSES<br/>until a care coordinator decides"]
    HR -- "approve / reject (ApprovalDecision)" --> HRES["handoff_resolution<br/>CODE: approved = callback booked, draft cleared<br/>rejected = keep package, pick another slot"]

    EM --> OUT([reply to member])
    Y --> OUT
    PC --> OUT
    LB -- "booked / re-ask / cancelled" --> OUT
    HRES --> OUT
```

Node names in code: `safety_gate`, `emergency`, `intent_router`, `program_coach`, `lab_booking`, `handoff_request`,
`handoff_resolution`. All business logic lives once in `app/workflow/graph.py`; each ADK node calls
`WorkflowGraph(chain=False).run_node(...)` for exactly one step and routes on `session.next_node`, so the plain-Python
runner (used by evals, voice, CLI) and the ADK runner cannot drift apart.

## 4. Which decisions are code and which are LLM, and why

| Decision | Code or LLM | Why |
|---|---|---|
| Red-flag escalation (chest pain, fainting, breathlessness, self-harm, bleeding) | **Code** (regex; variants listed explicitly, no fuzzy matching) | Recall must be 100% and the same every time. A model can be talked out of it or have a bad day. |
| "No diagnosis" refusal | **Code** (deterministic trigger + canned reply) | A violation is a clinical and legal event, so it is not left to prompt wording. The coach prompt repeats the rule as defence in depth. |
| Safety gate, second stage | **Not built.** The brief wants "deterministic code first, LLM second"; today there is no LLM stage for slang the regexes miss. | Honest gap. The production design is a cheap classifier behind the regexes that can only *raise* the triage level, never lower it (ARCHITECTURE.md risk 1). |
| Intent routing | **Code first, LLM second** | Keyword and session-context rules decide almost every turn at zero cost and zero latency. The LLM classifier runs only when no rule decides, and its label is accepted only if it is one of two known values, so prompt injection cannot invent a route. |
| Booking state machine, slot parsing, read-back, "explicit yes" | **Code** | Money-moving and irreversible. Number words become integers, so "fifteen" can never match "fifty". Only a whole-word yes with no negation books. |
| Tool calls (`search_packages`, `check_slots`, `book_test`) | **Code** | The LLM never chooses a tool or its arguments; arguments come from parsed state. Retries/backoff and the human handoff are plain Python. |
| Handoff approval | **Human** (ADK `RequestInput`) | A person decides; the workflow genuinely pauses and resumes. (Auth is a shared secret in this prototype, not real identity.) |
| Wellness answer wording | **LLM** (`program_coach`) | Fluent, empathetic, multilingual wording is what the model is for. It sees only the retrieved facts, must cite `[DOC_id]`, and says "I don't have that information" otherwise. |
| Mode B facts (member profile, schedule, catalogue, bookings) | **Code** fetches, **LLM** words them | Facts come from the backend, not from model memory. |

## 5. State and data model
Typed Pydantic V2 models (`app/workflow/state.py`), serialisable so the ADK session holds them between turns:
- `UserSessionState`: `session_id`, `channel` (chat / voice / eval), `member`, `booking_draft`, `triage_status`, `active_node`, `next_node`, `trace_id`, `handoff_ticket`, `grounding_mode`, `reply_lang`, `turn_history`.
- `MemberProfile` (name, age, programs, language preference, past bookings, goals) and `BookingDraft` (package, date, slot, `verbal_confirmed`, candidate packages) are used across turns: a member's name, language and booking history change the replies.
- Synthetic data in `data/`: 15 program/FAQ documents, 12 lab packages, a small member database.

## 6. Grounding modes (per-session `grounding_mode`)
- **Mode A - agentic RAG:** retrieval over the program library, answers cite source documents. Lexical retrieval (stemming + a small Hinglish lexicon). The semantic cache sits in front of Mode A only; member-specific answers are never cached.
- **Mode B - fact-grounded prompting:** no retrieval; tools return member/catalogue/booking facts that are injected into a structured prompt; anything else gets "I don't have that information".
- Both are run through the same evals; the measured comparison and the "when I would recommend each" paragraph are in `EVALS.md`.

## 7. Model routing (`config/models.yaml`, no code change to swap)
Routing entries (cost_optimized, quality_optimized, voice, plus eval-only mixes): `cost_optimized` (`gemini-3.5-flash-lite`, fallback `gpt-4o-mini`) for the coach and the router fallback, and `quality_optimized` (`gemini-3.8-flash`, fallback `gpt-4o`) for the eval judge. The client accepts a `node` name, so a separate `voice` entry can be added in the YAML alone. **Done (2026-11-22):** the same eval on four mixes (two Google, two OpenAI) with quality, p50/p95 and cost per 1,000 conversations, a routing policy table and a separate `voice` route; see `EVALS.md` "Model mixes". Open: voice wellness turns still exceed the 1.5 s budget (needs streaming into TTS).

## 8. Voice
Speech in -> same workflow -> speech out. Time-to-first-audio budget **1.5 s** (STT ~400 ms + workflow <= 600 ms + TTS first byte ~300 ms + slack). Read-back of test, date and slot plus an explicit "yes" before `book_test`; barge-in cancels TTS without losing state. STT/TTS are **simulated** in this repo; measured results and what is not measured are in `EVALS.md` (Voice section).

## 9. Observability
One root span per turn, a child span for every node, tool and LLM call, all carrying the same `trace_id`; LLM spans record model, tokens, cost and latency. Spans go to `logs/traces.jsonl` and to Langfuse when keys are set. The incident drill that uses these traces is in `docs/INCIDENT_DRILL.md`.

## 10. Cost estimate
Measured, not guessed: see `ARCHITECTURE.md` section 3 (cost per turn per mode from `python -m evaluations.run_evals`, scaled to 15M turns/month with the assumptions stated there). Voice STT/TTS and Redis costs are not measured and are labelled as assumptions.
