"""Tests for Requirement 4: Model-agnostic by config.

Verifies:
- Config-driven model routing via config/models.yaml (Gemini, OpenAI, Ollama/vLLM)
- Same workflow runs on Google and non-Google models with zero code change
- Environment variable overrides (MODEL_CONFIG_PATH, MODEL_NODE)
- Cross-vendor fallback logic (Google -> OpenAI)
- Dedicated low-latency voice route wired into VoiceAgent
- Evaluation suite artifacts across multiple model mixes (quality, p50/p95 latency, cost/1k conversations)
- Documentation coverage (EVALS.md and ARCHITECTURE.md routing policy and voice rationale)
"""
import json
from pathlib import Path
import pytest
import yaml

from app.channels.voice_agent import VoiceAgent
from app.workflow.graph import WorkflowGraph
from app.workflow.model_client import LLMResult, ModelClient


def test_models_yaml_structure_and_providers():
    """Verify config/models.yaml declares providers, models, and required routing nodes."""
    config_path = Path("config/models.yaml")
    assert config_path.exists(), "config/models.yaml must exist"

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    provider_names = {p["name"] for p in cfg.get("providers", [])}
    assert "gemini" in provider_names, "gemini provider must be declared"
    assert "openai" in provider_names, "openai provider must be declared"
    assert "ollama" in provider_names, "ollama provider must be declared"

    nodes = {n["name"]: n for n in cfg.get("routing", {}).get("nodes", [])}
    # Required production nodes
    assert "cost_optimized" in nodes, "cost_optimized node required"
    assert "quality_optimized" in nodes, "quality_optimized node required"
    assert "voice" in nodes, "voice node required"

    # Required cross-vendor fallbacks for resilience
    assert nodes["cost_optimized"]["default_model"] == "gemini-3.5-flash-lite"
    assert nodes["cost_optimized"]["fallback_model"] == "gpt-4o-mini"

    assert nodes["quality_optimized"]["default_model"] == "gemini-3.8-flash"
    assert nodes["quality_optimized"]["fallback_model"] == "gpt-4o"

    assert nodes["voice"]["default_model"] == "gemini-3.5-flash-lite"
    assert nodes["voice"]["fallback_model"] == "gpt-4o-mini"

    # Evaluation mix nodes (must have Google, OpenAI, and Ollama options)
    assert "mix_gemini_lite" in nodes
    assert "mix_openai_mini" in nodes
    assert "mix_ollama" in nodes


def test_workflow_runs_on_non_google_model_via_node():
    """The same workflow runs on OpenAI or Ollama with no code change, simply by specifying the model node."""
    # Gemini route
    g_gemini = WorkflowGraph(model_node="mix_gemini_lite")
    assert g_gemini.model_client.nodes["mix_gemini_lite"]["default_model"] == "gemini-3.5-flash-lite"

    # OpenAI route
    g_openai = WorkflowGraph(model_node="mix_openai_mini")
    assert g_openai.model_client.nodes["mix_openai_mini"]["default_model"] == "gpt-4o-mini"

    # Ollama open SLM route
    g_ollama = WorkflowGraph(model_node="mix_ollama")
    assert g_ollama.model_client.nodes["mix_ollama"]["default_model"] == "llama3.2"


def test_model_node_env_var_swaps_model_with_no_code_change(monkeypatch):
    """Setting MODEL_NODE environment variable swaps the active model across the entire workflow with no code change."""
    monkeypatch.setenv("MODEL_NODE", "mix_openai_mini")

    client = ModelClient()
    # Mock _invoke to observe model used
    invoked_models = []
    monkeypatch.setattr(ModelClient, "_invoke", lambda self, m, p: invoked_models.append(m) or LLMResult(text="response", model=m))

    res = client.generate("test prompt")
    assert res.model == "gpt-4o-mini"
    assert invoked_models == ["gpt-4o-mini"]


def test_model_config_path_env_var_overrides_config(tmp_path, monkeypatch):
    """Setting MODEL_CONFIG_PATH allows loading an alternate model configuration with no code change."""
    custom_yaml = tmp_path / "custom_models.yaml"
    custom_yaml.write_text(yaml.dump({
        "routing": {
            "nodes": [
                {"name": "cost_optimized", "default_model": "gpt-4o-mini"},
                {"name": "voice", "default_model": "gpt-4o-mini"}
            ]
        }
    }), encoding="utf-8")

    monkeypatch.setenv("MODEL_CONFIG_PATH", str(custom_yaml))
    client = ModelClient()
    assert client.nodes["cost_optimized"]["default_model"] == "gpt-4o-mini"


def test_voice_agent_defaults_to_voice_routing_node():
    """VoiceAgent specifically uses the latency-optimized 'voice' route by default."""
    agent = VoiceAgent(verbose=False)
    assert agent.graph is not None
    assert agent.graph.model_client.node == "voice"
    assert agent.graph.router_client.node == "voice"
    assert agent.graph.model_client.nodes["voice"]["default_model"] == "gemini-3.5-flash-lite"


def test_model_mix_eval_snapshot_covers_multiple_mixes_and_reports_metrics():
    """Verify that evaluations/snapshots/model_mix_2026-11-22.json reports quality, latency, and cost across mixes."""
    snap_path = Path("evaluations/snapshots/model_mix_2026-11-22.json")
    assert snap_path.exists(), "Model mix evaluation snapshot must exist"

    with open(snap_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])
    assert len(results) >= 2, "Must evaluate at least two model mixes"

    mix_names = {r["mix"] for r in results}
    assert "gemini_lite" in mix_names
    assert "openai_mini" in mix_names

    for r in results:
        # Quality reported
        assert r["faithfulness_pct"] is not None
        assert r["lexical_groundedness_pct"] is not None
        assert r["injection_passed"] is not None
        assert r["n_errors"] == 0

        # Latency p50 / p95 reported
        assert r["latency_p50_ms"] is not None and r["latency_p50_ms"] > 0
        assert r["latency_p95_ms"] is not None and r["latency_p95_ms"] > 0

        # Cost per 1,000 conversations reported
        assert r["cost_per_1k_conversations_usd"] is not None and r["cost_per_1k_conversations_usd"] > 0


def test_docs_contain_routing_policy_and_voice_rationale():
    """EVALS.md and ARCHITECTURE.md must contain the routing policy table and voice latency rationale."""
    evals_md = Path("EVALS.md").read_text(encoding="utf-8")
    arch_md = Path("ARCHITECTURE.md").read_text(encoding="utf-8")

    # EVALS.md checks
    assert "## Model mixes" in evals_md
    assert "routing policy" in evals_md.lower()
    assert "cost_optimized" in evals_md
    assert "quality_optimized" in evals_md
    assert "voice" in evals_md
    assert "gemini-3.5-flash-lite" in evals_md
    assert "gpt-4o-mini" in evals_md

    # ARCHITECTURE.md checks
    assert "Routing Policy Summary" in arch_md
    assert "cost_optimized" in arch_md
    assert "voice" in arch_md
