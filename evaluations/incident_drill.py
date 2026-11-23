"""Incident drill (brief section 7): break something on purpose, then show the traces and eval output an on-call
engineer needs to find the cause fast.

    python -m evaluations.incident_drill

Two incidents, each compared with a healthy baseline run in the same process:
  A. "Lab API down"      - partner booking API fails every call (LAB_FAILURE_RATE=1 equivalent).
  B. "Bad prompt change" - the active coach prompt is rolled back to v1 (no facts, no rules, no question).

Outputs (docs/incident_drill/): drill_results.json, trace_*.txt (span trees), report.html (eval diff + trace
waterfalls; screenshotted by frontend/e2e/incident_drill.spec.ts). Spans also go to Langfuse when keys are set; the
trace ids printed here can be pasted into the Langfuse trace search.
"""
import json
import os
import statistics
import sys
import time
from html import escape
from pathlib import Path
from typing import Dict, List, Optional

os.environ["TRACE_FILE"] = "logs/drill_traces.jsonl"   # must be set before the tracer is imported
sys.path.append(".")

from pydantic import BaseModel, ConfigDict

import app.workflow.graph as graph_mod
from app.workflow.graph import WorkflowGraph, execute_turn
from evaluations.prompt_iterations import run_version
from evaluations.run_evals import new_session

OUT = Path("docs/incident_drill")
TRACE_FILE = Path(os.environ["TRACE_FILE"])
BOOKING_CALL = ["book thyroid test", "9:00 AM", "yes"]


# ---------- trace helpers ----------
def spans_of(trace_id: str) -> List[dict]:
    out: List[dict] = []
    if TRACE_FILE.exists():
        for line in TRACE_FILE.read_text(encoding="utf-8").splitlines():
            if trace_id in line:
                rec = json.loads(line)
                if rec.get("trace_id") == trace_id:
                    out.append(rec)
    return sorted(out, key=lambda r: (r["start"], -r.get("latency_ms", 0)))


def _detail(s: dict) -> str:
    m = s.get("metadata", {})
    keys = ("attempt", "error", "slot", "package_id", "model", "route", "prompt_version", "prompt_tokens",
            "completion_tokens", "prompt_chars", "cost_usd", "mode", "n_sources", "empty", "final_node", "triage")
    return " ".join(f"{k}={m[k]}" for k in keys if k in m and m[k] not in (None, ""))


def render_tree(spans: List[dict]) -> str:
    """Indented span list: a span is a child of the innermost earlier span that fully contains it in time."""
    stack: List[tuple[float, int]] = []
    lines: List[str] = []
    t0 = spans[0]["start"] if spans else 0.0
    for s in spans:
        end = s["start"] + s.get("latency_ms", 0) / 1000
        while stack and s["start"] >= stack[-1][0] - 1e-6:
            stack.pop()
        lines.append(f"{'  ' * len(stack)}{s['name']:<{max(1, 34 - 2 * len(stack))}} {s['kind']:<5} "
                     f"+{(s['start'] - t0) * 1000:7.0f} ms  {s.get('latency_ms', 0):8.1f} ms  {_detail(s)}")
        stack.append((end, len(stack)))
    return "\n".join(lines)


def waterfall_html(spans: List[dict], title: str) -> str:
    if not spans:
        return f"<h3>{escape(title)}</h3><p>no spans</p>"
    t0 = spans[0]["start"]
    total = max((s["start"] - t0) * 1000 + s.get("latency_ms", 0) for s in spans) or 1.0
    rows = ""
    for s in spans:
        left = (s["start"] - t0) * 1000 / total * 100
        width = max(s.get("latency_ms", 0) / total * 100, 0.4)
        failed = bool(s.get("metadata", {}).get("error"))
        cls = "bar err" if failed else f"bar {s['kind']}"
        rows += (f"<tr><td class='n'>{escape(s['name'])}</td><td class='t'><div class='{cls}' "
                 f"style='margin-left:{left:.2f}%;width:{width:.2f}%'></div></td>"
                 f"<td class='d'>{s.get('latency_ms', 0):.0f} ms {escape(_detail(s))}</td></tr>")
    return (f"<h3>{escape(title)}</h3><p class='sub'>trace_id <code>{escape(spans[0]['trace_id'])}</code> "
            f"- {len(spans)} spans - {total:.0f} ms end to end. Red = span with an error.</p>"
            f"<table class='wf'>{rows}</table>")


