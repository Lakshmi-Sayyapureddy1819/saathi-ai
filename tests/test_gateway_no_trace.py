"""Regression: the ADK gateway must work when no trace_id is supplied (the safety gate's LLM stage calls it that way).

ADK 2.11's LlmRequest has no `custom_metadata`; reading it unguarded made every trace-less call raise, which the gate
swallowed, silently disabling its LLM second stage.
"""
from google.adk.models.llm_request import LlmRequest
from google.genai.types import Content, Part

from app.workflow.gateway import ADKModelGateway
from app.workflow.model_client import LLMResult


class _Stub:
    def generate(self, prompt, trace_id=None):
        return LLMResult(text="GREEN_NORMAL", model="stub", prompt_tokens=1, completion_tokens=1,
                         latency_ms=1.0, cost_usd=0.0, mock=False)


def test_gateway_generates_without_trace_id():
    gw = ADKModelGateway(client=_Stub())
    req = LlmRequest(contents=[Content(role="user", parts=[Part(text="hi")])], model="gateway")
    resp = gw.generate_request(req)
    assert resp.content.parts[0].text == "GREEN_NORMAL"
