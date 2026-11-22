"""Hermetic tests: never call real LLM/embedding APIs or write traces to the real log.

load_dotenv() does not override variables that already exist, so blanking them here wins over .env.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
    os.environ[_k] = ""
os.environ["TRACE_FILE"] = os.path.join(tempfile.gettempdir(), "saathi_test_traces.jsonl")
os.environ["LAB_FAILURE_RATE"] = "0"
