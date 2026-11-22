"""Health messages must not appear in logs, stdout or trace spans; operational diagnostics must survive."""
import logging

import app.observability.tracer as tr
from app.observability.redact import redact
from app.safety.triage_gate import evaluate_safety_gate
from app.tools.lab_tools import LabTools
from app.workflow.graph import WorkflowGraph, execute_turn
from app.workflow.state import MemberProfile, UserSessionState

MARK = "ZXQ-PRIVATE-7781"
RED = f"I have severe chest pain and it radiates to my left arm {MARK}"


def _trace_text(trace_id):
    with open(tr.TRACE_FILE, encoding="utf-8") as f:
        return "\n".join(l for l in f if trace_id in l)


def test_redact_hides_content_but_keeps_length_and_correlation():
    r1, r2, r3 = redact("chest pain"), redact("chest pain"), redact("headache")
    assert "chest" not in r1 and "len=10" in r1
    assert r1 == r2 and r1 != r3                              # same text correlates within the process
    assert "<redacted" in r1


def test_red_flag_gate_logs_and_stdout_exclude_the_message(caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        ok, status, payload = evaluate_safety_gate(RED, member_id="MEM_PRIV")
    out = capsys.readouterr()
    everything = caplog.text + out.out + out.err
    assert MARK not in everything and "chest pain" not in everything and "left arm" not in everything
    # ...but operations still get what they need:
    assert "CARDIAC_EMERGENCY" in everything and "MEM_PRIV" in everything and "len=" in everything
    # ...and the member still gets help (behaviour unchanged):
    assert (ok, status) == (False, "RED_CRISIS") and "112" in payload["helplines"].values()


def test_other_crisis_types_are_redacted_too(caplog):
    for text in [f"I want to end my life {MARK}", f"mere seene mein dard hai {MARK}", f"I am coughing blood {MARK}"]:
        with caplog.at_level(logging.DEBUG):
            evaluate_safety_gate(text, member_id="MEM_PRIV")
    assert MARK not in caplog.text and "end my life" not in caplog.text and "coughing blood" not in caplog.text


def test_full_turn_leaves_no_message_text_in_logs_or_traces(caplog):
    s = UserSessionState(channel="chat", member=MemberProfile(member_id="MEM_PRIV2", name="T", age=30), active_node="start")
    with caplog.at_level(logging.DEBUG):
        out, s = execute_turn(RED, s, graph=WorkflowGraph())
    assert "112" in out                                        # emergency response still delivered
    assert MARK not in caplog.text and MARK not in _trace_text(s.trace_id)
    assert "node_emergency" in _trace_text(s.trace_id)         # spans still recorded


def test_booking_tool_spans_do_not_store_the_raw_query_or_reply():
    g = WorkflowGraph()
    g.lab_tools = LabTools(failure_rate=0.0)
    s = UserSessionState(channel="chat", member=MemberProfile(member_id="MEM_PRIV3", name="T", age=30), active_node="start")
    _, s = execute_turn(f"book a senior citizen checkup {MARK}", s, graph=g)
    t1 = s.trace_id                                            # every turn has its own trace id
    _, s = execute_turn(f"female {MARK}", s, graph=g)
    text = _trace_text(t1) + _trace_text(s.trace_id)
    assert MARK not in text and "senior citizen" not in text
    assert "tool:search_packages" in text and "tool:select_package" in text and "<redacted" in text
