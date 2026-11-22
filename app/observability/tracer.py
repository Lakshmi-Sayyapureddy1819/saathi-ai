"""Tracing: every node, tool call and model call gets a span carrying a trace_id.

Spans always go to logs/traces.jsonl (one JSON object per span, queryable with jq).
If LANGFUSE_* env vars and the SDK are present, spans are mirrored to Langfuse on a
best-effort basis (Langfuse errors never break a turn).
Token counts/cost come from real provider usage metadata (see model_client); nothing is mocked.
"""
import os
import json
import time
import uuid
import logging
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

_lock = threading.Lock()
TRACE_FILE = os.environ.get("TRACE_FILE", "logs/traces.jsonl")

_langfuse = None
if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
    try:
        from langfuse import Langfuse
        _langfuse = Langfuse()
    except Exception as e:  # SDK missing or API changed: keep local tracing only
        logging.warning(f"Langfuse disabled: {e}")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def _write(record: dict) -> None:
    try:
        os.makedirs(os.path.dirname(TRACE_FILE) or ".", exist_ok=True)
        with _lock, open(TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
    except Exception as e:
        logging.error(f"Failed to write trace: {e}")


class Span:
    def __init__(self, record: dict):
        self.record = record

    def set(self, **meta) -> None:
        self.record["metadata"].update(meta)


@contextmanager
def span(name: str, trace_id: str, kind: str = "node", **metadata) -> Iterator[Span]:
    """Wrap a node / tool / LLM call. kind in {node, tool, llm}."""
    rec = {"trace_id": trace_id, "span_id": uuid.uuid4().hex[:16], "name": name,
           "kind": kind, "start": time.time(), "metadata": dict(metadata)}
    s = Span(rec)
    t0 = time.perf_counter()
    lf = None
    if _langfuse is not None:
        try:
            lf = _langfuse.start_as_current_span(name=name, metadata={"trace_id": trace_id, "kind": kind, **metadata})
            lf.__enter__()
        except Exception:
            lf = None
    try:
        yield s
        rec["status"] = "ok"
    except Exception as e:
        rec["status"] = "error"
        rec["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        rec["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        _write(rec)
        if lf is not None:
            try:
                lf.__exit__(None, None, None)
            except Exception:
                pass


def flush() -> None:
    if _langfuse is not None:
        try:
            _langfuse.flush()
        except Exception:
            pass
