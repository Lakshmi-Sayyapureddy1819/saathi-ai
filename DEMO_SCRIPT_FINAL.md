# Saathi Care AI: final demo script (about 7 minutes)

Read the **Say** blocks aloud as written. Replace `[your name]` in the opening. **Do** lists the actions. Each section lists what the viewer should notice, what is safe to quote, and a fallback.

Before recording, go through `DEMO_CHECKLIST.md`. Section A there decides which environment you record. Every claim here is traced in `DEMO_VERIFICATION.md`.

## Timeline

| Time | Section | Target |
|---|---|---|
| 0:00 to 0:50 | 1. Introduction and architecture | 50 s |
| 0:50 to 1:20 | 2. Chat with Mimi (Mode A) | 30 s |
| 1:20 to 1:45 | 3. Hinglish wellness question | 25 s |
| 1:45 to 2:25 | 4. Emergency and safety | 40 s |
| 2:25 to 3:10 | 5. Lab search and booking | 45 s |
| 3:10 to 3:45 | 6. Voice screen | 35 s |
| 3:45 to 4:25 | 7. Observability and trace walkthrough | 40 s |
| 4:25 to 5:10 | 8. Grounding: Mode A vs Mode B | 45 s |
| 5:10 to 5:50 | 9. Model routing and evaluation results | 40 s |
| 5:50 to 7:00 | 10. Conclusion and limitations | 70 s |

The targets include on-screen typing and waiting for replies. The narration alone is about 6 minutes 50 seconds (see the note at the end).

## Disclosures (say these in section 1 or 10; do not skip)

- The Gemini key is rejected right now, so replies come from OpenAI models.
- Lexical groundedness is 73.8%, below my 80% target.
- Judge agreement (kappa 0.795) comes from one person who labelled both annotator columns.
- The lab partner, telephony and emergency alerts are simulated.
- Browser speech is the browser's own engine. Voice timing numbers come from simulated audio.

---

## 1. Introduction and architecture

**Time:** 0:00 to 0:50 (50 s)

**Screen:** `https://github.com/Lakshmi-Sayyapureddy1819/saathi-ai`, file `ARCHITECTURE.md`, section 6.1 (the workflow diagram).

**Do:** Open the page, scroll to section 6.1, and leave the diagram on screen.

**Say:**

> Hi, I'm [your name]. This is Saathi Care AI, my take-home for HeyDoc AI. It is a wellness and lab-booking assistant in English, Hindi and Hinglish.
>
> It is a Google ADK workflow. Code makes every safety and booking decision: the safety gate, the emergency path and the booking confirmation. The language model writes wellness answers, helps classify intent when the rules do not decide, and acts as a second safety check that can only raise the risk level.
>
> Chat and the browser voice screen use the same API and workflow. This is a prototype: one backend instance, with in-memory sessions.

**Notice:** The decision nodes are in the diagram, and the model is not in control of safety or booking.

**Safe to quote:** One ADK workflow. Deterministic safety gate. One backend instance.

**Fallback:** If GitHub does not load, show the same section of `ARCHITECTURE.md` in the editor.

---

## 2. Chat with Mimi (Mode A)

**Time:** 0:50 to 1:20 (30 s)

**Screen:** The app (URL per the checklist), then **Chat with Mimi** (`#/chat`).

**Do:**
1. Open **Chat with Mimi**. In the start card, set **Continue as** to **Aarav Sharma** and start. Check that the mode is **Library search**.
2. Type `Suggest a gentle yoga routine for better sleep` and send.
3. Open **How I answered**.

**Say:**

> Mimi is the chat assistant. This is Mode A, library search. The coach searches the wellness library and cites the documents it used. Each citation is checked against the documents the model was given. Under **How I answered** you can see the search query, and whether the AI chose the lookup.

**Notice:** Citation chips with library titles. The search query under **How I answered**.

**Safe to quote:** The answer cites library documents. Citations are checked after the model returns them.

**Fallback:** If the app says it cannot reach the AI model, say the app reports that instead of inventing an answer, then show `frontend/e2e/screenshots/19-citations.png`.

---

## 3. Hinglish wellness question

**Time:** 1:20 to 1:45 (25 s)

**Screen:** Same chat page.

**Do:** Type `Mujhe raat ko neend nahi aati, koi yoga batayein` and send.

**Say:**

> Now a Hinglish question. The reply comes back in Hinglish, with a citation, and the pose names stay as they are in the library. One prompt rule I changed moved the strict groundedness score from 72.6 to 80.7 percent, in one run of twelve questions. That is a direction, not a result, and the strict score only checks English.

**Notice:** The reply language follows the question, and the pose name is not translated.

**Safe to quote:** Hinglish replies work. The 72.6 to 80.7 change is one run of 12 questions.

**Fallback:** `frontend/e2e/screenshots/03-wellness-hinglish.png`.

---

## 4. Emergency and safety

**Time:** 1:45 to 2:25 (40 s)

**Screen:** Same chat page.

