"""The larger offline eval must keep passing, and its confidence-bound maths must match the figures in EVALS.md."""
import pytest

from evaluations import deterministic_eval as de


def test_bounds_match_the_small_sample_figures_quoted_in_evals_md():
    assert de.upper_bound(0, 4) == pytest.approx(0.527, abs=0.002)    # "up to ~53%" for 0 wrong in n=4
    assert de.lower_bound(5, 5) == pytest.approx(0.549, abs=0.002)    # "as low as ~55%" for 5/5
    assert de.lower_bound(8, 8) == pytest.approx(0.688, abs=0.002)    # "~69%" for 8/8
    assert de.lower_bound(0, 10) == 0.0 and de.upper_bound(10, 10) == 1.0


def test_every_deterministic_metric_meets_its_target():
    metrics = de.run()
    by_name = {m.name: m for m in metrics}
    assert len(metrics) == 8
    for m in metrics:
        assert not m.failures, f"{m.name}: {m.failures}"
    assert by_name["Red-flag recall (core)"].n >= 25
    assert by_name["Wrong-booking rate"].n >= 100
    assert by_name["Chaos recovery (handoff on outage)"].n >= 50
