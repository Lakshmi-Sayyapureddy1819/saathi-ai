"""Config-driven model client (config/models.yaml) with fallback, real usage metadata and spans."""
import os
import logging
import re
import threading
import time
from datetime import date, datetime, timezone
from typing import List, Optional

import requests
import yaml
from pydantic import BaseModel, ConfigDict

from app.observability.tracer import span, new_trace_id


class LLMResult(BaseModel):
    """Typed result of one model call. Token counts come from provider usage metadata."""
    model_config = ConfigDict(frozen=True)
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    mock: bool = False


class PricingEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    input_per_mtok: float
    output_per_mtok: float
    effective_from: date = date.min  # the newest entry whose date <= today applies


# USD per 1M tokens, Standard paid tier. Verified 2026-11-22 against aistudio.google.com/docs/pricing and
# OpenAI API pricing. gemini-3.8-flash doubles on 2027-01-01 (published schedule), so entries are date-aware.
# gemini-2.5-* stays only for historical traces: Google shuts them down 2026-12-01.
PRICING: dict[str, List[PricingEntry]] = {
    "gemini-3.5-flash-lite": [PricingEntry(input_per_mtok=0.30, output_per_mtok=2.50)],
    "gemini-3.8-flash": [PricingEntry(input_per_mtok=0.75, output_per_mtok=3.75),
                         PricingEntry(input_per_mtok=1.50, output_per_mtok=7.50, effective_from=date(2027, 1, 1))],
    "gemini-2.5-flash": [PricingEntry(input_per_mtok=0.30, output_per_mtok=2.50)],
    "gemini-2.5-pro": [PricingEntry(input_per_mtok=1.25, output_per_mtok=10.00)],
    "gpt-4o-mini": [PricingEntry(input_per_mtok=0.15, output_per_mtok=0.60)],
    "gpt-4o": [PricingEntry(input_per_mtok=2.50, output_per_mtok=10.00)],
    "llama3.2": [PricingEntry(input_per_mtok=0.0, output_per_mtok=0.0)],
}


def _cost(model: str, prompt_tokens: int, completion_tokens: int, today: Optional[date] = None) -> float:
    today = today or date.today()
    applicable = [e for e in PRICING.get(model, []) if e.effective_from <= today]
    if not applicable:
        return 0.0
    p = max(applicable, key=lambda e: e.effective_from)
    return (prompt_tokens * p.input_per_mtok + completion_tokens * p.output_per_mtok) / 1_000_000


# ---------------------------------------------------------------- model health (visible failures)
# Why this exists: a provider can fail (bad key, outage, injected fault) and the fallback silently hides it, so the
# app "works" while traces show an unexplained mix of vendors. Every outcome is counted with its reason, and the
# status is exposed (no secrets) so a degraded primary is noticed, not discovered later.
class ModelHealth(BaseModel):
    model_config = ConfigDict(frozen=True)
    model: str
    ok: int = 0
    failed: int = 0
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    last_ok_at: Optional[datetime] = None


class LLMStatus(BaseModel):
    model_config = ConfigDict(frozen=True)
    models: List[ModelHealth]
    fallback_calls: int  # calls answered by a fallback model because the primary failed
    credentials: dict[str, str]  # provider -> "ok" | "rejected (HTTP 400)" | "not set" | "unreachable" | "not checked"


_HEALTH: dict[str, ModelHealth] = {}
_FALLBACKS = 0
_CREDS: dict[str, str] = {}
_LOCK = threading.Lock()

# Resilience knobs. A provider that fails BREAKER_THRESHOLD times in a row is skipped for BREAKER_COOLDOWN_S so a dead
# provider is not waited on (timeouts) by every message; after the cooldown the next call probes it again. Only routes
# that HAVE a fallback use the breaker; eval-only "mix" routes (no fallback) must see every failure, so they skip it.
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_SECONDS", "15"))
RETRY_DELAY_S = 0.4
BREAKER_THRESHOLD = 3
BREAKER_COOLDOWN_S = 30.0
_CONSEC: dict[str, int] = {}
_OPEN_UNTIL: dict[str, float] = {}


def _is_transient(exc: BaseException) -> bool:
    """Worth one quick retry: a dropped connection, rate limit (429) or provider 5xx. Not a timeout (retrying a
    15 s hang doubles the member's wait) and not a 4xx such as a rejected key."""
    if isinstance(exc, (requests.exceptions.Timeout, TimeoutError)):
        return False
    if isinstance(exc, (requests.exceptions.ConnectionError, ConnectionError)):
        return True
    return bool(re.search(r"returned (429|5\d\d)\b", str(exc)))


