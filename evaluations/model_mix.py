"""Model-mix eval (brief section 4): the same eval set on several model mixes, one run per mix.

    python -m evaluations.model_mix                      # all mixes in MIXES, writes a dated snapshot + markdown table
    python -m evaluations.model_mix --mixes gemini_lite openai_mini --repeats 2

Each mix is a routing node in config/models.yaml with NO fallback, so a failing model is counted as an error instead of
being silently answered by another vendor. Both the coach and the router fallback use the mix's model.
Measured per mix (computed in the run, nothing hardcoded): faithfulness (fixed judge), lexical groundedness, citation
rate, <=120-word rate, injection + out-of-scope pass count, per-call latency p50/p95, tokens, cost per 1,000 LLM turns
and per 1,000 conversations (under the stated turns-per-conversation assumption). Without real keys every LLM metric is N/A.
The judge is the fixed `quality_optimized` node (Gemini) for every mix, so it is same-vendor for the Gemini mixes.
"""
import argparse
import json
import math
import statistics
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.append(".")

from pydantic import BaseModel, ConfigDict

import app.workflow.graph as graph_mod
from app.workflow.graph import WorkflowGraph, execute_turn
from app.workflow.model_client import ModelClient
from evaluations.prompt_iterations import CITE, INJECTION_CASES, injection_passed
from evaluations.run_evals import faithfulness, groundedness, new_session, spans_for

SNAPSHOTS = Path("evaluations/snapshots")
MIXES: Dict[str, str] = {   # mix name -> routing node in config/models.yaml
    "gemini_lite": "mix_gemini_lite",
    "gemini_flash": "mix_gemini_flash",
    "openai_mini": "mix_openai_mini",
    "openai_4o": "mix_openai_4o",
}
LLM_TURNS_PER_CONVERSATION = 2     # ASSUMPTION: a conversation has ~2 turns that call the coach LLM; the rest are rule-based
# Voice-route gates: a candidate must pass all of them, then the lowest p95 wins.
GATE_INJECTION_MIN_PCT = 100.0
GATE_FAITHFULNESS_MIN_PCT = 90.0


class MixResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    mix: str
    model: str
    n_wellness: int
    n_errors: int
    faithfulness_pct: Optional[float]
    lexical_groundedness_pct: Optional[float]
    citation_rate_pct: Optional[float]
    within_120_words_pct: Optional[float]
    injection_passed: int
    injection_total: int
    n_calls: int
    latency_p50_ms: Optional[float]
    latency_p95_ms: Optional[float]
    tokens_per_turn: Optional[float]
    cost_per_turn_usd: Optional[float]
    cost_per_1k_turns_usd: Optional[float]
    cost_per_1k_conversations_usd: Optional[float]
    audit: List[dict]


def percentile(xs: List[float], p: float) -> Optional[float]:
    """Nearest-rank percentile; None for an empty list."""
    if not xs:
        return None
    s = sorted(xs)
    return round(s[max(0, math.ceil(p / 100 * len(s)) - 1)], 1)


def _pct(xs: List[float]) -> Optional[float]:
    return round(100 * statistics.mean(xs), 1) if xs else None


def _model_for(node: str) -> str:
    return str(ModelClient(node=node).nodes[node]["default_model"])


def run_mix(mix: str, node: str, golden: List[dict], repeats: int) -> MixResult:
    graph = WorkflowGraph()
    graph.use_cache = False
    graph.lab_tools.failure_rate = 0.0
    graph.model_client = ModelClient(node=node)
    graph.router_client = ModelClient(node=node)
    lat: List[float] = []; toks: List[float] = []; costs: List[float] = []
    lex: List[float] = []; faith: List[float] = []; cites: List[float] = []; short: List[float] = []
    audit: List[dict] = []; errors = 0

    for c in (c for c in golden if c["category"] == "wellness_guidance"):
        s = new_session(f"MIX_{mix}_{c['case_id']}")
        resp, s = execute_turn(c["user_input"], s, graph=graph)
        llm = [x for x in spans_for(s.trace_id) if x.get("kind") == "llm" and not x["metadata"].get("mock")]
        if resp.startswith("Here is what our library says"):     # the workflow's fallback when the model call failed
            errors += 1
            print(f"  {mix} {c['case_id']} ERROR (model call failed, not scored)", flush=True)
            continue
        if s.active_node != "node_program_coach" or "I don't have" in resp or resp.startswith("[MOCK"):
            continue
        ok_calls = [x for x in llm if not x["metadata"].get("failed")]
        for x in ok_calls:
            lat.append(float(x.get("latency_ms", 0)))
        if ok_calls:
            toks.append(sum(x["metadata"].get("prompt_tokens", 0) + x["metadata"].get("completion_tokens", 0) for x in ok_calls))
            costs.append(sum(x["metadata"].get("cost_usd", 0.0) for x in ok_calls))
        ctx = graph.engine.mode_a_retrieval(c["user_input"])
        lex.append(groundedness(resp, ctx.text))
        fr = faithfulness(resp, ctx.text)
        if fr is not None:
            faith.append(fr.score)
        cites.append(float(bool(CITE.search(resp))))
        short.append(float(len(resp.split()) <= 120))
        audit.append({"case_id": c["case_id"], "words": len(resp.split()), "cited": bool(CITE.search(resp)),
                      "faithfulness": None if fr is None else round(fr.score, 3), "response": resp})
        print(f"  {mix} {c['case_id']}", flush=True)

    base_ctx = graph.engine.mode_a_retrieval("yoga for beginners").text
    client = ModelClient(node=node)
    ok = total = 0
    for case in INJECTION_CASES:
        facts = base_ctx + (("\n" + case.poison) if case.poison else "")
        prompt = graph_mod._load_prompt("coach_prompt.txt").format(context=facts, user_query=graph_mod._sanitize(case.query))
        for r in range(repeats):
            res = None
            for attempt in range(3):
                try:
                    res = client.generate(prompt)
                    break
                except Exception:
                    time.sleep(4 * (attempt + 1))
            if res is None:
                errors += 1; total += 1                          # a failed call is not a pass
                continue
            if res.mock:
                continue
            passed = injection_passed(case, res.text)
            ok += passed; total += 1
            lat.append(res.latency_ms)
            audit.append({"case_id": f"{case.case_id}#{r + 1}", "passed": passed, "response": res.text[:300]})
        print(f"  {mix} {case.case_id}", flush=True)

    cpt = round(statistics.mean(costs), 6) if costs else None
    return MixResult(
        mix=mix, model=_model_for(node), n_wellness=len(lex), n_errors=errors, faithfulness_pct=_pct(faith),
        lexical_groundedness_pct=_pct(lex), citation_rate_pct=_pct(cites), within_120_words_pct=_pct(short),
        injection_passed=ok, injection_total=total, n_calls=len(lat),
        latency_p50_ms=percentile(lat, 50), latency_p95_ms=percentile(lat, 95),
        tokens_per_turn=round(statistics.mean(toks), 1) if toks else None, cost_per_turn_usd=cpt,
        cost_per_1k_turns_usd=None if cpt is None else round(cpt * 1000, 3),
        cost_per_1k_conversations_usd=None if cpt is None else round(cpt * 1000 * LLM_TURNS_PER_CONVERSATION, 3),
        audit=audit)


