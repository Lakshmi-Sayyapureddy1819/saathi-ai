"""Centralized Google ADK Model Gateway.

Subclasses ADK's native `BaseLlm` and serves as the single unified model invocation layer for the application.
Provides native `generate_content_async(LlmRequest)` implementation, ensuring every LLM call flows through
ADK's request/response lifecycle. Supports multi-provider fallback, exponential backoff, circuit breaking,
and observability.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, AsyncGenerator, Dict, Optional

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import ConfigDict

from app.workflow.model_client import LLMResult, ModelClient


def run_coro_sync(coro: Any) -> Any:
    """Safely executes an async coroutine synchronously, whether or not an event loop is already running."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


class ADKModelGateway(BaseLlm):
    """Unified Google ADK BaseLlm implementation that encapsulates routing, resilience, and multi-provider models."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    model: str = "gateway"
    _client: ModelClient = None
    _trace_id: Optional[str] = None

    def __init__(
        self,
        client: Optional[ModelClient] = None,
        node: Optional[str] = None,
        trace_id: Optional[str] = None,
        quality_optimized: bool = False,
        **kwargs: Any,
    ):
        super().__init__(model="gateway", **kwargs)
        if client is not None:
            self._client = client
        else:
            self._client = ModelClient(node=node, quality_optimized=quality_optimized)
        self._trace_id = trace_id

    @property
    def nodes(self) -> Dict[str, Any]:
        return getattr(self._client, "nodes", {})

    @property
    def config(self) -> Dict[str, Any]:
        return getattr(self._client, "config", {})

    @property
    def node(self) -> Optional[str]:
        return getattr(self._client, "node", None)

    @node.setter
    def node(self, value: Optional[str]) -> None:
        if self._client:
            self._client.node = value

    @property
    def quality_optimized(self) -> bool:
        return getattr(self._client, "quality_optimized", False)

    @quality_optimized.setter
    def quality_optimized(self, value: bool) -> None:
        if self._client:
            self._client.quality_optimized = value

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """Native ADK BaseLlm asynchronous generation."""
        prompt_parts = []
        for content in (llm_request.contents or []):
            for part in (content.parts or []):
                if getattr(part, "text", None):
                    prompt_parts.append(part.text)

        prompt = "".join(prompt_parts)
        trace_id = self._trace_id
        # ADK 2.11's LlmRequest has no `custom_metadata`; read it defensively so a missing trace id never aborts the call.
        meta = getattr(llm_request, "custom_metadata", None)
        if not trace_id and isinstance(meta, dict):
            trace_id = meta.get("trace_id")

        # Execute through the centralized routing and resilience engine
        if hasattr(self._client, "generate"):
            res = self._client.generate(prompt, trace_id=trace_id)
            text = res.text
            pt = res.prompt_tokens
            ct = res.completion_tokens
            lat = res.latency_ms
            cost = res.cost_usd
            mock = res.mock
            model_name = res.model
        elif hasattr(self._client, "call_model"):
            text = self._client.call_model(prompt)
            pt, ct, lat, cost, mock = 0, 0, 0.0, 0.0, False
            model_name = getattr(self._client, "model", self.model)
        elif callable(self._client):
            res = self._client(prompt)
            text = res if isinstance(res, str) else getattr(res, "text", str(res))
            pt, ct, lat, cost, mock = 0, 0, 0.0, 0.0, False
            model_name = getattr(self._client, "model", self.model)
        else:
            raise RuntimeError(f"Client {type(self._client)} does not implement generate or call_model")

        resp_content = types.Content(
            role="model",
            parts=[types.Part(text=text)],
        )

        usage = types.GenerateContentResponseUsageMetadata(
            prompt_token_count=pt,
            candidates_token_count=ct,
            total_token_count=pt + ct,
        )

        custom_meta = {
            "model": model_name,
            "latency_ms": lat,
            "cost_usd": cost,
            "mock": mock,
        }

        yield LlmResponse(
            content=resp_content,
            usage_metadata=usage,
            custom_metadata=custom_meta,
            finish_reason=types.FinishReason.STOP,
            partial=False,
        )

    def generate_request(self, llm_request: LlmRequest, trace_id: Optional[str] = None) -> LlmResponse:
        """Synchronously invokes the gateway using a native ADK LlmRequest, returning a native LlmResponse."""
        if trace_id:
            self._trace_id = trace_id

        async def _run() -> LlmResponse:
            resp: Optional[LlmResponse] = None
            async for r in self.generate_content_async(llm_request):
                resp = r
            if resp is None:
                raise RuntimeError("No response returned from ADKModelGateway.")
            return resp

        return run_coro_sync(_run())

    def generate(self, prompt: str, trace_id: Optional[str] = None) -> LLMResult:
        """Generates content via an ADK LlmRequest, returning an LLMResult for backward-compatible call sites."""
        req = LlmRequest(
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            model=self.model,
        )
        resp = self.generate_request(req, trace_id=trace_id)

        text = ""
        if resp.content and resp.content.parts:
            text = "".join(p.text for p in resp.content.parts if p.text)

        meta = resp.custom_metadata or {}
        usage = resp.usage_metadata
        pt = getattr(usage, "prompt_token_count", 0) if usage else 0
        ct = getattr(usage, "candidates_token_count", 0) if usage else 0

        return LLMResult(
            text=text,
            model=meta.get("model", self.model),
            prompt_tokens=pt,
            completion_tokens=ct,
            latency_ms=meta.get("latency_ms", 0.0),
            cost_usd=meta.get("cost_usd", 0.0),
            mock=meta.get("mock", False),
        )

    def call_model(self, prompt: str, trace_id: Optional[str] = None) -> str:
        """Simple text generation string interface."""
        return self.generate(prompt, trace_id=trace_id).text

    @classmethod
    def supported_models(cls) -> list[str]:
        return ["gateway"]
