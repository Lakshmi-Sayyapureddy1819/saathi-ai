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
_lf_auth_verified: Optional[bool] = None
_lf_active: "contextvars.ContextVar[bool]" = contextvars.ContextVar("lf_active", default=False)


class TracingStatus(BaseModel):
    model_config = ConfigDict(frozen=True)
    langfuse_enabled: bool
    langfuse_errors: int
    last_langfuse_error: Optional[str]
    note: str
    auth_verified: Optional[bool] = None  # True: keys accepted; False: rejected (Langfuse turned off); None: not checked / unreachable


def tracing_status() -> TracingStatus:
    return TracingStatus(langfuse_enabled=_langfuse is not None, langfuse_errors=_lf_errors,
                         last_langfuse_error=_lf_last_error, note=_lf_init_note, auth_verified=_lf_auth_verified)


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


def _credentials_rejected(exc: BaseException) -> bool:
    """401/403 from Langfuse (or its 'no projects for these credentials' error) means the keys are wrong."""
    code = getattr(exc, "status_code", None)
    return code in (401, 403) or type(exc).__name__ in ("UnauthorizedError", "AccessDeniedError") or "No projects" in str(exc)


class _Short(Exception):
    """Compact view of an SDK API error: HTTP status + the service's own message, without the header dump."""
    def __init__(self, exc: BaseException):
        body = getattr(exc, "body", None)
        msg = body.get("message") if isinstance(body, dict) else None
        status = getattr(exc, "status_code", None)
        detail = msg or str(exc)[:200]
        super().__init__(f"HTTP {status}: {detail}" if status else detail)
        self.__class__ = type(type(exc).__name__, (Exception,), {})  # keep the original class name in the log line


def verify_credentials(client: Any) -> Optional[bool]:
    """Blocking, bounded credential check (the SDK's own timeout applies). Returns True / False, or None when it
    could not be decided (network down, Langfuse unreachable): an outage is not evidence of bad keys."""
    global _lf_auth_verified
    try:
        client.auth_check()
        _lf_auth_verified = True
    except Exception as e:  # noqa: BLE001
        if _credentials_rejected(e):
            _lf_auth_verified = False
            _lf_fail("credential check (keys rejected)", _Short(e))
        else:
            _lf_auth_verified = None
            _lf_fail("credential check (could not reach Langfuse; keys unverified)", e)
    return _lf_auth_verified


def init_langfuse(client: Any = None, check_auth: Optional[bool] = None) -> None:
    """(Re)initialise the Langfuse backend. Pass `client` to inject one (tests); otherwise build from env.

    The credential check runs for env-built clients (skip with LANGFUSE_AUTH_CHECK=0) and for injected ones only when
    check_auth=True. Rejected keys switch Langfuse OFF with a clear reason, instead of letting every span export fail
    in the background (the SDK exports asynchronously, so a 401 would otherwise only reach the log)."""
    global _langfuse, _lf_init_note, _lf_auth_verified
    _lf_auth_verified = None
    if client is None:
        if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
            _langfuse, _lf_init_note = None, "disabled: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set (local tracing only)"
            logger.info("Langfuse %s", _lf_init_note)
            return
        try:
            from langfuse import Langfuse
            client = Langfuse()  # reads LANGFUSE_PUBLIC_KEY / SECRET_KEY / HOST|BASE_URL from the environment
        except Exception as e:  # SDK missing or incompatible: say so loudly, keep local tracing
            _langfuse = None
            _lf_init_note = f"disabled: could not initialise Langfuse ({_lf_fail('init', e)})"
            logger.warning("Langfuse %s", _lf_init_note)
            return
        do_check = check_auth if check_auth is not None else os.environ.get("LANGFUSE_AUTH_CHECK", "1") != "0"
        note_ok = "enabled"
    else:
        do_check = bool(check_auth)
        note_ok = "injected client"
    _langfuse, _lf_init_note = client, note_ok
    if not do_check:
        return
    result = verify_credentials(client)
    if result is False:
        try:
            client.shutdown()  # stop the background exporter so it does not keep failing
        except Exception as e:  # noqa: BLE001
            _lf_fail("shutdown after rejected credentials", e)
        _langfuse = None
        _lf_init_note = ("disabled: Langfuse REJECTED the credentials (401). Check LANGFUSE_PUBLIC_KEY (pk-lf-...), "
                         "LANGFUSE_SECRET_KEY (sk-lf-...) and LANGFUSE_HOST / region. Local tracing continues.")
        logger.warning("Langfuse %s", _lf_init_note)
    elif result is None:
        _lf_init_note = "enabled, but credentials could not be verified (Langfuse unreachable); spans may be dropped"
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


def capture_content() -> bool:
    """LANGFUSE_CAPTURE_CONTENT=true sends raw prompts/replies/queries to the trace. Default: redacted (health data)."""
    return os.environ.get("LANGFUSE_CAPTURE_CONTENT", "").strip().lower() in ("1", "true", "yes")