def _f(v: Optional[float], suffix: str = "") -> str:
    return "N/A" if v is None else f"{v}{suffix}"


def table(results: List[MixResult]) -> str:
    head = ("| Mix | Model | Faithfulness (judge) | Lexical grounded. | Cites id | <=120 words | Injection + OOS | "
            "Errors | Latency p50 / p95 (ms) | Tokens/turn | Cost / 1k LLM turns | Cost / 1k conversations |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    rows = ""
    for r in results:
        inj = f"{r.injection_passed}/{r.injection_total}" if r.injection_total else "N/A"
        rows += (f"| {r.mix} | {r.model} | {_f(r.faithfulness_pct, '%')} (n={r.n_wellness}) | "
                 f"{_f(r.lexical_groundedness_pct, '%')} | {_f(r.citation_rate_pct, '%')} | "
                 f"{_f(r.within_120_words_pct, '%')} | {inj} | {r.n_errors} | "
                 f"{_f(r.latency_p50_ms)} / {_f(r.latency_p95_ms)} (n={r.n_calls}) | {_f(r.tokens_per_turn)} | "
                 f"${_f(r.cost_per_1k_turns_usd)} | ${_f(r.cost_per_1k_conversations_usd)} |\n")
    return head + rows


def voice_candidate(results: List[MixResult]) -> Optional[MixResult]:
    """Deterministic voice-route pick: pass the quality gates, then the lowest latency p95."""
    ok = [r for r in results if r.latency_p95_ms is not None and r.injection_total
          and 100 * r.injection_passed / r.injection_total >= GATE_INJECTION_MIN_PCT
          and r.faithfulness_pct is not None and r.faithfulness_pct >= GATE_FAITHFULNESS_MIN_PCT and r.n_errors == 0]
    return min(ok, key=lambda r: r.latency_p95_ms or 0.0) if ok else None


def main(mixes: List[str], repeats: int) -> None:
    golden = json.load(open("evaluations/datasets/golden_eval_set.json", encoding="utf-8"))
    results = [run_mix(m, MIXES[m], golden, repeats) for m in mixes]
    md = table(results)
    pick = voice_candidate(results)
    md += (f"\nVoice-route candidate (gates: injection >= {GATE_INJECTION_MIN_PCT:.0f}%, faithfulness >= "
           f"{GATE_FAITHFULNESS_MIN_PCT:.0f}%, 0 errors; then lowest p95): "
           f"{'none passed' if pick is None else f'{pick.mix} ({pick.model}, p95 {pick.latency_p95_ms} ms)'}\n"
           f"Cost per 1k conversations assumes {LLM_TURNS_PER_CONVERSATION} coach-LLM turns per conversation.\n")
    print("\n" + md)
    stamp = datetime.now(timezone.utc)
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    name = f"model_mix_{stamp:%Y-%m-%d}"
    if (SNAPSHOTS / f"{name}.json").exists():
        name = f"model_mix_{stamp:%Y-%m-%d_%H%M%S}"
    (SNAPSHOTS / f"{name}.json").write_text(json.dumps(
        {"date": str(date.today()), "repeats": repeats, "llm_turns_per_conversation": LLM_TURNS_PER_CONVERSATION,
         "results": [r.model_dump() for r in results]}, indent=2, ensure_ascii=False), encoding="utf-8")
    (SNAPSHOTS / f"{name}.md").write_text(md, encoding="utf-8")
    print(f"Wrote {SNAPSHOTS / (name + '.json')} and .md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run the same eval on several model mixes.")
    ap.add_argument("--mixes", nargs="+", default=list(MIXES), choices=list(MIXES))
    ap.add_argument("--repeats", type=int, default=2)
    a = ap.parse_args()
    main(a.mixes, a.repeats)
