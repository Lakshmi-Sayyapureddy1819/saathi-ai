# Demo preparation and recording checklist

Use with `DEMO_SCRIPT_FINAL.md`. Nothing here has been recorded or uploaded. Items marked **Decision** need your choice before you record.

## A. Decisions first

- [ ] **Decision: which environment to record.**
  - **Public site** `https://d1a1ddkuv955vw.cloudfront.net`. Its frontend is **older than HEAD**: the live bundle (`index-RYGtdC6W.js`) does not match the current local build (`index-CiuGxcdi.js`). The last recorded redeploy was 14:33 IST, before several commits. The backend version is unknown. Options: redeploy HEAD first (`deploy\deploy.ps1 -Action Update`, documented in `AWS_DEPLOYMENT.md` section 9; this changes deployment resources, so it needs your approval), or record locally.
  - **Local** on `127.0.0.1` with the safe settings in section B. This shows HEAD's behaviour.
  - Section 7 (trace walkthrough) is always **local**. The cloud trace file is on the server.
- [x] **Voice screen and Mimi (resolved 23 Nov).** Mimi is back inside the voice orb on the "Talk to Mimi" page, at your request. The e2e assertion was flipped to match. Not yet re-run in a browser (Playwright Chromium download stalled); typecheck and 31 unit tests pass.
- [ ] **Decision: coach routing.** The coach runs `quality_optimized` (`gemini-3.8-flash`, fallback `gpt-4o`), not the `cost_optimized` route the routing table recommends. Either change `app/workflow/graph.py` line 126 and re-measure, or keep the on-camera correction in section 9 (the script does this).
- [ ] **Decision: the trace-ID bug.** Section 7 mentions it on camera. Remove that paragraph only after you fix it.
- [ ] **Decision: `ARCHITECTURE.md`.** It has an uncommitted edit in the working tree. Commit or discard it before showing the repository. I did not commit anything.
- [ ] **Gemini key.** It is rejected (HTTP 400 locally, HTTP 403 on the cloud host). Rotating it or checking API access is outside the code. Until then, replies come from OpenAI, and the script says so.

## B. Safety settings for any local run (required)

Your local `.env` contains **Telegram credentials** and Upstash, Langfuse and lab-partner settings. If you start the backend with that file as it is, an emergency message can be sent to a **real care-team Telegram chat**, and traces can go to Langfuse. Do this before starting the backend:

- [ ] Start the backend from **Git Bash** in the repository root, with these variables set to empty or simulator values. This is the form I tested:

```
APP_ENV=development TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= UPSTASH_REDIS_REST_URL= UPSTASH_REDIS_REST_TOKEN= REDIS_URL= LANGFUSE_PUBLIC_KEY= LANGFUSE_SECRET_KEY= LANGFUSE_HOST= LAB_BACKEND=simulator LAB_API_URL= LAB_API_KEY= LAB_FAILURE_RATE=0 ALLOW_SIMULATORS=1 .venv/Scripts/python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

- [ ] **Do not use PowerShell for this.** In PowerShell, `$env:NAME=""` deletes the variable, so `.env` would load the Telegram token again. The Git Bash form keeps the variables set and empty, so `python-dotenv` (which does not overwrite existing variables) leaves them blank.
- [ ] Confirm alerts are log-only: `curl http://127.0.0.1:8000/api/readiness` must show `emergency_alerts` as `simulated` with "log only (no channel configured)". I ran this same setup on port 8300 on 23 November, and it showed exactly that.
- [ ] Start the frontend in a second terminal: `npm run dev` inside `frontend\` (per `README.md`), then open `http://127.0.0.1:5173`.
- [ ] Do not open or show `.env` or any secret value on screen.

## C. Pre-flight checks (do these the day you record)

