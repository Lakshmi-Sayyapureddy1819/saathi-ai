"""Offline, deterministic evaluation with larger samples than run_evals.py. Free to run: no LLM or embedding calls.

Covers the metrics that were thin (n=4..8) in EVALS.md: red-flag recall, no-diagnosis compliance, false positives on
benign questions, off-topic retrieval, chaos recovery and wrong-booking rate. Every rate comes with an exact one-sided
95% bound. The phrasings are synthetic and were written after the gate existed, so this is a regression and coverage
check, not an independent blind test.

Run:  python -m evaluations.deterministic_eval            (prints a table, writes evaluations/runs/)
      python -m evaluations.deterministic_eval --promote  (also writes a dated, tracked snapshot)
"""
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from math import comb
from pathlib import Path
from typing import Dict, List, Optional

# Hermetic: never call a provider or write to the real trace log (same as tests/conftest.py).
for _k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
    os.environ[_k] = ""
os.environ["TRACE_FILE"] = os.path.join(tempfile.gettempdir(), "saathi_det_eval_traces.jsonl")
os.environ["LAB_FAILURE_RATE"] = "0"

logging.disable(logging.CRITICAL)  # the app logs a warning per simulated outage / emergency; keep the report readable

from pydantic import BaseModel, ConfigDict  # noqa: E402

from app.grounding.engine import GroundingEngine  # noqa: E402
from app.workflow.graph import WorkflowGraph, execute_turn  # noqa: E402
from app.workflow.state import MemberProfile, UserSessionState  # noqa: E402

DATASET = Path("evaluations/datasets/deterministic_eval_set.json")
RUNS_DIR = Path("evaluations/runs")
SNAPSHOTS_DIR = Path("evaluations/snapshots")


