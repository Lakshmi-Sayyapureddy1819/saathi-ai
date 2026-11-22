"""Tracing: every node, tool call and model call gets a span carrying a trace_id.

Spans always go to logs/traces.jsonl (one JSON object per span, queryable with jq). When LANGFUSE_PUBLIC_KEY and
LANGFUSE_SECRET_KEY are set they are also sent to Langfuse via the 4.x observation API
(`start_as_current_observation`); LLM spans become Langfuse *generations* with model, token usage and cost.

Langfuse problems never break a turn, but they are never silent either: each failure is counted, logged, kept in
`tracing_status().last_langfuse_error`, and written to the affected local span as `langfuse_error`.
"""
import contextvars
import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

_lock = threading.Lock()
TRACE_FILE = os.environ.get("TRACE_FILE", "logs/traces.jsonl")

_langfuse: Any = None                      # a langfuse.Langfuse client, or None
_lf_errors = 0
_lf_last_error: Optional[str] = None
_lf_init_note: str = "not initialised"
_lf_active: "contextvars.ContextVar[bool]" = contextvars.ContextVar("lf_active", default=False)


class TracingStatus(BaseModel):
    model_config = ConfigDict(frozen=True)
    langfuse_enabled: bool
    langfuse_errors: int
    last_langfuse_error: Optional[str]
    note: str


def tracing_status() -> TracingStatus:
    return TracingStatus(langfuse_enabled=_langfuse is not None, langfuse_errors=_lf_errors,
                         last_langfuse_error=_lf_last_error, note=_lf_init_note)


def _lf_fail(stage: str, exc: BaseException) -> str:
    """Record a Langfuse failure: counter + last error + a log line (all of the first 5, then every 100th)."""
    global _lf_errors, _lf_last_error
    msg = f"{stage}: {type(exc).__name__}: {exc}"
    with _lock:
        _lf_errors += 1
        _lf_last_error = msg
        n = _lf_errors
    if n <= 5 or n % 100 == 0:
        logger.warning("Langfuse %s (failure #%d; local tracing continues)", msg, n)
    return msg


def init_langfuse(client: Any = None) -> None:
    """(Re)initialise the Langfuse backend. Pass `client` to inject one (tests); otherwise build from env."""
    global _langfuse, _lf_init_note
    if client is not None:
        _langfuse, _lf_init_note = client, "injected client"
        return
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        _langfuse, _lf_init_note = None, "disabled: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set (local tracing only)"
        logger.info("Langfuse %s", _lf_init_note)
        return
    try:
        from langfuse import Langfuse
        _langfuse = Langfuse()  # reads LANGFUSE_PUBLIC_KEY / SECRET_KEY / HOST|BASE_URL from the environment
        _lf_init_note = "enabled"
    except Exception as e:  # SDK missing or incompatible: say so loudly, keep local tracing
        _langfuse = None
        _lf_init_note = f"disabled: could not initialise Langfuse ({_lf_fail('init', e)})"
        logger.warning("Langfuse %s", _lf_init_note)


init_langfuse()


def new_trace_id() -> str:
    return uuid.uuid4().hex  # 32 lowercase hex chars: also a valid Langfuse/OpenTelemetry trace id


def _write(record: dict) -> None:
    try:
        os.makedirs(os.path.dirname(TRACE_FILE) or ".", exist_ok=True)
        with _lock, open(TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("Failed to write trace: %s", e)


class Span:
    def __init__(self, record: dict):
        self.record = record

    def set(self, **meta) -> None:
        self.record["metadata"].update(meta)


def _plain(meta: dict) -> dict:
    """Langfuse/OTel attributes want JSON-friendly values."""
    return {k: v if isinstance(v, (str, int, float, bool)) or v is None else str(v) for k, v in meta.items()}


_AS_TYPE = {"llm": "generation", "tool": "tool"}


@contextmanager
def span(name: str, trace_id: str, kind: str = "node", **metadata) -> Iterator[Span]:
    """Wrap a node / tool / LLM call. kind in {root, node, tool, llm}."""
    rec = {"trace_id": trace_id, "span_id": uuid.uuid4().hex[:16], "name": name,
           "kind": kind, "start": time.time(), "metadata": dict(metadata)}
    s = Span(rec)
    t0 = time.perf_counter()

    lf_cm, lf_obs, lf_token = None, None, None
    if _langfuse is not None:
        try:
            kw: dict = {"name": name, "as_type": _AS_TYPE.get(kind, "span"), "metadata": _plain({"kind": kind, **metadata})}
            if kind == "llm" and metadata.get("model"):
                kw["model"] = metadata["model"]
            if not _lf_active.get():  # outermost span of this call tree: bind it to OUR trace id
                kw["trace_context"] = {"trace_id": trace_id}
            lf_cm = _langfuse.start_as_current_observation(**kw)
            lf_obs = lf_cm.__enter__()
            lf_token = _lf_active.set(True)
        except Exception as e:
            rec["langfuse_error"] = _lf_fail(f"start span '{name}'", e)
            lf_cm = lf_obs = None
    try:
        yield s
        rec["status"] = "ok"
    except Exception as e:
        rec["status"] = "error"
        rec["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        rec["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        if lf_cm is not None:
            try:
                md = rec["metadata"]
                upd: dict = {"metadata": _plain({"kind": kind, "latency_ms": rec["latency_ms"], **md})}
                if kind == "llm":
                    if md.get("prompt_tokens") is not None or md.get("completion_tokens") is not None:
                        upd["usage_details"] = {"input": md.get("prompt_tokens", 0), "output": md.get("completion_tokens", 0)}
                    if md.get("cost_usd") is not None:
                        upd["cost_details"] = {"total": md["cost_usd"]}
                if rec["status"] == "error":
                    upd["level"], upd["status_message"] = "ERROR", rec.get("error", "")
                lf_obs.update(**upd)
            except Exception as e:
                rec["langfuse_error"] = _lf_fail(f"update span '{name}'", e)
            try:
                lf_cm.__exit__(None, None, None)
            except Exception as e:
                rec["langfuse_error"] = _lf_fail(f"end span '{name}'", e)
            finally:
                if lf_token is not None:
                    _lf_active.set(False)
        _write(rec)


def flush() -> None:
    if _langfuse is not None:
        try:
            _langfuse.flush()
        except Exception as e:
            _lf_fail("flush", e)