# ---------- measurements ----------
class BookingRun(BaseModel):
    model_config = ConfigDict(frozen=True)
    calls: int
    booked: int
    handed_off: int
    tool_errors: int
    final_turn_ms_p50: float
    example_trace_id: str


def run_booking_calls(graph: WorkflowGraph, n: int, tag: str) -> BookingRun:
    booked = handed = errors = 0
    final_ms: List[float] = []
    example = ""
    for i in range(n):
        graph.lab_tools._booked.clear()
        graph.lab_tools._bookings.clear()
        s = new_session(f"{tag}{i}")
        for msg in BOOKING_CALL:
            t = time.perf_counter()
            out, s = execute_turn(msg, s, graph=graph)
        final_ms.append((time.perf_counter() - t) * 1000)
        booked += int(bool(s.member.past_bookings))
        handed += int(s.active_node == "node_human_handoff")
        sp = spans_of(s.trace_id)
        errors += sum(1 for x in sp if x["name"] == "tool:book_test" and x["metadata"].get("error"))
        example = example or s.trace_id
    return BookingRun(calls=n, booked=booked, handed_off=handed, tool_errors=errors,
                      final_turn_ms_p50=round(statistics.median(final_ms), 0), example_trace_id=example)

def run_stale_record_calls(graph: WorkflowGraph, n: int, tag: str) -> BookingRun:
    booked = handed = errors = 0
    final_ms: List[float] = []
    example = ""
    for i in range(n):
        graph.lab_tools._booked.clear()
        graph.lab_tools._bookings.clear()
        s = new_session(f"{tag}{i}")
        for j, msg in enumerate(BOOKING_CALL):
            if j == 2 and s.booking_draft.package_id:
                d = s.booking_draft
                graph.lab_tools._booked.add((d.package_id, d.selected_date, d.selected_slot))
            t = time.perf_counter()
            out, s = execute_turn(msg, s, graph=graph)
        final_ms.append((time.perf_counter() - t) * 1000)
        booked += int(bool(s.member.past_bookings))
        handed += int(s.active_node == "node_human_handoff")
        sp = spans_of(s.trace_id)
        errors += sum(1 for x in sp if x["name"] == "tool:book_test" and x["metadata"].get("error"))
        example = example or s.trace_id
    return BookingRun(calls=n, booked=booked, handed_off=handed, tool_errors=errors,
                      final_turn_ms_p50=round(statistics.median(final_ms), 0), example_trace_id=example)

def coach_trace(graph: WorkflowGraph, query: str, tag: str) -> str:
    s = new_session(tag)
    _, s = execute_turn(query, s, graph=graph)
    return s.trace_id

