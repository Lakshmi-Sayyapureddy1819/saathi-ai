# Evaluation snapshots

Dated, frozen evidence for reviewers. **Do not edit these files.** They are the per-case record behind `EVALS.md`
(responses, triage results, the groundedness/faithfulness audit with unsupported-claim lists, and the Mode A/B
latency and token lists).

| File | Run | Models | LLM calls | SHA-256 |
|---|---|---|---|---|
| `eval_results_2026-11-22.json` | 2026-11-22 08:00 (IST), 02:30 UTC | `gemini-3.5-flash-lite` (68 calls), `gemini-3.8-flash` (30 calls) | 98 real, 0 mock, 0 failed | `96182c6aa63ead388cde2318904fe1d20d3238d62c1929eaf1615ff64c2071e5` (LF line endings, as stored in Git) |
| `eval_results_2026-11-22_061107.json` | 2026-11-22 (later run, `--promote`) | `gemini-3.5-flash-lite`, `gemini-3.8-flash` | real | `9f2b277d84d095e763fe0ec3b5781e797d9bd1086633626d13a3c674bd404c14` (LF) |
| `prompt_iterations_2026-11-22.json` (+ `.md`, `.notes.txt`) | 2026-11-22, `python -m evaluations.prompt_iterations` | `gemini-3.5-flash-lite` (coach) + `gemini-3.8-flash` (faithfulness judge) | real | `afc628565d9db98db43df52570e8622024ec8667116675f117410cef7a532bac` (LF) |

**Checksum note.** The SHA-256 above is of the file with LF line endings, which is what Git stores. On Windows with `core.autocrlf=true` the checked-out file has CRLF line endings and hashes to `55f4fdc3b7016c39c11ad1d304f1921e8413456abdbc3669724b0466dfcfa519`. To verify on any platform: `python -c "import hashlib;print(hashlib.sha256(open('FILE','rb').read().replace(b'\r\n',b'\n')).hexdigest())"`.

Produced by `python -m evaluations.run_evals` on the working tree on top of commit `40ba3c3`, before the evaluation
output paths below were introduced (it was then written to `evaluations/eval_results.json`; the earlier tracked
version of that file remains in Git history). `EVALS.md` is the human-readable report for the **latest** snapshot (`eval_results_2026-11-22_061107.json`, which adds the voice metrics); the first file is the earlier run kept as history.

## How future runs avoid noisy tracked-file changes

LLM output, trace ids and latencies differ on every run, so tracking a regenerated file produces ~1,000-line diffs that
say nothing. Therefore:

- A normal run writes **only** to `evaluations/runs/<UTC stamp>/` (`eval_results.json`, `EVALS.md`). That folder is
  git-ignored. Nothing tracked changes.
- To publish a run deliberately, use `python -m evaluations.run_evals --promote`. It rewrites `EVALS.md` and **adds** a
  new dated file here. An existing snapshot is never overwritten (a same-day second promote gets a time suffix).
- Promote rarely (for example, once per submission or release), and commit the new snapshot together with the
  `EVALS.md` it belongs to. Treat older snapshots as history.