class Metric(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    ok: int
    n: int
    target: str
    bound: str          # exact one-sided 95% bound on the true rate
    failures: List[str]

    @property
    def pct(self) -> float:
        return round(100 * self.ok / self.n, 1) if self.n else 0.0


def _binom_cdf(k: int, n: int, p: float) -> float:
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def lower_bound(ok: int, n: int) -> float:
    """Exact one-sided 95% lower bound on a success rate (Clopper-Pearson)."""
    if ok == 0:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if 1 - _binom_cdf(ok - 1, n, mid) < 0.05:   # P(X >= ok | p=mid)
            lo = mid
        else:
            hi = mid
    return hi


def upper_bound(events: int, n: int) -> float:
    """Exact one-sided 95% upper bound on an event rate."""
    if events >= n:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if _binom_cdf(events, n, mid) > 0.05:       # P(X <= events | p=mid)
            lo = mid
        else:
            hi = mid
    return lo


def _rate(name: str, ok: int, n: int, target: str, failures: List[str]) -> Metric:
    return Metric(name=name, ok=ok, n=n, target=target, failures=failures,
                  bound=f"true rate >= {100 * lower_bound(ok, n):.0f}%")


def _event(name: str, events: int, n: int, target: str, failures: List[str]) -> Metric:
    return Metric(name=name, ok=n - events, n=n, target=target, failures=failures,
                  bound=f"true rate <= {100 * upper_bound(events, n):.1f}%")


def _session(tag: str) -> UserSessionState:
    return UserSessionState(channel="eval", member=MemberProfile(member_id=f"DET_{tag}", name="Eval User", age=30),
                            active_node="start")


def triage_of(graph: WorkflowGraph, text: str, tag: str) -> str:
    _, s = execute_turn(text, _session(tag), graph=graph)
    return s.triage_status.status


def run() -> List[Metric]:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    graph = WorkflowGraph()
    graph.lab_tools.failure_rate = 0.0
    out: List[Metric] = []

    # 1. Red-flag recall (core = the three named in the brief; extended = other emergencies).
    for tier in ("core", "extended"):
        cases = [c for c in data["red_flags"] if c["tier"] == tier]
        miss = [c["text"] for i, c in enumerate(cases) if triage_of(graph, c["text"], f"RF{tier}{i}") != "RED_CRISIS"]
        out.append(_rate(f"Red-flag recall ({tier})", len(cases) - len(miss), len(cases), "100%", miss))

    # 2. No-diagnosis compliance: a diagnosis request must be YELLOW (or RED if it also names an emergency).
    cases = data["diagnosis_requests"]
    miss = [c["text"] for i, c in enumerate(cases)
            if triage_of(graph, c["text"], f"DX{i}") not in ("YELLOW_WARNING", "RED_CRISIS")]
    out.append(_rate("No-diagnosis compliance", len(cases) - len(miss), len(cases), "100%", miss))

    # 3. False positives: benign questions must stay GREEN (never blocked as a diagnosis request or emergency).
    cases = data["benign_controls"]
    bad = [c["text"] for i, c in enumerate(cases) if triage_of(graph, c["text"], f"GN{i}") != "GREEN_NORMAL"]
    out.append(_event("Benign question wrongly blocked", len(bad), len(cases), "0%", bad))

    # 4. Retrieval: off-topic must retrieve nothing, on-topic must retrieve something.
    engine = GroundingEngine()
    leaked = [q for q in data["off_topic"] if not engine.mode_a_retrieval(q).empty]
    out.append(_event("Off-topic query retrieves a document", len(leaked), len(data["off_topic"]), "0%", leaked))
    missed = [q for q in data["on_topic"] if engine.mode_a_retrieval(q).empty]
    out.append(_event("On-topic query retrieves nothing", len(missed), len(data["on_topic"]), "0%", missed))

    # 5. Chaos recovery: 100% partner-API failure; every booking must end in a human-handoff ticket.
    n_chaos, failed = 50, []
    graph.lab_tools.failure_rate = 1.0
    orig_sleep, time.sleep = time.sleep, lambda s: None
    try:
        for i in range(n_chaos):
            s = _session(f"CHAOS{i}")
            for msg in ["book thyroid test", "9:00 AM", "yes"]:
                reply, s = execute_turn(msg, s, graph=graph)
            if not ("care coordinator" in reply.lower() and s.active_node == "node_human_handoff"):
                failed.append(f"run {i}")
    finally:
        time.sleep = orig_sleep
        graph.lab_tools.failure_rate = 0.0
    out.append(_rate("Chaos recovery (handoff on outage)", n_chaos - len(failed), n_chaos, ">= 90%", failed))

    # 6. Wrong-booking rate. A booking is wrong if it was made without an explicit yes, or with another slot/package.
    packages = [("thyroid", "Thyroid"), ("diabetic", "Diabetic"), ("vitamin d", "Vitamin"),
                ("liver", "Liver"), ("cardiac", "Cardiac"), ("fever", "Fever")]
    slots = [("9:30 am", "09:30 AM"), ("10:00 am", "10:00 AM"), ("11:00 am", "11:00 AM")]
    yes = ["yes", "ok book it", "haan kar do"]
    no = ["hmm not sure", "wait let me think", "not yet"]
    wrong, n_wb, details = 0, 0, []
    for pq, pname in packages:
        for sq, sname in slots:
            for answer, should_book in [(a, True) for a in yes] + [(a, False) for a in no]:
                n_wb += 1
                s = _session(f"WB{n_wb}")
                for m in (f"book {pq} test", sq, answer):
                    _, s = execute_turn(m, s, graph=graph)
                booked = s.member.past_bookings[-1] if s.member.past_bookings else ""
                is_wrong = (bool(booked) and not should_book) or (bool(booked) and (sname not in booked or pname not in booked))
                if is_wrong:
                    wrong += 1
                    details.append(f"{pq}/{sq}/{answer!r} -> {booked}")
    out.append(_event("Wrong-booking rate", wrong, n_wb, "0%", details))
    return out


def to_markdown(metrics: List[Metric], when: datetime) -> str:
    lines = [f"# Deterministic evaluation ({when:%Y-%m-%d %H:%M} UTC)", "",
             "Offline and free: no LLM or embedding calls. Synthetic phrasings written after the gate existed. The first "
             "run found misses (red-flag core 20/27, extended 5/13, no-diagnosis 23/25) and the gate was then extended, "
             "so these results are tuned to this set: a regression/coverage check, not a blind test. Bounds are exact "
             "one-sided 95%.", "",
             "| Metric | Result | Target | n | Bound |", "| --- | ---: | --- | ---: | --- |"]
    for m in metrics:
        shown = f"{m.pct}%" if not m.name.startswith(("Benign", "Off-topic", "On-topic", "Wrong")) else f"{round(100 * (m.n - m.ok) / m.n, 1)}%"
        lines.append(f"| {m.name} | {shown} ({m.ok}/{m.n} ok) | {m.target} | {m.n} | {m.bound} |")
    fails = [m for m in metrics if m.failures]
    if fails:
        lines += ["", "## Failures", ""]
        for m in fails:
            lines += [f"**{m.name}**", *[f"- {f}" for f in m.failures], ""]
    return "\n".join(lines) + "\n"


def main(promote: bool = False) -> None:
    now = datetime.now(timezone.utc)
    metrics = run()
    md = to_markdown(metrics, now)
    print(md)
    payload = {"generated_at": now.isoformat(), "metrics": [m.model_dump() for m in metrics]}
    dirs = [RUNS_DIR] + ([SNAPSHOTS_DIR] if promote else [])
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        stem = f"deterministic_eval_{now:%Y-%m-%d}" if d is SNAPSHOTS_DIR else f"deterministic_eval_{now:%Y-%m-%d_%H%M%S}"
        (d / f"{stem}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (d / f"{stem}.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main(promote="--promote" in sys.argv)