- [ ] Public health: `curl https://d1a1ddkuv955vw.cloudfront.net/api/health` returns `{"status":"ok"}`. (Checked on 23 Nov: returned ok.)
- [ ] Public readiness: `curl https://d1a1ddkuv955vw.cloudfront.net/api/readiness` shows `ready: true`, `emergency_alerts` simulated. (Checked on 23 Nov.)
- [ ] Public LLM status: `curl https://d1a1ddkuv955vw.cloudfront.net/api/llm-status`. Expect Gemini rejected, and the `gpt-4o` fallback serving. If Gemini works again, the script's statements about the key are wrong; change them.
- [ ] Public bundle: `curl -s https://d1a1ddkuv955vw.cloudfront.net/ | findstr /i assets/index` shows whether the build changed since 23 Nov.
- [ ] Local tests (optional but recommended, from Git Bash): `.venv/Scripts/python.exe -m pytest tests -q` should show 584 passed. `npx tsc --noEmit` and `npx vitest run` in `frontend\` should be clean with 31 passed.
- [ ] Rehearse the whole script **twice**, once with a timer. Note which sections run long.
- [ ] Check the AWS facts the script relies on in AWS Settings, not from memory: the project's Region (`AWS_DEPLOYMENT.md` says `ap-southeast-2`, under **AWS Settings > View all projects > Overview > Additional Info > Region**), and the credit balance and spend under **AWS Settings > Billing**. The script does not quote AWS cost figures.

## D. Data and state

- [ ] Member: **Aarav Sharma** (`MEM_1001`, Hinglish preference, pending thyroid checkup `LP_002`). The script uses him for sections 2 to 8.
- [ ] Look at **My Bookings** before you start. Earlier checks left bookings on the public demo, so pick a member with a clean history if the list is confusing.
- [ ] **Dates are relative.** "Tomorrow" and "kal" are resolved from the day you record. Read the date the app shows; never say a fixed date. If 9:00 is not offered, choose the first slot listed.
- [ ] **Booking IDs differ on every run.** Do not read them aloud, and do not put one in a caption.
- [ ] **The answer cache is in memory.** A repeated question is answered from cache: no LLM call, and no model spans. If you rehearsed the yoga question, restart the backend before recording, or use new phrasing. On the public site the cache state is unknown.
- [ ] The fasting example (`Mujhe sugar check karwana hai, kal subah 9 baje`) is refused for the diabetic profile with early slots offered. Use it only if you need a backup for section 5.
- [ ] Section 7 needs **one fresh local chat turn** just before the walkthrough, so the newest trace is there.

## E. Browser and microphone (section 6)

- [ ] Use **Chrome or Edge**. The voice screen needs the browser's speech recognition and speech synthesis.
- [ ] Allow the microphone. Test it: say the three voice phrases once and watch the read-back card appear.
- [ ] Use a headset if you have one, to avoid echo.
- [ ] If the browser does not report recognition confidence, the app holds booking speech for a tap-to-confirm review. The read-back still happens. Test this before recording.
- [ ] If you have no working microphone, skip the speaking and show `frontend/e2e/screenshots/v8-voice-readback.png`. Say that the voice numbers are simulated.

## F. Screen and privacy

- [ ] Close other tabs, notifications and any chat or email windows.
- [ ] **Terminal path:** the prompt shows your Windows user folder. Crop the recording so it is not visible, or open the repository from a shorter path, before recording section 7.
- [ ] Clear the terminal. Do **not** show the ADK "branch will end" warnings or the asyncio "Event loop is closed" message. They appear in the server output.
- [ ] Do not show: `.env`, any secret, the Telegram token, Langfuse keys, the Upstash token, the coordinator token, AWS account IDs, or the AWS console pages with account details. The script does not need the AWS console.
- [ ] Set the browser zoom to about 110% so the chat is legible. Record at 1920x1080 or a similar size.
- [ ] Keep the `EVALS.md` and `config/models.yaml` tabs open and scrolled to the right place before section 8 or 9.

## G. Run of show and time checks

| Checkpoint | Expected time | If you are behind |
|---|---|---|
| End of section 2 | 1:20 | Skip the citation panel details |
| End of section 5 | 3:10 | Skip the **My Bookings** step |
| End of section 7 | 4:25 | Skip the Langfuse paragraph |
| End of section 9 | 5:50 | Shorten to the first two sentences and the results |
| Section 10 | 7:00 | Keep the disclosures; cut the closing sentence |

Cut order, most expendable first: the "seven times" clause in section 9; the cost sentence in section 8; the Langfuse paragraph in section 7; the voice walkthrough (show the screenshot instead). **Never cut the disclosures** (Gemini, 73.8%, single annotator, simulated lab and alerts).

## H. Fallback assets (in the repository)

| Need | File |
|---|---|
| Citation chips and How I answered | `frontend/e2e/screenshots/19-citations.png` |
| Hinglish wellness | `frontend/e2e/screenshots/03-wellness-hinglish.png` |
| Emergency card | `frontend/e2e/screenshots/04-emergency.png` |
| Booked confirmation | `frontend/e2e/screenshots/08-booked.png` |
| My Bookings | `frontend/e2e/screenshots/17-my-bookings.png` |
| Voice read-back | `frontend/e2e/screenshots/v8-voice-readback.png` |
| Voice review | `frontend/e2e/screenshots/v7-voice-review.png` |
| Mode A and Mode B | `frontend/e2e/screenshots/20-mode-a-library.png`, `21-mode-b-records.png` |
| Routing config | `config/models.yaml` |
| Evaluation tables | `EVALS.md` |
| Architecture diagram | `ARCHITECTURE.md` section 6.1 |
| Offline voice evaluation output | run `.venv/Scripts/python.exe -m evaluations.voice_eval` (free, simulated) |
| Offline safety evaluation output | run `.venv/Scripts/python.exe -m evaluations.deterministic_eval` (free) |

The screenshots were refreshed in commit `a69d6a1` (23 November, 17:40 IST, "refresh screenshots for Talk to Mimi screen"). They show the local build at that commit, not the live site. The screenshot folder also has a `redesign` subfolder; use the top-level files.

## I. Known gaps to be ready to answer

- Gemini is rejected, so replies come from OpenAI.
- Lexical groundedness is 73.8%, below the 80% target.
- Judge agreement (kappa 0.795) is from one annotator. The 1.000 "inter-annotator" value is not independent evidence.
- Mode B names programs by ID, not title.
- Mode A's cost moved about 4.6 times between runs and is unexplained.
- The semantic cache is running its token-overlap fallback. Its 0% false-hit figure was measured on embeddings and does not apply.
- Langfuse model spans and the Langfuse screen are not verified. Real Redis is not verified.
- Real speech, real telephony and a real lab partner are not tested.
- The cloud frontend may be older than HEAD (see section A).
- Spend is about USD 3.8 from the app's own price table, not a provider invoice.

## J. After the recording

- [ ] Review the recording before any upload. Upload only after you have checked the disclosures are audible.
- [ ] Remove any browser history, microphone permissions or saved sessions you do not want kept, if you recorded on a shared machine.
- [ ] Stop the local backend and frontend processes you started.
- [ ] Commit or discard the `ARCHITECTURE.md` change, and keep `DEMO_*.md` out of commits unless you intend to publish them.
