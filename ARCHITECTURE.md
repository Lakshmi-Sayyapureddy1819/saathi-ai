
# Enterprise Architect Memo: Saathi Care AI

**To:** HeyDoc AI Steering Committee  
**From:** Enterprise AI Architect  
**Date:** 2026-11-21  
**Subject:** Production Architecture for Saathi Care AI at 15M Monthly Turns Scale

---

> **Scope of this memo.** It describes the *target production architecture* at 15M turns/month. The repository
> implements a prototype subset: the deterministic safety gate, the workflow graph (plain Python and an ADK 2.11
> wrapper with a coordinator-approval pause), lab tools with a simulated partner API, grounding (Mode A/B), an
> in-process embedding cache, redacted logging/tracing, and the evaluation harness. **Not implemented here:**
> Kubernetes, Redis, a real ASR/TTS service, DPDP consent tokens, the `/user/purge-data` erasure endpoint, a
> circuit-breaker, Twilio (the SMS is a logged mock) and real voice audio. Sections 2, 4 and 5 are design intent.
>
> **Cost figures.** Every dollar figure below is derived from per-turn costs measured with `python -m evaluations.run_evals`
> (section 3 shows the arithmetic and the assumptions). The earlier $4,980 / $28,500 projection has been removed. STT/TTS and
> Redis costs were **not measured** and are left as explicit inputs, not guessed.

### Measured LLM cost (2026-11-22, `python -m evaluations.run_evals`, gemini-3.5-flash-lite, cache off)

| Mode | Mean tokens/turn (incl. thinking) | Cost/turn | 15M wellness turns/month |
|---|---|---|---|
| A (retrieval) | 810.7 - 918.0 (3 runs) | $0.000521 - $0.000623 | ~$7,800 - $9,300 |
| B (facts + tools) | 564.8 - 640.2 (3 runs) | $0.000234 - $0.000253 | ~$3,500 - $3,800 |

Three runs on the migrated model (n=12 turns per mode each; later runs also include the retrieval and prompt-v4
changes, which answer two more questions with an LLM call, so Mode A rose slightly; treat as +/-25%). Previous model (gemini-2.5-flash, 2 runs): Mode A $0.001463-$0.001861/turn, Mode B $0.000934-$0.001220/turn.
Prices (Standard, per 1M tokens, verified 2026-11-22 on aistudio.google.com/docs/pricing): gemini-3.5-flash-lite
$0.30 in / $2.50 out; gemini-3.8-flash $0.75 / $3.75 through 2026-12-31, then $1.50 / $7.50 from 2027-01-01 (used for
the quality route and the eval judge; not in the table above); GPT-4o $2.50 / $10; GPT-4o-mini $0.15 / $0.60.
Caveats: wellness questions only (booking turns make no LLM call unless the router falls back); voice STT/TTS and
Redis costs were **not measured**; no cache saving is assumed anywhere in section 3 (measured cache hit rate ~0% at the safe 0.88 threshold). Models migrated from gemini-2.5-flash/pro per Google's deprecation page (shutdown 2026-12-01).

## 1. Executive Summary

This document outlines the production architecture for the Saathi Care AI assistant, designed to handle a target load of **15 million monthly turns** (10M chat, 5M voice). The architecture prioritizes cost efficiency, regulatory compliance under India's DPDP Act 2023, and operational resilience. By implementing a tiered model routing strategy and an intelligent caching layer, the LLM cost is projected from measured per-turn costs only (section 3); no cache saving is assumed because none was measured. The system is engineered for deterministic safety, data privacy, and robust observability from day one.

## 2. Scale & Performance Architecture

The system is designed as a containerized Python application, deployed on a managed Kubernetes cluster (e.g., GKE Autopilot, AKS) for automated scaling.

- **Target Load:** 15,000,000 turns/month
- **Peak Load Estimate:** ~15 turns/second (assuming 8-hour daily peak usage)
- **Voice Channel:** Voice input will be handled by a dedicated Speech-to-Text (ASR) service (e.g., Google Chirp, Azure Speech). The raw audio is **never** stored; only the transcript is passed to the core application.

