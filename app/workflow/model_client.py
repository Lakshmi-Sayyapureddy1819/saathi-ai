"""Config-driven model client (config/models.yaml) with fallback, real usage metadata and spans."""
import os
import logging
import time
from typing import Optional

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


# USD per 1M tokens. Update from the providers' pricing pages; used only for cost estimates.
PRICING: dict[str, PricingEntry] = {
    "gemini-2.5-flash": PricingEntry(input_per_mtok=0.30, output_per_mtok=2.50),
    "gemini-2.5-pro": PricingEntry(input_per_mtok=1.25, output_per_mtok=10.00),
    "gpt-4o-mini": PricingEntry(input_per_mtok=0.15, output_per_mtok=0.60),
    "gpt-4o": PricingEntry(input_per_mtok=2.50, output_per_mtok=10.00),
}


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = PRICING.get(model)
    if p is None:
        return 0.0
    return (prompt_tokens * p.input_per_mtok + completion_tokens * p.output_per_mtok) / 1_000_000


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

        for model_id in (node_config.get("default_model"), node_config.get("fallback_model")):
            if not model_id:
                continue
            with span(f"llm:{model_id}", trace_id, kind="llm", model=model_id, route=node_name,
                      prompt_chars=len(prompt)) as s:
                try:
                    result = self._invoke(model_id, prompt)
                    s.set(prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
                          cost_usd=result.cost_usd, mock=result.mock)
                    if result.text:
                        return result
                except Exception as e:
                    logging.warning(f"Model {model_id} failed: {e}")
                    s.set(failed=True)
        raise RuntimeError(f"All models failed for route {node_name}")

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
                              json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
            if r.status_code != 200:
                raise RuntimeError(f"Gemini API returned {r.status_code}")  # body omitted: may echo request
            data = r.json()
            usage = data.get("usageMetadata", {})
            pt, ct = usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0)
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
                              timeout=20)
            if r.status_code != 200:
                raise RuntimeError(f"OpenAI API returned {r.status_code}")
            data = r.json()
            usage = data.get("usage", {})
            pt, ct = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
            return LLMResult(text=data["choices"][0]["message"]["content"], model=model_id,
                             prompt_tokens=pt, completion_tokens=ct,
                             latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                             cost_usd=_cost(model_id, pt, ct))

        raise RuntimeError(f"Unsupported model provider for {model_id}")
