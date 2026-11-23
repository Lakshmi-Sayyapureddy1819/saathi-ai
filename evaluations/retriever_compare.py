"""Compare retrieval backends (lexical vs dense embeddings) on the same labelled queries, and pick the embedding
off-topic threshold from data instead of guessing.

Run from the project root:  python -m evaluations.retriever_compare
Needs GEMINI_API_KEY for the embedding rows (otherwise they are reported as N/A). Costs a few embedding calls
(one per library document plus one per query); writes evaluations/snapshots/retriever_compare_<date>.md.

Labels: `on_topic` / `off_topic` from deterministic_eval_set.json, plus the golden wellness questions (each must retrieve
something). 'Hit' means a non-empty result; there are no per-query gold doc ids, so this measures coverage and
off-topic rejection, not ranking precision.
"""
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional

sys.path.append(".")

from app.workflow import graph as _graph  # noqa: F401,E402  (loads .env the same way the app does)
from app.grounding.retriever import EmbeddingRetriever, LexicalRetriever  # noqa: E402
from app.grounding.semantic_cache import _embed  # noqa: E402

THRESHOLDS = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75]


def _queries() -> Dict[str, List[str]]:
    det = json.loads(Path("evaluations/datasets/deterministic_eval_set.json").read_text(encoding="utf-8"))
    golden = json.loads(Path("evaluations/datasets/golden_eval_set.json").read_text(encoding="utf-8"))
    wellness = [c["user_input"] for c in golden if c["category"] == "wellness_guidance"]
    return {"on_topic": list(dict.fromkeys(det["on_topic"] + wellness)), "off_topic": det["off_topic"]}


def main() -> None:
    programs = json.loads(Path("data/programs.json").read_text(encoding="utf-8"))
    q = _queries()
    cache: Dict[str, Optional[List[float]]] = {}

    def embed(t: str) -> Optional[List[float]]:
        if t not in cache:
            cache[t] = _embed(t)
        return cache[t]

    lines = ["# Retriever comparison (lexical vs embedding)", "",
             f"Run {date.today()}. on-topic n={len(q['on_topic'])}, off-topic n={len(q['off_topic'])}. "
             "Hit = non-empty result. Small labelled sets: use as direction, not as a benchmark.", "",
             "| Backend | On-topic answered | Off-topic wrongly answered |", "|---|---|---|"]
    lex = LexicalRetriever(programs)
    on = sum(bool(lex.search(x)) for x in q["on_topic"])
    off = sum(bool(lex.search(x)) for x in q["off_topic"])
    lines.append(f"| lexical | {on}/{len(q['on_topic'])} | {off}/{len(q['off_topic'])} |")

    if not os.getenv("GEMINI_API_KEY") or embed("probe") is None:
        lines.append("| embedding | N/A (no working GEMINI_API_KEY) | N/A |")
    else:
        best = None
        for th in THRESHOLDS:
            r = EmbeddingRetriever(programs, embed, fallback=lex, min_score=th)
            on = sum(bool(r.search(x)) for x in q["on_topic"])
            off = sum(bool(r.search(x)) for x in q["off_topic"])
            lines.append(f"| embedding, min_score={th} | {on}/{len(q['on_topic'])} | {off}/{len(q['off_topic'])} |")
            score = (on - len(q["on_topic"])) - 2 * off  # a wrong answer costs twice a missed one
            if best is None or score > best[0]:
                best = (score, th)
        lines += ["", f"Best threshold on this set (off-topic answers weighted 2x): **{best[1]}**. "
                      "Set EMBED_RETRIEVAL_MIN_SCORE to this value when RETRIEVER=embedding."]
    out = "\n".join(lines) + "\n"
    print(out)
    snap = Path("evaluations/snapshots")
    snap.mkdir(parents=True, exist_ok=True)
    (snap / f"retriever_compare_{date.today()}.md").write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
