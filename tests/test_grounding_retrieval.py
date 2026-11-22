"""Retrieval regressions found while auditing groundedness (see EVALS.md)."""
from app.grounding.engine import GroundingEngine, HINGLISH_EXPANSION, _stem
from evaluations.run_evals import Claim, Faithfulness, faithfulness, groundedness

E = GroundingEngine()


def _src(q):
    return E.mode_a_retrieval(q).sources


def test_stemming_connects_relax_to_relaxation_docs():
    assert _src("How to relax?") == ["PROG_Y_004", "PROG_Y_005"]      # Shavasana, Balasana (was: nothing)
    assert _stem("relax") == _stem("relaxation") and _stem("digestion") == _stem("digestive")


def test_hinglish_heat_query_finds_cooling_breath_not_a_heating_one():
    assert _src("garmi ke liye pranayama?") == ["PROG_P_004"]          # Sheetali; Kapalbhati (heating) excluded


def test_weak_runner_up_is_dropped():
    assert _src("anulom vilom ke kya fayde hain?") == ["PROG_P_001"]  # hydration doc only shared 'fayde'
    assert _src("paani peene ke fayde") == ["PROG_D_003"]


def test_strong_second_hit_is_kept_and_unrelated_query_is_empty():
    assert len(_src("yoga for stress")) == 2
    assert E.mode_a_retrieval("tell me a joke").empty


def test_expansion_lexicon_targets_exist_in_library_vocabulary():
    # Every expansion should be a real word in the library, otherwise it is dead weight.
    vocab = " ".join(p["title"] + " " + p["content"] + " " + " ".join(p["tags"]) for p in E.programs).lower()
    dead = [w for ws in HINGLISH_EXPANSION.values() for w in ws if _stem(w) not in {_stem(t) for t in vocab.split()}]
    assert len(dead) <= len(sum(HINGLISH_EXPANSION.values(), [])) // 3, f"too many dead expansions: {dead}"


def test_faithfulness_score_math_and_no_fake_score_without_llm():
    f = Faithfulness(claims=[Claim(claim="a", supported=True), Claim(claim="b", supported=False)])
    assert f.score == 0.5 and f.unsupported == ["b"]
    assert Faithfulness(claims=[]).score == 1.0
    assert faithfulness("some answer", "some context") is None         # keys are blank in tests -> mock -> None


def test_strict_lexical_proxy_definition_unchanged():
    assert groundedness("stretches hamstrings", "It stretches the hamstrings and hips") == 1.0
    assert groundedness("khayein poha", "eat poha") < 1.0               # Hinglish word is not in an English context


def test_judge_control_is_na_without_llm():
    from evaluations.run_evals import faithfulness_judge_control
    assert faithfulness_judge_control(E) is None