_FREE_TEXT_KEYS = frozenset({"query", "reply", "text", "prompt", "user_text", "response", "note", "target_symptom"})


def _mask(value: Any, free_text: bool = True) -> Any:
    """Span input/output as it may leave the process. Raw only when capture is explicitly on; otherwise free text
    (a bare string, or a dict value under a _FREE_TEXT_KEYS key) is redacted and structured ids/slots/dates pass."""
    if value is None or capture_content():
        return value
    if isinstance(value, str):
        if not free_text:
            return value
        from app.observability.redact import redact
        return redact(value)
    if isinstance(value, dict):
        return {k: _mask(v, k in _FREE_TEXT_KEYS) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mask(v, free_text) for v in value]
    return value if isinstance(value, (int, float, bool)) else str(value)


class Span:
    def __init__(self, record: dict):
        self.record = record

    def set(self, **meta) -> None:
        self.record["metadata"].update(meta)

    def set_input(self, value: Any) -> None:
        self.record["input"] = _mask(value)

    def set_output(self, value: Any) -> None:
        self.record["output"] = _mask(value)


def _plain(meta: dict) -> dict:
    """Langfuse/OTel attributes want JSON-friendly values."""
    return {k: v if isinstance(v, (str, int, float, bool)) or v is None else str(v) for k, v in meta.items()}


_AS_TYPE = {"llm": "generation", "tool": "tool"}


def _trace_attributes(name: str, md: dict) -> Any:
    """propagate_attributes(...) context manager: user (pseudonymous member_id), session, version, tags, trace name."""
    from langfuse import propagate_attributes
    tags = ["saathi"] + [f"{k}:{md[k]}" for k in ("channel", "engine") if md.get(k)]
    return propagate_attributes(
        user_id=str(md["member_id"]) if md.get("member_id") else None,
        session_id=str(md["session_id"]) if md.get("session_id") else None,
        version=str(md["prompt_version"]) if md.get("prompt_version") else None,
        tags=tags, trace_name=name,
        metadata={k: str(md[k]) for k in ("channel", "engine", "prompt_version") if md.get(k)})


@contextmanager
def span(name: str, trace_id: str, kind: str = "node", input: Any = None, **metadata) -> Iterator[Span]:
    """Wrap a node / tool / LLM call. kind in {root, node, tool, llm}.

    `input` / Span.set_input / Span.set_output fill Langfuse's Input/Output panes (redacted unless
    LANGFUSE_CAPTURE_CONTENT=true). A root span also sets the trace-level user, session, tags, version and I/O."""
    rec = {"trace_id": trace_id, "span_id": uuid.uuid4().hex[:16], "name": name,
           "kind": kind, "start": time.time(), "metadata": dict(metadata)}
    s = Span(rec)
    if input is not None:
        s.set_input(input)
    t0 = time.perf_counter()

    lf_cm, lf_obs, lf_token, lf_attrs = None, None, None, None
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
            if kind == "root":  # trace-level attributes, propagated to every child observation
                lf_attrs = _trace_attributes(name, metadata)
                if lf_attrs is not None:
                    lf_attrs.__enter__()
        except Exception as e:
            rec["langfuse_error"] = _lf_fail(f"start span '{name}'", e)
            if lf_token is not None:
                _lf_active.reset(lf_token)
            lf_cm = lf_obs = lf_token = lf_attrs = None
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
                if rec.get("input") is not None:
                    upd["input"] = rec["input"]
                if rec.get("output") is not None:
                    upd["output"] = rec["output"]
                if kind == "llm":
                    if md.get("prompt_tokens") is not None or md.get("completion_tokens") is not None:
                        upd["usage_details"] = {"input": md.get("prompt_tokens", 0), "output": md.get("completion_tokens", 0)}
                    if md.get("cost_usd") is not None:
                        upd["cost_details"] = {"total": md["cost_usd"]}
                if rec["status"] == "error":
                    upd["level"], upd["status_message"] = "ERROR", rec.get("error", "")
                lf_obs.update(**upd)
                if kind == "root" and (rec.get("input") is not None or rec.get("output") is not None):
                    lf_obs.set_trace_io(input=rec.get("input"), output=rec.get("output"))
            except Exception as e:
                rec["langfuse_error"] = _lf_fail(f"update span '{name}'", e)
            try:
                if lf_attrs is not None:
                    lf_attrs.__exit__(None, None, None)
                lf_cm.__exit__(None, None, None)
            except Exception as e:
                rec["langfuse_error"] = _lf_fail(f"end span '{name}'", e)
            finally:
                if lf_token is not None:
                    _lf_active.reset(lf_token)
        _write(rec)


def flush(background: bool = False) -> None:
    """Send buffered spans to Langfuse. background=True returns at once (voice: the ~400 ms network round trip must
    not sit between the caller finishing a sentence and hearing the reply)."""
    if background and _langfuse is not None:
        threading.Thread(target=flush, name="langfuse-flush", daemon=True).start()
        return
    if _langfuse is not None:
        try:
            _langfuse.flush()
        except Exception as e:
            _lf_fail("flush", e)
