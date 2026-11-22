"""Tests the kappa *formula* and the refusal to report it without enough labels (synthetic data, not validation)."""
from evaluations.run_evals import cohens_kappa, judge_agreement, MIN_LABELLED


def test_kappa_formula_known_values():
    assert cohens_kappa(["pass", "fail"], ["pass", "fail"]) == 1.0
    # Classic 2x2 example: po=0.7, pe=0.5 -> kappa=0.4
    a = ["y"] * 20 + ["y"] * 5 + ["n"] * 10 + ["n"] * 15
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert abs(cohens_kappa(a, b) - 0.4) < 1e-9


def test_kappa_refused_with_too_few_labels():
    judged = {f"C{i}": "pass" for i in range(MIN_LABELLED - 1)}
    labels = {k: {"annotator_a": "pass", "annotator_b": "pass"} for k in judged}
    r = judge_agreement(judged, labels)
    assert r["judge_vs_a"] is None and r["human_vs_human"] is None


def test_no_labels_means_na():
    assert judge_agreement({"WG-001": "pass"}, {})["judge_vs_a"] is None


def test_pricing_is_date_aware_and_covers_configured_models():
    from datetime import date
    import yaml
    from app.workflow.model_client import _cost, PRICING
    assert abs(_cost("gemini-3.8-flash", 1_000_000, 1_000_000, date(2026, 12, 31)) - 4.50) < 1e-9
    assert abs(_cost("gemini-3.8-flash", 1_000_000, 1_000_000, date(2027, 1, 1)) - 9.00) < 1e-9
    cfg = yaml.safe_load(open("config/models.yaml", encoding="utf-8"))
    for n in cfg["routing"]["nodes"]:
        for m in (n["default_model"], n.get("fallback_model")):
            if m is None:
                continue
            assert m in PRICING, f"no price for configured model {m}"
        assert "gemini-2.5" not in n["default_model"]
