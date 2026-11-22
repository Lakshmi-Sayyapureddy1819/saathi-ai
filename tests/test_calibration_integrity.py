"""Frozen calibration set: evaluation must never replace it, edits must be detected, and a labelled set is immutable.
All tests use temp files; the real dataset is never touched."""
import hashlib
import json
import os
import stat

import pytest

import evaluations.run_evals as ev
from evaluations.calibration import (CalibrationIntegrityError, FrozenResponse, digest, freeze, labels_exist,
                                     load_frozen)


def _resp(n=3):
    return [FrozenResponse(case_id=f"C{i}", user_input=f"q{i}", expected_outcome="x", response=f"answer {i}")
            for i in range(n)]


def _paths(tmp_path):
    return dict(path=tmp_path / "resp.json", hash_path=tmp_path / "resp.sha256", label_path=tmp_path / "labels.json")


def _labels(tmp_path, a=None, b=None, n=3):
    (tmp_path / "labels.json").write_text(json.dumps(
        {"labels": {f"C{i}": {"annotator_a": a, "annotator_b": b} for i in range(n)}}), encoding="utf-8")


def test_freeze_writes_file_hash_and_makes_it_read_only(tmp_path):
    p = _paths(tmp_path); _labels(tmp_path)
    fs = freeze(_resp(), **p)
    assert load_frozen(p["path"], p["hash_path"]).meta.sha256 == fs.meta.sha256 == digest(_resp())
    assert p["hash_path"].read_text().strip() == fs.meta.sha256
    assert not os.access(p["path"], os.W_OK)                       # accidental overwrite blocked at the OS level


def test_second_freeze_is_refused_without_force(tmp_path):
    p = _paths(tmp_path); _labels(tmp_path)
    freeze(_resp(), **p)
    before = p["path"].read_bytes()
    with pytest.raises(CalibrationIntegrityError, match="already exists"):
        freeze(_resp(2), **p)
    assert p["path"].read_bytes() == before


def test_force_is_allowed_only_while_no_labels_exist(tmp_path):
    p = _paths(tmp_path); _labels(tmp_path)                        # template: all null
    assert not labels_exist(p["label_path"])
    freeze(_resp(), **p)
    fs2 = freeze(_resp(2), force=True, **p)                        # ok: nothing labelled yet
    assert len(load_frozen(p["path"], p["hash_path"]).responses) == 2 == len(fs2.responses)
    _labels(tmp_path, a="pass", b="fail")                          # a human has now labelled
    assert labels_exist(p["label_path"])
    before = p["path"].read_bytes()
    with pytest.raises(CalibrationIntegrityError, match="Human labels exist"):
        freeze(_resp(3), force=True, **p)
    assert p["path"].read_bytes() == before                        # labelled set is immutable, even with force


def test_partial_labels_also_count_as_labelled(tmp_path):
    p = _paths(tmp_path); _labels(tmp_path, a="pass", b=None)
    assert labels_exist(p["label_path"])


def test_tampering_is_detected_not_trusted(tmp_path):
    p = _paths(tmp_path); _labels(tmp_path)
    freeze(_resp(), **p)
    os.chmod(p["path"], stat.S_IWRITE | stat.S_IREAD)
    d = json.loads(p["path"].read_text(encoding="utf-8"))
    d["responses"][0]["response"] = "a different answer"
    p["path"].write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(CalibrationIntegrityError, match="does not match"):
        load_frozen(p["path"], p["hash_path"])


def test_missing_hash_or_legacy_format_is_an_error(tmp_path):
    p = _paths(tmp_path); _labels(tmp_path)
    freeze(_resp(), **p)
    os.chmod(p["hash_path"], stat.S_IWRITE | stat.S_IREAD); p["hash_path"].unlink()
    with pytest.raises(CalibrationIntegrityError, match="missing"):
        load_frozen(p["path"], p["hash_path"])
    p["path"].chmod(stat.S_IWRITE | stat.S_IREAD)
    p["path"].write_text(json.dumps([{"case_id": "C0"}]), encoding="utf-8")        # old list format
    with pytest.raises(CalibrationIntegrityError, match="not a valid frozen"):
        load_frozen(p["path"], p["hash_path"])


def test_absent_means_not_frozen_yet(tmp_path):
    p = _paths(tmp_path)
    assert load_frozen(p["path"], p["hash_path"]) is None


# ---- repeated EVALUATION must not change the frozen files or the labels ----
def test_run_evals_has_no_code_path_that_writes_calibration_files():
    src = open(ev.__file__, encoding="utf-8").read()
    assert "RESPONSES_FILE" not in src and "calibration_responses" not in src.replace("freeze_calibration", "")
    assert "calibration_cases" not in src                       # evaluation no longer regenerates calibration answers


def test_repeated_judging_leaves_frozen_set_and_labels_byte_identical(tmp_path, monkeypatch):
    p = _paths(tmp_path); _labels(tmp_path, a="pass", b="pass")
    freeze(_resp(15), force=False, **{**p, "label_path": tmp_path / "none.json"})   # frozen before labelling
    monkeypatch.setattr(ev, "LABEL_FILE", p["label_path"])
    h = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()
    snap = {k: h(v) for k, v in p.items()}
    calls = []
    monkeypatch.setattr(ev, "run_llm_judge", lambda case, resp: calls.append(resp) or "pass")
    for _ in range(3):                                          # evaluate three times
        fs = load_frozen(p["path"], p["hash_path"])
        judged = {r.case_id: ev.run_llm_judge({"user_input": r.user_input, "expected_outcome": r.expected_outcome}, r.response)
                  for r in fs.responses}
        agree = ev.judge_agreement(judged, ev.load_human_labels())
    assert {k: h(v) for k, v in p.items()} == snap              # responses, hash and labels unchanged
    assert set(calls) == {f"answer {i}" for i in range(15)}     # the judge saw exactly the frozen responses
    assert agree["n"] == 3 or agree["n"] == 0                   # labels reference C0..C2 only; 15 needed -> N/A
    assert agree["judge_vs_a"] is None


def test_real_dataset_is_frozen_verified_and_labels_still_blank():
    fs = load_frozen()                                          # raises if the real file was edited
    assert fs is not None and len(fs.responses) == 15
    assert not labels_exist()                                   # we never fabricate labels
