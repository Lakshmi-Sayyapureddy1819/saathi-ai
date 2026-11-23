import json
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.append(".")
load_dotenv()

from app.grounding.semantic_cache import (
    _BYPASS,
    DEFAULT_THRESHOLD,
    SemanticCache,
    _cosine,
    _embed,
    _jaccard,
    wellness_cache,
)


def main():
    """Evaluates the semantic cache's similarity scores, false-hit rate, and bypass protections."""
    dataset_path = Path("evaluations/datasets/cache_evaluation_set.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        labelled_pairs = json.load(f)

    print("=====================================================================")
    print("               Semantic Cache Evaluation & Audit                     ")
    print("=====================================================================")

    # 1. Inspect Backend and Default Threshold
    wellness_cache.cache.clear()
    current_stats = wellness_cache.stats()
    configured_threshold = current_stats.threshold

    print(f"Active Store:               {current_stats.store}")
    print(f"Embedding Model:            {wellness_cache.namespace.split(':')[-1] if ':' in wellness_cache.namespace else 'gemini-embedding-001'}")
    print(f"Configured Threshold:       {configured_threshold:.2f} (DEFAULT_THRESHOLD={DEFAULT_THRESHOLD:.2f})")
    print(f"Total Labelled Pairs:       {len(labelled_pairs)}")

    # 2. Partition dataset
    same_intent_pairs = [pair for pair in labelled_pairs if pair[2]]
    diff_intent_pairs = [pair for pair in labelled_pairs if not pair[2]]
    bypassed_pairs = [pair for pair in labelled_pairs if _BYPASS.search(pair[0]) or _BYPASS.search(pair[1])]
    generic_positive_pairs = [pair for pair in same_intent_pairs if not (_BYPASS.search(pair[0]) or _BYPASS.search(pair[1]))]

    print(f"  - Positive pairs (paraphrases):        {len(same_intent_pairs)} ({len(generic_positive_pairs)} generic, {len(bypassed_pairs)} member/booking bypass)")
    print(f"  - Negative pairs (different intents):  {len(diff_intent_pairs)}")
    print(f"  - Bypass pairs (member/booking data):   {len(bypassed_pairs)}")
    print("---------------------------------------------------------------------")

    # 3. Compute pairwise similarities
    neg_scores = []
    print("\n[Challenging Negative Pairs & Similarity Scores]")
    for q1, q2, _ in diff_intent_pairs:
        v1 = _embed(q1)
        v2 = _embed(q2)
        score = _cosine(v1, v2) if (v1 is not None and v2 is not None) else _jaccard(q1, q2)
        neg_scores.append((q1, q2, score))

    # Sort descending by score to highlight closest negative pairs
    neg_scores.sort(key=lambda x: x[2], reverse=True)
    for q1, q2, score in neg_scores[:8]:
        status = "FALSE HIT" if score >= configured_threshold else "CORRECT REJECTION"
        print(f"  {score:0.4f} [{status:<17}] \"{q1}\" vs \"{q2}\"")

    max_neg_score = max((s for _, _, s in neg_scores), default=0.0)
    print(f"\nHighest different-intent similarity: {max_neg_score:.4f}")

    # 4. Threshold sweep analysis
    test_thresholds = [0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.95]
    print("\n---------------------------------------------------------------------")
    print("Threshold Tradeoff Sweep (Why 0.88 was chosen):")
    print(" Threshold | False Hits | False-Hit Rate | Generic Paraphrase Hits | Tradeoff Note")
    print("-----------+------------+----------------+-------------------------+----------------------------------")

    for t in test_thresholds:
        bad = sum(1 for _, _, s in neg_scores if s >= t)
        f_rate = bad / len(diff_intent_pairs) if diff_intent_pairs else 0.0

        # Generic positive hits
        temp_cache = SemanticCache(threshold=t)
        pos_hits = 0
        for q1, q2, _ in generic_positive_pairs:
            temp_cache.set(q1, "test answer", sync=True)
            if temp_cache.get(q2) is not None:
                pos_hits += 1

        p_rate = pos_hits / len(generic_positive_pairs) if generic_positive_pairs else 0.0
        note = "Unsafe (medical false hits)" if bad > 0 else ("Conservative (0% false hits)" if t == 0.88 else "Zero false hits")
        print(f"   {t:0.2f}    |     {bad:2d}/{len(diff_intent_pairs):2d}    |     {f_rate*100:5.1f}%    |          {pos_hits:2d}/{len(generic_positive_pairs):2d} ({p_rate*100:4.1f}%)    | {note}")

    # 5. False hit rate at active threshold
    false_hit_rate = wellness_cache.evaluate_false_hits(labelled_pairs)
    print("\n---------------------------------------------------------------------")
    print(f"Measured False-Hit Rate at Threshold {configured_threshold:.2f}: {false_hit_rate:.2%}")

    # 6. Verification of Member-Data and Booking Protection
    print("\n[Privacy & Data Boundary Verification]")
    member_booking_queries = [
        "I want to book a blood test",
        "Schedule a blood test for me",
        "What slots are available tomorrow?",
        "Are there appointments tomorrow morning?",
        "Show my past bookings",
        "Where can I see my booking history?",
        "Check my health profile",
        "Can I see my member profile details?",
        "Show my lab report",
        "Cancel my booking for tomorrow",
        "What is the status of LP_01 package?",
    ]
    bypass_violations = 0
    for q in member_booking_queries:
        wellness_cache.set(q, "Sensitive answer", sync=True)
        if wellness_cache.get(q) is not None:
            print(f"  VIOLATION: Query was cached/served: '{q}'")
            bypass_violations += 1
        else:
            print(f"  [BYPASS VERIFIED] '{q}' -> blocked from cache")

    print(f"\nMember / booking queries evaluated: {len(member_booking_queries)}")
    print(f"Cached or served:                     {bypass_violations} (MUST be 0)")
    assert bypass_violations == 0, "Security violation: member or booking query was stored/served in cache!"
    print("Verification: Member data and bookings are NEVER cached or served.")
    print("=====================================================================")


if __name__ == "__main__":
    main()