**Do:**
1. Type `mujhe seene mein dard aur saans nahi aa rahi` and send. Show the emergency card.
2. Type `what medicine for diabetes?` and send. Show the safety notice.

**Say:**

> This message describes chest pain and breathlessness. The red-flag rule is plain code, and it runs before any model is called. The member gets the helplines at once, and the draft booking is cleared. In this deployment the alert is log only. Nothing is sent to Telegram or SMS.
>
> Next, a medicine question. The app does not diagnose or advise on medicines. It points the member to a doctor or to a lab test.
>
> On my eight-case golden set, red-flag recall is 100 percent. The offline set passes as well, but I tuned those rules after its first run failed.

**Notice:** The emergency card appears at once, with 112, 108 and 14416. The medicine question gets a refusal and a next step.

**Safe to quote:** Red-flag recall 100% on 8 golden cases. 27 of 27 offline core phrasings, tuned. Alerts are log only.

**Fallback:** `frontend/e2e/screenshots/04-emergency.png`.

---

## 5. Lab search and booking

**Time:** 2:25 to 3:10 (45 s)

**Screen:** **Lab Tests** (`#/labs`), then **Chat with Mimi**, then **My Bookings** (`#/bookings`).

**Do:**
1. Open **Lab Tests**. Say the count, 12 packages.
2. In **Chat with Mimi**, type `I feel tired all the time, I want to check my thyroid` and send. Expect thyroid slots.
3. Type `tomorrow 9 am` and send. Expect a read-back ending in "Shall I go ahead and book it? (yes/no)". If 9:00 is not offered, pick the first slot offered.
4. Type `yes`. Expect a confirmation with a booking ID. Do not read the ID aloud.
5. Type `yes` again. Expect "no booking pending".
6. Open **My Bookings** and show the new row.

**Say:**

> I'll ask about a thyroid check. The app lists slots, and I pick tomorrow at nine. Before anything is booked, the app reads back the test, date and time, and asks yes or no. I say yes and get a booking ID. A second yes books nothing new.
>
> The lab is an in-process simulator. There is no real lab partner, and failures are simulated with the default failure rate at zero.

**Notice:** The read-back comes before the booking. The second yes creates nothing.

**Safe to quote:** Booking needs an explicit yes. A repeated yes creates no duplicate. The lab partner is simulated.

**Fallback:** `frontend/e2e/screenshots/08-booked.png` and `17-my-bookings.png`. Say the booking path was also tested through the API, with the same result.

---

## 6. Voice screen

**Time:** 3:10 to 3:45 (35 s)

**Screen:** **Talk to Mimi** (`#/voice`). Keep the navigation label as it is.

**Do:**
1. Open **Talk to Mimi** and point at the orb. Start a voice conversation and allow the microphone.
2. Say `Mujhe thyroid test book karna hai`, then `Kal subah 10:30 baje`.
3. When **Please confirm these details** appears, say `yes, confirm` or tap **Confirm booking**.

**Say:**

> This is the voice screen. The orb shows the assistant's state. Speech recognition and synthesis are the browser's own engines. The transcript goes into the same workflow as chat. Before anything is booked, the app reads back the details and waits for a clear yes. If the browser reports low recognition confidence, the app holds the text for review. If I speak over the assistant, it stops.
>
> I have not measured real speech accuracy or accents. The timing figures come from simulated audio.

**Notice:** The read-back card appears before the booking. Mimi sits inside the orb and reacts to the assistant's state.

**Safe to quote:** Read-back before booking. In a simulated evaluation of 15 calls, 20 of 20 read-back checks were correct, with no wrong bookings. Real speech is not measured.

**Fallback:** No microphone: say so, then show `frontend/e2e/screenshots/v8-voice-readback.png`.

---

## 7. Observability and trace walkthrough

**Time:** 3:45 to 4:25 (40 s)

**Screen:** Terminal at the repository root, on a **local** run. The cloud trace file is on the server and is not visible here.

**Do:**
1. Run the first command below and pick the most recent trace ID.
2. Run the second command with that ID.

**Say:**

> Each turn has one root span. Every node, tool and model call is a child span with the same trace ID. This is the local trace file.
>
> Each model span shows the route and the model that answered. If a call failed, its span is marked failed, and the next model call is the fallback. Message text is redacted by default.
>
> Langfuse export is built, and I saw node and tool spans there in an earlier run. I have not verified the model spans or the Langfuse screen, so I won't show them.
>
> One known bug: a safety-check model call can be filed under the previous turn's trace ID. I found it while testing, and I have not fixed it yet.

**Notice:** One trace ID runs through all spans. Model spans show route and model. The text is redacted. A failed span can appear, because the Gemini key is rejected. Use it to show the fallback if it appears.

**Safe to quote:** One root span per turn, with child spans for each node, tool and model call. Content redacted by default.

**Fallback:** Show a saved copy of the command output, or `logs/traces.jsonl` in the editor.

**Terminal commands.** Run these in **Git Bash** from the repository root. Windows PowerShell 5.1 strips the double quotes inside the `-c` argument, so the commands fail there. I tested these in Git Bash.

List the last three turns:

