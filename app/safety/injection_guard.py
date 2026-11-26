"""Deterministic input guard against jailbreaks and prompt injection (CLAUDE.md: safety rules are code, not LLM judgement).

Runs in the safety gate AFTER the emergency triage, so a message that also describes a medical emergency still goes to
the emergency path. It only decides whether a *non-emergency* message is trying to change the assistant's rules, reveal
its instructions, or impersonate a system/role. A blocked turn never reaches an LLM.

Privacy: the verdict carries only the rule name, never the user's text (it goes into Langfuse metadata).
"""
import re
from typing import Literal, Optional, Pattern, Tuple

from pydantic import BaseModel, ConfigDict

InjectionRule = Literal[
    "instruction_override", "prompt_disclosure", "persona_override", "role_spoof", "delimiter_spoof",
]


class GuardVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)
    blocked: bool
    rule: Optional[InjectionRule] = None


_W = r"(?:\W+\w+){0,4}?\W+"  # up to four filler words between two key words ("ignore ALL my previous instructions")

_RULES: Tuple[Tuple[InjectionRule, Pattern[str]], ...] = (
    ("instruction_override", re.compile(
        rf"\b(ignore|disregard|forget|override|bypass)\b{_W}"
        r"(instructions?|rules?|prompts?|guidelines?|guardrails?|restrictions?|safeguards?|"
        r"safety\s+(rules|restrictions|guidelines|filters))\b",
        re.I)),
    ("instruction_override", re.compile(
        r"\b(sab|saare|saari|pichle|pehle\s+ke|apne|aapke)\s+(rules|instructions|nirdesh|niyam)\s+"
        r"(bhool|bhul|ignore|chhod|tod)", re.I)),
    ("prompt_disclosure", re.compile(
        rf"\b(reveal|print|repeat|dump|leak|output|display)\b{_W}"
        r"(system\s+prompt|your\s+prompt|hidden\s+prompt|initial\s+prompt|your\s+instructions|"
        r"(internal|hidden|secret|original|underlying)\s+(instructions?|prompts?|rules))", re.I)),
    ("prompt_disclosure", re.compile(
        r"\b(apne|aapke)\s+(rules|instructions|nirdesh)\s+(batao|bataiye|dikhao|dikhaiye)", re.I)),
    ("persona_override", re.compile(
        r"\byou\s+are\s+now\s+(?:an?\s+|the\s+)?\w*\s*(bot|ai|assistant|model|mode|persona|character|dan)\b", re.I)),
    ("persona_override", re.compile(
        r"\bpretend\s+(to\s+be|you\s+are|you're)\b|\bdeveloper\s+mode\b|\bjailbr(eak|oken)\b|\bDAN\s+mode\b|"
        r"\bwith\s+no\s+(rules|restrictions|limits|filters)\b", re.I)),
    ("role_spoof", re.compile(r"^\s*(system|assistant|developer)\s*:", re.I | re.M)),
    ("delimiter_spoof", re.compile(
        r"</?\s*(system|assistant|instructions?|tool_?(result|call)?)\s*>|\[/?INST\]|<\|im_(start|end)\|>|###\s*system",
        re.I)),
)


def check_injection(text: str) -> GuardVerdict:
    """Return a blocked verdict with the first matching rule, or a clean verdict. Pure function, no I/O."""
    for rule, pattern in _RULES:
        if pattern.search(text):
            return GuardVerdict(blocked=True, rule=rule)
    return GuardVerdict(blocked=False)