def _breaker_open(model: str) -> bool:
    with _LOCK:
        return _OPEN_UNTIL.get(model, 0.0) > time.monotonic()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _reason(exc: BaseException) -> str:
    """Short, safe failure reason: class + message, truncated, with any configured API key scrubbed. Provider response
    bodies are never included by the callers (they can echo the request)."""
    text = f"{type(exc).__name__}: {exc}"
    for var in ("GEMINI_API_KEY", "OPENAI_API_KEY"):
        key = os.getenv(var)
        if key:
            text = text.replace(key, "<key>")
    return text[:160]


def _record(model: str, ok: bool, error: Optional[str] = None, fallback: bool = False) -> None:
    global _FALLBACKS
    with _LOCK:
        h = _HEALTH.get(model) or ModelHealth(model=model)
        if ok:
            h = h.model_copy(update={"ok": h.ok + 1, "last_ok_at": _now()})
            if fallback:
                _FALLBACKS += 1
        else:
            h = h.model_copy(update={"failed": h.failed + 1, "last_error": error, "last_error_at": _now()})
        _HEALTH[model] = h
        if ok:
            _CONSEC[model] = 0
            _OPEN_UNTIL.pop(model, None)
        else:
            _CONSEC[model] = _CONSEC.get(model, 0) + 1
            if _CONSEC[model] >= BREAKER_THRESHOLD:
                _OPEN_UNTIL[model] = time.monotonic() + BREAKER_COOLDOWN_S
                logging.error("Circuit open for %s after %d consecutive failures: skipping it for %.0fs.",
                              model, _CONSEC[model], BREAKER_COOLDOWN_S)


def llm_status() -> LLMStatus:
    with _LOCK:
        return LLMStatus(models=sorted(_HEALTH.values(), key=lambda h: h.model), fallback_calls=_FALLBACKS,
                         credentials=dict(_CREDS) or {"gemini": "not checked", "openai": "not checked"})


def reset_llm_status() -> None:
    global _FALLBACKS
    with _LOCK:
        _HEALTH.clear()
        _CREDS.clear()
        _CONSEC.clear()
        _OPEN_UNTIL.clear()
        _FALLBACKS = 0


def check_credentials(timeout: float = 8.0) -> dict[str, str]:
    """Ask each configured provider's own (free) model-list endpoint whether the key is accepted. Never raises, never
    logs the key, and sends it only to that provider. Run at server start so a bad key is a loud, specific message
    ("GEMINI_API_KEY rejected (HTTP 400)") instead of a mystery fallback to another vendor later."""
    checks = {
        "gemini": (os.getenv("GEMINI_API_KEY"), "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
                   lambda k: {"x-goog-api-key": k}),
        "openai": (os.getenv("OPENAI_API_KEY"), "https://api.openai.com/v1/models",
                   lambda k: {"Authorization": f"Bearer {k}"}),
    }
    out: dict[str, str] = {}
    for name, (key, url, headers) in checks.items():
        if not key:
            out[name] = "not set"
            continue
        try:
            status = requests.get(url, headers=headers(key), timeout=timeout).status_code
            out[name] = "ok" if status == 200 else (f"rejected (HTTP {status})" if status in (400, 401, 403)
                                                    else f"error (HTTP {status})")
        except Exception as e:  # noqa: BLE001 - startup check must never crash the server
            out[name] = f"unreachable ({type(e).__name__})"
        if out[name] != "ok":
            logging.error("LLM credential check: %s key is %s. Calls to %s models will fail over to the other "
                          "provider.", name.upper(), out[name], name)
    with _LOCK:
        _CREDS.clear()
        _CREDS.update(out)
    return out


