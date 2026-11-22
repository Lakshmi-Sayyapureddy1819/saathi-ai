"""Evaluation output policy: normal runs must not touch tracked files; promotion adds dated evidence, never replaces it."""
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import evaluations.run_evals as ev

RESULTS = {"rows": [["Metric", "1%", ">= 1%", "n=1"]], "ab": {}, "groundedness_audit": [], "raw": []}
BODY = "## Metrics\n\nbody\n"


def _now(h=2, m=30, s=0):
    return datetime(2026, 11, 22, h, m, s, tzinfo=timezone.utc)


def _tree(root: Path):
    return sorted(str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*") if p.is_file())


def test_default_run_writes_only_under_ignored_runs_dir(tmp_path):
    written = ev.write_outputs(RESULTS, BODY, promote=False, now=_now(), root=tmp_path)
    files = _tree(tmp_path)
    assert files == ["evaluations/runs/20261122T023000Z/EVALS.md", "evaluations/runs/20261122T023000Z/eval_results.json"]
    assert not (tmp_path / "EVALS.md").exists() and not (tmp_path / "evaluations/snapshots").exists()
    assert len(written) == 2
    assert "untracked" in (tmp_path / files[0]).read_text(encoding="utf-8")
    assert json.loads((tmp_path / files[1]).read_text(encoding="utf-8")) == RESULTS


def test_promote_publishes_report_and_adds_a_dated_snapshot(tmp_path):
    ev.write_outputs(RESULTS, BODY, promote=True, now=_now(), root=tmp_path)
    snap = tmp_path / "evaluations/snapshots/eval_results_2026-11-22.json"
    assert snap.exists() and json.loads(snap.read_text(encoding="utf-8")) == RESULTS
    report = (tmp_path / "EVALS.md").read_text(encoding="utf-8")
    assert "eval_results_2026-11-22.json" in report and report.endswith(BODY)


def test_promote_never_overwrites_an_existing_snapshot(tmp_path):
    ev.write_outputs(RESULTS, BODY, promote=True, now=_now(2, 30, 0), root=tmp_path)
    first = tmp_path / "evaluations/snapshots/eval_results_2026-11-22.json"
    before = first.read_bytes()
    newer = dict(RESULTS, rows=[["Metric", "2%", ">= 1%", "n=1"]])
    ev.write_outputs(newer, BODY, promote=True, now=_now(9, 5, 7), root=tmp_path)
    assert first.read_bytes() == before                                              # earlier evidence untouched
    extra = sorted(p.name for p in first.parent.iterdir() if p.name != first.name)
    assert extra == ["eval_results_2026-11-22_090507.json"]                           # added, not replaced


def test_main_exposes_an_explicit_promote_flag_defaulting_to_off():
    assert inspect.signature(ev.main).parameters["promote"].default is False
    assert "--promote" in inspect.getsource(ev)


def test_runs_dir_is_git_ignored():
    assert "evaluations/runs/" in Path(".gitignore").read_text(encoding="utf-8").splitlines()


# ---- the tracked snapshot is real, valid, and consistent with the tracked report ----
def test_tracked_snapshot_is_valid_and_matches_evals_md():
    md = Path("EVALS.md").read_text(encoding="utf-8")
    snap = sorted(Path("evaluations/snapshots").glob("eval_results_*.json"))[-1]      # the latest promoted snapshot
    d = json.loads(snap.read_text(encoding="utf-8"))
    assert sorted(d) == ["ab", "groundedness_audit", "raw", "rows", "voice"] and len(d["raw"]) == 55
    assert snap.name in md                                                            # the report points at its evidence
    mismatched = [r[0] for r in d["rows"] if f"| {r[0]} | {r[1]} |" not in md]
    assert not mismatched, f"EVALS.md disagrees with the snapshot for: {mismatched}"


def test_no_stale_duplicate_results_file_is_left_at_the_old_path():
    assert not Path("evaluations/eval_results.json").exists()
    assert (Path("evaluations/snapshots/README.md")).exists()
