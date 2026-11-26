"""Gemini built-in safety filters are set explicitly on every Gemini request (app/workflow/model_client.py)."""
from google.adk.models import LlmRequest
from google.genai import types as gtypes

from app.workflow.model_client import gemini_safety_config


def _thresholds() -> dict:
    cfg = gemini_safety_config()
    return {s.category: s.threshold for s in cfg.safety_settings}


def test_all_five_harm_categories_are_set():
    assert set(_thresholds()) == {
        gtypes.HarmCategory.HARM_CATEGORY_HARASSMENT,
        gtypes.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        gtypes.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        gtypes.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        gtypes.HarmCategory.HARM_CATEGORY_JAILBREAK,
    }


def test_jailbreak_is_blocked_at_the_lowest_threshold_and_dangerous_content_is_relaxed():
    t = _thresholds()
    assert t[gtypes.HarmCategory.HARM_CATEGORY_JAILBREAK] == gtypes.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE
    assert t[gtypes.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT] == gtypes.HarmBlockThreshold.BLOCK_ONLY_HIGH


def test_config_attaches_to_an_adk_llm_request():
    req = LlmRequest(model="gemini-2.5-flash", config=gemini_safety_config())
    assert len(req.config.safety_settings) == 5
