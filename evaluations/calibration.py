"""Frozen calibration responses: the single set of agent answers that humans label AND the judge scores.

Why: kappa only means something if the judge and the annotators looked at the *same* responses. Generation is
therefore a separate, deliberate step (`python -m evaluations.freeze_calibration`); evaluation only ever READS the
frozen file. Safeguards against accidental replacement:
  * freeze refuses to overwrite an existing file unless --force;
  * even with --force it refuses once any human label exists in human_labels.json;
  * the file is made read-only after freezing;
  * a sidecar SHA-256 is verified on every load, so an edit or partial overwrite is detected, not trusted.
"""
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

DATASETS = Path("evaluations/datasets")
RESPONSES_FILE = DATASETS / "calibration_responses.json"
HASH_FILE = DATASETS / "calibration_responses.sha256"
LABEL_FILE = DATASETS / "human_labels.json"


class CalibrationIntegrityError(RuntimeError):
    """The frozen set is missing its hash, was edited, or cannot be replaced safely."""


class FrozenResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    case_id: str
    user_input: str
    expected_outcome: str
    response: str


class FreezeMeta(BaseModel):
    model_config = ConfigDict(frozen=True)
    frozen_at: str
    note: str = ""
    models: List[str] = []
    prompt_version: str = ""
    sha256: str


class FrozenSet(BaseModel):
    model_config = ConfigDict(frozen=True)
    meta: FreezeMeta
    responses: List[FrozenResponse]


def digest(responses: List[FrozenResponse]) -> str:
    """Hash of the responses only (not the metadata), over a canonical JSON form."""
    canon = json.dumps([r.model_dump() for r in responses], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def labels_exist(label_path: Path = LABEL_FILE) -> bool:
    """True if any annotator has recorded any label (the template is all null)."""
    try:
        data = json.loads(Path(label_path).read_text(encoding="utf-8")).get("labels", {})
    except FileNotFoundError:
        return False
    return any(v is not None for entry in data.values() for v in entry.values())


def _make_writable(path: Path) -> None:
    if path.exists():
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


def freeze(responses: List[FrozenResponse], *, models: List[str] = (), prompt_version: str = "", note: str = "",
           path: Path = RESPONSES_FILE, hash_path: Path = HASH_FILE, label_path: Path = LABEL_FILE,
           force: bool = False) -> FrozenSet:
    path, hash_path = Path(path), Path(hash_path)
    if path.exists() and not force:
        raise CalibrationIntegrityError(
            f"{path} already exists and is frozen. Refusing to overwrite (use --force only if no labels exist).")
    if path.exists() and labels_exist(label_path):
        raise CalibrationIntegrityError(
            f"Human labels exist in {label_path}: replacing {path} would invalidate them. Refusing, even with --force. "
            "Start a new calibration round (new files) instead.")
    fs = FrozenSet(meta=FreezeMeta(frozen_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), note=note,
                                   models=list(models), prompt_version=prompt_version, sha256=digest(responses)),
                   responses=list(responses))
    _make_writable(path)
    _make_writable(hash_path)
    path.write_text(json.dumps(fs.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    hash_path.write_text(fs.meta.sha256 + "\n", encoding="utf-8")
    os.chmod(path, stat.S_IREAD)
    os.chmod(hash_path, stat.S_IREAD)
    return fs


def load_frozen(path: Path = RESPONSES_FILE, hash_path: Path = HASH_FILE) -> Optional[FrozenSet]:
    """None if nothing has been frozen yet. Raises CalibrationIntegrityError if the file does not match its hash."""
    path, hash_path = Path(path), Path(hash_path)
    if not path.exists():
        return None
    try:
        fs = FrozenSet.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception as e:
        raise CalibrationIntegrityError(
            f"{path} is not a valid frozen calibration set ({type(e).__name__}). "
            "If it is an old-format file, re-freeze it with no labels present.") from e
    if not hash_path.exists():
        raise CalibrationIntegrityError(f"{hash_path} is missing: cannot verify {path}.")
    recorded = hash_path.read_text(encoding="utf-8").strip()
    actual = digest(fs.responses)
    if not (recorded == actual == fs.meta.sha256):
        raise CalibrationIntegrityError(
            f"{path} does not match its recorded hash (file edited or replaced). Labels may no longer apply.")
    return fs