```mermaid
graph TD
    subgraph User Channels
        A[Chat Client]
        B[Voice Client]
    end

    subgraph Infrastructure
        C[Load Balancer]
        D[ASR Service]
        E[K8s Cluster: Saathi Care AI Pods]
        F[Redis Enterprise]
    end

    subgraph Core Logic in Pod
        G[Safety Gate]
        H[Workflow Graph]
        I[Tool Suite]
        J[Grounding Engine]
    end

    subgraph External Services
        K[LLM Providers API]
        L[Twilio API]
        M[Langfuse API]
    end

    A --> C
    B --> D --> C
    C --> E
    E --> G --> H
    H --> I
    H --> J
    I --> F
    J --> F
    I --> K
    J --> K
    H -.-> L
    H -.-> M
    I -.-> M
```

## 3. Tiered routing and cost estimate (built on measured costs)

**Model mix (what the repo actually runs, `config/models.yaml`):** every production LLM call (the coach's answer and the
router's fallback classification) uses `gemini-3.5-flash-lite` (fallback `gpt-4o-mini`). `gemini-3.8-flash` is used only
as the eval judge, so it is not in the serving cost. Booking, safety, slot parsing and handoff make **no** LLM call.
A separate `voice` route now exists (same model, latency-first, wired through `WorkflowGraph(model_node="voice")`), and the same eval was run on four mixes (gemini-3.5-flash-lite, gemini-3.8-flash, gpt-4o-mini, gpt-4o): see `EVALS.md` "Model mixes" for quality, p50/p95 and cost per 1k conversations, and the routing policy. Cheapest passing mix: gpt-4o-mini ($0.19 / 1k LLM turns) but it has the worse p95; flash-lite is kept as default for its p95. Not built: streaming into TTS.

**Measured per-turn LLM cost** (latest run, 2026-11-22, n=12 wellness turns per mode, cache off): Mode A $0.000618,
Mode B $0.000251 (range over runs: A $0.00052-$0.00062, B $0.00023-$0.00026).

**Projection to 15M turns/month (10M chat + 5M voice).** Cost = turns that call the coach LLM x measured cost per turn.
The share of turns that are LLM wellness turns is an **assumption** (it depends on real traffic, which we do not have),
so three values are shown:

| Share of all turns that call the coach LLM | Mode A (retrieval) | Mode B (facts + tools) |
|---|---|---|
| 25% (3.75M turns) | ~$2,300 | ~$940 |
| 50% (7.5M turns) | ~$4,650 | ~$1,880 |
| 100% (upper bound, 15M turns) | ~$9,300 | ~$3,750 |

Arithmetic: turns x $0.00062 (A) or x $0.00025 (B). Treat as +/-25% (run-to-run variation). No cache saving is
included: the semantic cache measured ~0% hit rate at the safe 0.88 threshold, and member-specific (Mode B) answers are
never cached. These figures cover the LLM only.

**Not in the numbers (inputs to be priced, not guessed):**
- Voice STT and TTS: cost = (5M voice turns x average seconds of audio per turn) x the chosen vendor's per-minute / per-character list price. Neither the audio length nor the vendor price was measured here.
- Redis, Kubernetes/Cloud Run compute, Langfuse, egress.
- Router fallback LLM calls (a short classification) occur only when no keyword rule decides; their share of traffic was not measured.

**Latency budgets (measured vs target):**

| Path | Target | Measured |
|---|---|---|
| Booking / safety / emergency turn (no LLM) | < 100 ms workflow | p50 ~10 ms, p95 ~45 ms (voice eval, 50 turns) |
| Voice time to first audio (caller stops -> first sound) | 1.5 s | Booking turns: ~60 ms workflow + simulated STT/TTS, so within budget only *before* real STT (~400 ms) and TTS (~300 ms), which are assumed. Wellness-by-voice turns: 1.8-2.9 s before real STT/TTS, **over budget** |
| Chat wellness answer | ~3 s p50 | LLM mean 2.7-4.7 s across runs; p95 up to 12 s in a loaded run |

To bring voice wellness turns inside 1.5 s the design needs streaming tokens into TTS and a smaller/faster voice route;
neither is implemented. In production, keep Langfuse export off the request path (done for voice: it cost about 400 ms
per turn when flushed synchronously).

**Where caching and smaller models fit.** Mode B facts and all transactional turns avoid retrieval and (mostly) the LLM
altogether, which is why Mode B costs about 2.5x less per turn here. A semantic cache only helps generic Mode A
questions and only at a threshold high enough to avoid wrong-answer hits; our measured saving is ~0%, so none is claimed.
`gemini-3.5-flash-lite` is already the small model; the next saving is routing, not shrinking further.

**Deployment (design intent, not built):** Cloud Run (stateless, autoscaling, min-instances for voice) or Vertex AI Agent
Engine, with session state in Redis/Firestore; the ADK workflow is the same in either.

## 4. Health data, consent and retention under India's DPDP Act 2023 (design intent; consent, erasure and audio handling are NOT implemented)

**What we log vs mask.**

| Data | Log? | Treatment |
|---|---|---|
| Member's own words (chat text, voice transcript) | Not in plain text | **Implemented:** redacted in logs, stdout and trace spans (length + opaque tag only). Raw-text capture is an explicit opt-in (`LANGFUSE_CAPTURE_CONTENT`), off by default |
| Call audio | Never stored | Processed in memory by the ASR service and discarded; only the redacted transcript flows on. Voiceprints are biometric-adjacent, so no audio is retained for QA unless a separate explicit consent exists |
| Names, phone numbers, member ids | Pseudonymous member id only | Names/phones masked in traces; id is the join key |
| Symptoms, booking details, triage level | Triage level and booking ids yes; free-text symptoms no | Triage status and `trace_id` are enough for audit; the symptom text is not copied into logs or the emergency SMS |
| Token counts, latency, cost, model, prompt version | Yes | Not personal data |

**Consent (DPDP s.6).** Granular, purpose-specific consent recorded *before* the first health-related turn: (1) coaching,
(2) lab booking and sharing booking data with the partner lab, (3) optional QA use of transcripts. Withdrawal is as easy
as giving it and disables the matching purpose immediately.

**Retention and erasure (DPDP s.8(7), s.12-13).** Proposal, to be confirmed with the client's counsel: chat/voice turn
history 30 days, then deleted; booking records for the period the lab relationship requires; traces keep no member text, so
they can live 90 days. A `/user/purge-data` endpoint deletes turn history, drafts and cached member-specific answers
within 24 hours of a verified request. Cross-border: confirm LLM/ASR provider regions before sending health context abroad.

## 5. Top 3 production risks and how we would watch for them

_Implemented in the prototype: member message text is redacted from logs, stdout and trace spans (length + opaque tag only)._

| # | Risk | Mitigation | How we would watch it in production |
|---|---|---|---|
| 1 | Slang or code-mixed distress that the red-flag regexes miss (a false negative is the worst failure) | Daily false-negative audit queue; a second-stage classifier that can only raise the triage level (not built) | Weekly recall on a growing labelled red-flag set (target 100%); alert on any human-reviewed miss; rate of sessions the audit queue flags |
| 2 | Partner lab API 500 spike | Retries with backoff, then handoff to a care coordinator (built); circuit-breaker to stop hammering a dead API (not built) | Alert on `tool:book_test` error rate and handoff-ticket rate (the incident drill shows both: `docs/INCIDENT_DRILL.md`); coordinator queue age |
| 3 | Voice time-to-first-audio drift and wrong readings of numbers/dates | Read-back of test, date and slot plus an explicit yes (built); streaming into TTS and local TTS fallback (not built) | p95 TTFA per turn type against the 1.5 s budget; read-back correction rate (caller says "no" after a read-back); wrong-booking rate (target 0) |
