# Demo script: Saathi Care AI (5–8 minutes)

Use this as a shot list. Record and upload the video yourself; no video link exists yet. Live site:
https://d1a1ddkuv955vw.cloudfront.net (AWS Sydney, `ap-southeast-2`). Local run: see the README.

## Disclose on camera (say these, do not skip them)

- **Lexical groundedness is 73.8%, below the 80% target** (final live run). Claim-level faithfulness is 97.8%, so the lexical proxy
  may be penalising paraphrase; that explanation is untested.
- **The Gemini API key returns HTTP 403.** Every answer you see is served by **OpenAI** (the fallback). Semantic-cache embeddings
  also fail over to word-overlap matching.
- **Judge agreement (kappa 0.795) rests on one annotator** who labelled both annotator columns, so inter-annotator agreement is
  self-consistency, not independent agreement.
- **The lab partner and emergency alerts are simulated.** Alerts are log-only; no Telegram message is sent by the public demo.
- **Voice speech uses the browser's built-in engines.** The backend evaluation of voice uses simulated audio.

## Timeline

| Time | Segment | What to show | What to say |
|---|---|---|---|
| 0:00–0:45 | **Architecture overview** | `ARCHITECTURE.md` section 6 diagram, or `AWS_DEPLOYMENT.md` section 4 | One Google ADK 2.11 `Workflow` of `@node` steps; code makes every booking and safety decision, the LLM only words wellness answers; one EC2 host behind CloudFront, one backend instance by design (sessions are in memory). |
| 0:45–1:30 | **Mimi chat** | Open the live site → Chat with Mimi → ask "Suggest a gentle yoga routine for better sleep" | Mimi is the chat persona; answers cite library documents. Show the citation chips and "How I answered". |
| 1:30–2:15 | **Hinglish conversation** | "Mujhe sugar check karwana hai, kal subah 7:30 baje" | The request is understood in Hinglish; the reply comes back in Hinglish. Note that "9 baje" is refused for a fasting test (valid slots are offered). |
| 2:15–2:45 | **Emergency / safety** | "mujhe seene mein dard aur saans nahi aa rahi" | Deterministic red-flag rule (code, not the LLM): helplines immediately, booking cleared. No external alert is sent on the public demo. Mention the medication refusal if time allows: "what medicine for diabetes?" gets a no-diagnosis reply. |
| 2:45–3:45 | **Lab search and booking** | Lab Tests → pick a package → slot → "yes" to the read-back; then My Bookings; repeat "yes" | Explicit confirmation is required; a repeated "yes" creates no duplicate. Booking history shows the record. Simulated lab backend; `LAB_FAILURE_RATE` is 0 on this host. |
| 3:45–4:30 | **Voice assistant** | Open the **Voice assistant** screen (not Mimi) → Start voice conversation | The voice assistant is separate from Mimi; the orb reacts to the real microphone level. Speech uses the browser's engines; read-back before any booking. Use a headset or fake device if the mic is unavailable. |
| 4:30–5:15 | **Evaluation results** | `EVALS.md` results table | 55 chat cases (14.5% Hindi/Hinglish), 15 voice calls. Intent 95.83%, red-flag recall 100% (n=8), no-diagnosis 100% (n=5), wrong-booking 0% (n=4). Lexical groundedness 73.8% misses target (see disclosures). |
| 5:15–6:00 | **Mode A vs Mode B** | `EVALS.md` "Mode A vs Mode B" table | Mode A (library search, cites sources): 18.6 s mean, $0.00399/turn, 0% member-data correct. Mode B (member records only): 12.8 s, $0.00252/turn, 100% member-data correct. Recommendation: Mode B for member data, Mode A only for the library. |
| 6:00–6:30 | **Model routing decision** | `config/models.yaml` and `EVALS.md` "Proposed routing policy" | Default `gemini-3.5-flash-lite` with `gpt-4o-mini` fallback (lowest p95 among mixes that passed the gates, about $0.60 per 1k LLM turns). Note that the Gemini key is currently rejected, so the fallback is what is serving traffic. |
| 6:30–7:00 | **Observability** | `logs/traces.jsonl` (one root span per turn, child spans per node/tool/LLM call, shared `trace_id`); optional Langfuse | Every turn is traceable; content is redacted by default (`LANGFUSE_CAPTURE_CONTENT=false`). Say that Langfuse was not confirmed connected on the cloud host. |
| 7:00–7:45 | **AWS deployment** | Console links in `AWS_DEPLOYMENT.md` section 6: CloudFormation stack, EC2 instance, CloudFront | One CloudFormation stack in Sydney, Free plan with $100 credits (expire 2027-05-23), about ₹2,116/month. Secrets in Secrets Manager, not in the image. Health check `/api/health` returns ok. |
| 7:45–8:00 | **Close** | Repo and `AI_USAGE.md` | Public repo; AI tools used and where AI output was corrected; the disclosures above. |

## Pre-recording checklist

- [ ] Open the live site and confirm `/api/health` returns OK, so the demo does not start on a 504.
- [ ] Use a member with a clean booking history (the cloud demo already holds test bookings from earlier checks).
- [ ] Turn off notifications and close unrelated tabs.
- [ ] Allow microphone access, or plan to skip the live voice step and show the voice screen only.
- [ ] Keep the `.env` file and Secrets Manager values off screen.
- [ ] Have `EVALS.md`, `AWS_DEPLOYMENT.md` and the terminal ready for the trace walkthrough.