class ModelClient:
    def __init__(self, config_path: str = "config/models.yaml", quality_optimized: bool = False,
                 node: Optional[str] = None):
        """`node` selects a routing entry in models.yaml (e.g. 'voice'); defaults by quality flag."""
        self.config_path = config_path
        self.config = self._load_config()
        self.nodes = {n["name"]: n for n in self.config.get("routing", {}).get("nodes", [])}
        self.quality_optimized = quality_optimized
        self.node = node

    def _load_config(self) -> dict:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logging.error(f"Failed to load model config: {e}")
            return {}

    def call_model(self, prompt: str, trace_id: Optional[str] = None) -> str:
        return self.generate(prompt, trace_id).text

    def generate(self, prompt: str, trace_id: Optional[str] = None) -> LLMResult:
        trace_id = trace_id or new_trace_id()
        node_name = self.node or ("quality_optimized" if self.quality_optimized else "cost_optimized")
        node_config = self.nodes.get(node_name)
        if not node_config:
            raise ValueError(f"Unknown node configuration: {node_name}")

        primary = node_config.get("default_model")
        use_breaker = bool(node_config.get("fallback_model"))
        for model_id in (primary, node_config.get("fallback_model")):
            if not model_id:
                continue
            if use_breaker and _breaker_open(model_id):
                logging.warning("Skipping %s: circuit open (recent consecutive failures).", model_id)
                continue
            with span(f"llm:{model_id}", trace_id, kind="llm", model=model_id, route=node_name,
                      prompt_chars=len(prompt), input=prompt) as s:
                try:
                    result = self._invoke_with_retry(model_id, prompt)
                    s.set(prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
                          cost_usd=result.cost_usd, mock=result.mock)
                    s.set_output(result.text)
                    if result.text:
                        if not result.mock:
                            _record(model_id, ok=True, fallback=model_id != primary)
                            if model_id != primary:
                                logging.warning("Primary model %s failed; this call was served by fallback %s "
                                                "(route %s).", primary, model_id, node_name)
                        return result
                except Exception as e:
                    reason = _reason(e)
                    logging.warning(f"Model {model_id} failed: {reason}")
                    s.set(failed=True, error=reason)  # the reason is on the span, not just a failed flag
                    _record(model_id, ok=False, error=reason)
        raise RuntimeError(f"All models failed for route {node_name}")

    def _invoke_with_retry(self, model_id: str, prompt: str) -> LLMResult:
        try:
            return self._invoke(model_id, prompt)
        except Exception as e:  # noqa: BLE001
            if not _is_transient(e):
                raise
            logging.warning("Model %s transient failure (%s); retrying once.", model_id, _reason(e))
            time.sleep(RETRY_DELAY_S)
            return self._invoke(model_id, prompt)

    def _invoke(self, model_id: str, prompt: str) -> LLMResult:
        gemini_key = os.getenv("GEMINI_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        t0 = time.perf_counter()

        if not gemini_key and not openai_key:
            # Explicitly flagged mock so evals/metrics can exclude it.
            return LLMResult(text=f"[MOCK:{model_id}] No API keys configured.", model=model_id, mock=True)

        if "gemini" in model_id.lower():
            if not gemini_key:
                raise RuntimeError("GEMINI_API_KEY is missing.")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"
            r = requests.post(url, headers={"x-goog-api-key": gemini_key},
                              json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=LLM_TIMEOUT_S)
            if r.status_code != 200:
                raise RuntimeError(f"Gemini API returned {r.status_code}")  # body omitted: may echo request
            data = r.json()
            usage = data.get("usageMetadata", {})
            pt = usage.get("promptTokenCount", 0)
            # Gemini 2.5 bills "thinking" tokens as output but reports them separately.
            ct = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
            return LLMResult(text=data["candidates"][0]["content"]["parts"][0]["text"], model=model_id,
                             prompt_tokens=pt, completion_tokens=ct,
                             latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                             cost_usd=_cost(model_id, pt, ct))

        if "gpt" in model_id.lower():
            if not openai_key:
                raise RuntimeError("OPENAI_API_KEY is missing.")
            r = requests.post("https://api.openai.com/v1/chat/completions",
                              headers={"Authorization": f"Bearer {openai_key}"},
                              json={"model": model_id, "messages": [{"role": "user", "content": prompt}]},
                              timeout=LLM_TIMEOUT_S)
            if r.status_code != 200:
                raise RuntimeError(f"OpenAI API returned {r.status_code}")
            data = r.json()
            usage = data.get("usage", {})
            pt, ct = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
            return LLMResult(text=data["choices"][0]["message"]["content"], model=model_id,
                             prompt_tokens=pt, completion_tokens=ct,
                             latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                             cost_usd=_cost(model_id, pt, ct))

        if "llama" in model_id.lower() or "ollama" in model_id.lower() or os.getenv("OLLAMA_HOST"):
            ollama_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            r = requests.post(f"{ollama_url}/api/generate",
                              json={"model": model_id, "prompt": prompt, "stream": False},
                              timeout=LLM_TIMEOUT_S)
            if r.status_code != 200:
                raise RuntimeError(f"Ollama API returned {r.status_code}")
            data = r.json()
            pt, ct = data.get("prompt_eval_count", 0), data.get("eval_count", 0)
            return LLMResult(text=data.get("response", ""), model=model_id,
                             prompt_tokens=pt, completion_tokens=ct,
                             latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                             cost_usd=_cost(model_id, pt, ct))

        raise RuntimeError(f"Unsupported model provider for {model_id}")