def main(calls: int = 5) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    golden = json.load(open("evaluations/datasets/golden_eval_set.json", encoding="utf-8"))
    graph = WorkflowGraph()
    graph.use_cache = False
    original_prompt = graph_mod.PROMPT_VERSION

    print("== baseline: healthy ==")
    graph.lab_tools.failure_rate = 0.0
    healthy_booking = run_booking_calls(graph, calls, "HB")
    healthy_prompt = run_version(original_prompt, golden, repeats=1)
    healthy_coach_trace = coach_trace(graph, "What yoga helps with stress?", "HC")

    print("== incident A: lab API down ==")
    graph.lab_tools.failure_rate = 1.0
    outage_booking = run_booking_calls(graph, calls, "OB")
    graph.lab_tools.failure_rate = 0.0

    print("== incident B: bad prompt change (coach prompt rolled back to v1) ==")
    bad_prompt = run_version("v1", golden, repeats=1)
    graph_mod.PROMPT_VERSION = "v1"
    bad_coach_trace = coach_trace(graph, "What yoga helps with stress?", "BC")
    graph_mod.PROMPT_VERSION = original_prompt
    
    print("== incident C: stale backend record ==")
    stale_booking = run_stale_record_calls(graph, calls, "SB")

    trees = {"trace_A_outage.txt": spans_of(outage_booking.example_trace_id),
             "trace_baseline_booking.txt": spans_of(healthy_booking.example_trace_id),
             "trace_B_bad_prompt.txt": spans_of(bad_coach_trace),
             "trace_baseline_coach.txt": spans_of(healthy_coach_trace),
             "trace_C_stale_record.txt": spans_of(stale_booking.example_trace_id)}
    for name, sp in trees.items():
        (OUT / name).write_text(render_tree(sp) + "\n", encoding="utf-8")

    def pct(a: int, b: int) -> str:
        return f"{round(100 * a / b)}%"

    diff_a = [("Booking success (booked / calls)", pct(healthy_booking.booked, calls), pct(outage_booking.booked, calls)),
              ("Handed to a care coordinator", pct(healthy_booking.handed_off, calls), pct(outage_booking.handed_off, calls)),
              ("`tool:book_test` spans with an error", str(healthy_booking.tool_errors), str(outage_booking.tool_errors)),
              ("Final booking turn p50 latency", f"{healthy_booking.final_turn_ms_p50:.0f} ms",
               f"{outage_booking.final_turn_ms_p50:.0f} ms")]
               
    diff_c = [("Booking success (booked / calls)", pct(healthy_booking.booked, calls), pct(stale_booking.booked, calls)),
              ("Handed to a care coordinator", pct(healthy_booking.handed_off, calls), pct(stale_booking.handed_off, calls)),
              ("`tool:book_test` spans with an error", str(healthy_booking.tool_errors), str(stale_booking.tool_errors)),
              ("Final booking turn p50 latency", f"{healthy_booking.final_turn_ms_p50:.0f} ms",
               f"{stale_booking.final_turn_ms_p50:.0f} ms")]
               
    f = lambda v, sfx="": "N/A" if v is None else f"{v}{sfx}"  # noqa: E731
    diff_b = [("Faithfulness (LLM judge)", f(healthy_prompt.faithfulness_pct, "%"), f(bad_prompt.faithfulness_pct, "%")),
              ("Lexical groundedness", f(healthy_prompt.lexical_groundedness_pct, "%"), f(bad_prompt.lexical_groundedness_pct, "%")),
              ("Answers citing a source id", f(healthy_prompt.citation_rate_pct, "%"), f(bad_prompt.citation_rate_pct, "%")),
              ("Injection + out-of-scope suite", f"{healthy_prompt.injection_passed}/{healthy_prompt.injection_total}",
               f"{bad_prompt.injection_passed}/{bad_prompt.injection_total}"),
              ("Tokens per turn", f(healthy_prompt.tokens_per_turn), f(bad_prompt.tokens_per_turn))]

    def md_table(title: str, rows: list, bad_label: str) -> str:
        return (f"**{title}**\n\n| Metric | Healthy | {bad_label} |\n|---|---|---|\n"
                + "\n".join(f"| {a} | {b} | {c} |" for a, b, c in rows) + "\n")

    (OUT / "eval_diff.md").write_text(
        md_table("Incident A: lab API down", diff_a, "Incident") + "\n"
        + md_table(f"Incident B: coach prompt rolled back to v1 (healthy = {original_prompt})", diff_b, "Incident (v1)") + "\n"
        + md_table("Incident C: stale backend record", diff_c, "Incident"),
        encoding="utf-8")
    (OUT / "drill_results.json").write_text(json.dumps({
        "healthy_booking": healthy_booking.model_dump(), "outage_booking": outage_booking.model_dump(), "stale_booking": stale_booking.model_dump(),
        "healthy_prompt": healthy_prompt.model_dump(exclude={"audit"}), "bad_prompt": bad_prompt.model_dump(exclude={"audit"}),
        "trace_ids": {"A_outage": outage_booking.example_trace_id, "baseline_booking": healthy_booking.example_trace_id,
                      "B_bad_prompt": bad_coach_trace, "baseline_coach": healthy_coach_trace, "C_stale_record": stale_booking.example_trace_id}},
        indent=2, ensure_ascii=False), encoding="utf-8")

    def html_table(rows: list, bad_label: str) -> str:
        body = "".join(f"<tr><td>{escape(a)}</td><td>{escape(b)}</td><td class='bad'>{escape(c)}</td></tr>" for a, b, c in rows)
        return f"<table class='m'><tr><th>Metric</th><th>Healthy</th><th>{escape(bad_label)}</th></tr>{body}</table>"

    css = ("body{font-family:Segoe UI,Arial,sans-serif;margin:24px;max-width:1100px;color:#1d2433}"
           "h1{font-size:20px}h2{font-size:17px;border-bottom:1px solid #d6dbe6;padding-bottom:4px;margin-top:28px}"
           "h3{font-size:14px;margin:18px 0 2px}.sub{margin:0 0 6px;color:#566;font-size:12px}"
           "table.m{border-collapse:collapse;margin:8px 0}table.m td,table.m th{border:1px solid #cfd6e4;padding:5px 12px;font-size:13px;text-align:left}"
           "td.bad{background:#fdecea;font-weight:600}table.wf{width:100%;border-collapse:collapse;font-size:12px}"
           "td.n{width:230px;font-family:Consolas,monospace;padding:2px 6px;white-space:nowrap}td.t{width:40%;background:#f3f5f9;padding:2px 0}"
           "td.d{padding:2px 8px;color:#445;font-family:Consolas,monospace;font-size:11px}.bar{height:12px;border-radius:2px;background:#4c7bd9}"
           ".bar.root{background:#25314d}.bar.node{background:#4c7bd9}.bar.tool{background:#2f9e8f}.bar.llm{background:#a35bd6}"
           ".bar.err{background:#d93025}code{background:#eef1f7;padding:1px 4px;border-radius:3px}")
    (OUT / "report.html").write_text(
        f"<!doctype html><html><head><meta charset='utf-8'><title>Incident drill</title><style>{css}</style></head><body>"
        "<h1>Saathi Care AI - incident drill</h1>"
        "<h2 id='a'>Incident A: partner lab API down</h2>"
        "<p>Eval output, healthy vs incident (same 3-turn booking call, same code):</p>" + html_table(diff_a, "Lab API down")
        + waterfall_html(trees["trace_A_outage.txt"], "Trace of one failed booking turn (the handoff happens after 3 failed attempts)")
        + waterfall_html(trees["trace_baseline_booking.txt"], "Same turn when healthy (for comparison)")
        + "<h2 id='b'>Incident B: bad prompt change (coach prompt rolled back to v1)</h2>"
        + "<p>Eval output, healthy vs incident (12 golden wellness questions + injection suite):</p>" + html_table(diff_b, "Prompt v1")
        + waterfall_html(trees["trace_B_bad_prompt.txt"], "Trace of one coach turn under the bad prompt (see prompt_version and prompt_chars)")
        + waterfall_html(trees["trace_baseline_coach.txt"], "Same question when healthy")
        + "<h2 id='c'>Incident C: stale backend record</h2>"
        + "<p>Eval output, healthy vs incident (same 3-turn booking call):</p>" + html_table(diff_c, "Stale record")
        + waterfall_html(trees["trace_C_stale_record.txt"], "Trace of one failed booking turn due to stale record (fails fast without retry)")
        + "</body></html>", encoding="utf-8")
    print((OUT / "eval_diff.md").read_text(encoding="utf-8"))
    print("trace ids:", json.dumps(json.load(open(OUT / "drill_results.json"))["trace_ids"], indent=1))


if __name__ == "__main__":
    main()