```
.venv/Scripts/python.exe -c 'import json; r=[s for s in (json.loads(l) for l in open("logs/traces.jsonl",encoding="utf-8") if l.strip()) if s.get("kind")=="root"]; [print(s["trace_id"], (s.get("metadata") or {}).get("channel",""), s.get("latency_ms")) for s in r[-3:]]'
```

Show every span for one trace (replace the ID):

```
.venv/Scripts/python.exe -c 'import json,sys; t=sys.argv[1]; [print(s["kind"], s["name"], (s.get("metadata") or {}).get("route",""), (s.get("metadata") or {}).get("model",""), "FAILED" if (s.get("metadata") or {}).get("failed") else "", s.get("latency_ms")) for s in (json.loads(l) for l in open("logs/traces.jsonl",encoding="utf-8") if l.strip()) if s.get("trace_id")==t]' REPLACE_WITH_TRACE_ID
```

Clear the terminal first. Do not show the ADK warnings or the shutdown message from asyncio.

---

## 8. Grounding: Mode A vs Mode B

**Time:** 4:25 to 5:10 (45 s)

**Screen:** **Chat with Mimi**, then the `EVALS.md` table "Mode A (retrieval) vs Mode B (facts + tools)" on GitHub.

**Do:**
1. Switch the answer mode to **Your records** (Mode B).
2. Type `What programs am I enrolled in?` and send. Point out that it lists IDs, not titles.
3. Type `Suggest a gentle yoga routine for better sleep` and send. Expect "I don't have that information."
4. Open the `EVALS.md` table.

**Say:**

> Mode A is library search. It cites sources, but it cannot answer questions about one member's data. Mode B reads the member's records through tools and answers only from those facts. It names programs by ID, a gap I have not fixed.
>
> In the 23 November run, Mode A cited answers on all twelve wellness questions. Mode B answered none of them, by design. On five member-data questions, Mode B got five right, and Mode A got none right. Cost was about 0.004 dollars per turn for Mode A and 0.0025 for Mode B. Mode A's cost moved about 4.6 times between runs, and I have not explained that.
>
> My recommendation: Mode B for member data, and Mode A only for the library.

**Notice:** The toggle changes the behaviour. Mode B refuses what its records cannot answer.

**Safe to quote:** One run, 12 wellness and 5 member-data questions per mode. Mode B 5 of 5 on member data, Mode A 0 of 5. Cost and latency vary between runs.

**Fallback:** `frontend/e2e/screenshots/20-mode-a-library.png` and `21-mode-b-records.png`.

---

## 9. Model routing and evaluation results

**Time:** 5:10 to 5:50 (40 s)

**Screen:** `config/models.yaml` in the editor, then the `EVALS.md` results table.

**Do:** Show the three routes in `config/models.yaml`, then the results table.

**Say:**

> Models come from `config/models.yaml`. There are three routes, each with a fallback to a different vendor. In the 22 November four-mix snapshot, Gemini 3.8 Flash cost about seven times the lite model per turn, and quality was not clearly different. So my proposed default is Gemini Flash-Lite, with GPT-4o-mini as fallback.
>
> A correction: the chat coach runs on the quality route today, Gemini 3.8 Flash with GPT-4o fallback. The cost I quote is for the lite mix.
>
> From the 23 November run: intent accuracy 95.8 percent, 23 of 24. Red-flag recall 100 percent on eight cases. Zero wrong bookings in four. Groundedness 73.8 percent, below my 80 percent target. Judge agreement 0.795, from one person labelling both columns.

**Notice:** The config is simple, and the correction is stated plainly.

**Safe to quote:** Each figure above, with its sample size. The four-mix figures come from the 22 November snapshot.

**Fallback:** Show `EVALS.md` in the editor, at "Metrics".

---

## 10. Conclusion and limitations

**Time:** 5:50 to 7:00 (70 s, including a pause at the end)

**Screen:** The GitHub repository README, section "Known gaps".

**Say:**

> To finish: what works, and what does not.
>
> Working and tested: the ADK workflow, the safety gate, booking confirmation, both grounding modes and the local trace file. The backend has 584 passing tests today. The frontend typecheck is clean, and 31 frontend unit tests pass.
>
> Not working, or not proven: the Gemini key is rejected right now, so replies come from OpenAI. Groundedness is below target. The lab partner, telephony and alerts are simulated. Real speech, Langfuse model spans and real Redis are untested.
>
> LLM spend is about 3.8 US dollars, under the 500 rupee cap at the rate in my README. It is a prototype, not production. Thank you.

**Notice:** The limits are stated before anyone asks.

**Safe to quote:** 584 backend tests and 31 frontend tests passing (re-run on 23 November). About USD 3.8 spend, under the cap at the README rate.

**Fallback:** None needed. This section is spoken.

---

## Expected duration

The narration is about 960 words. At 140 words per minute that is about 6 minutes 50 seconds, before typing and waiting for replies. I have not timed a rehearsal, so expect a run of 7 to 7:30. To get under 7:00, cut the cost sentence in section 8 and the "seven times" clause in section 9.
