"""The labelling tool records exactly what is typed, is resumable, and never shows or calls the judge.
(Scripted answers here exercise the tool; they are not calibration labels.)"""
import json
from pathlib import Path

from evaluations import label_calibration as lc
from evaluations.run_evals import judge_agreement


def _copy_labels(tmp_path: Path) -> Path:
    """A blank template with the real case ids, so the tests do not depend on the real (hand-labelled) file."""
    real = json.loads(Path(lc.LABEL_FILE).read_text(encoding="utf-8"))
    blank = {"_instructions": real.get("_instructions", ""),
             "labels": {cid: {"annotator_a": None, "annotator_b": None} for cid in real["labels"]}}
    p = tmp_path / "labels.json"
    p.write_text(json.dumps(blank), encoding="utf-8")
    return p


def _run(answers, p, annotator="a"):
    it = iter(answers)
    shown = []
    n = lc.label_cases(annotator, label_path=p, ask=lambda _prompt: next(it), out=shown.append)
    return n, "\n".join(shown)


def test_records_typed_labels_only_for_chosen_annotator(tmp_path):
    p = _copy_labels(tmp_path)
    n, _ = _run(["p", "m", "f", "q"], p)
    labs = json.loads(p.read_text(encoding="utf-8"))["labels"]
    vals = [v["annotator_a"] for v in labs.values()]
    assert n == 3 and vals[:3] == ["pass", "marginal", "fail"] and all(v is None for v in vals[3:])
    assert all(v["annotator_b"] is None for v in labs.values())


def test_resume_keeps_existing_and_never_mentions_judge(tmp_path):
    p = _copy_labels(tmp_path)
    _run(["p", "q"], p)
    n, shown = _run([""] + ["f"] * 14, p)           # Enter keeps the first label, then label the rest
    labs = json.loads(p.read_text(encoding="utf-8"))["labels"]
    assert n == 15 and list(labs.values())[0]["annotator_a"] == "pass"
    assert "judge" not in shown.lower().replace("judge's output", "")  # no verdicts shown to the annotator


def test_single_annotator_gives_judge_kappa_but_not_inter_annotator():
    ids = [f"C{i}" for i in range(15)]
    judged = {c: "pass" for c in ids}
    labels = {c: {"annotator_a": "pass", "annotator_b": None} for c in ids}
    r = judge_agreement(judged, labels)
    assert r["judge_vs_a"] is not None and r["human_vs_human"] is None and r["judge_vs_b"] is None
