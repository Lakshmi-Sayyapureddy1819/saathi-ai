"""Hermetic tests: never call real LLM/embedding APIs or write traces to the real log.

load_dotenv() does not override variables that already exist, so blanking them here wins over .env.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY",
           "LANGFUSE_CAPTURE_CONTENT"):  # a developer's .env must never switch raw-text capture on in tests
    os.environ[_k] = ""
os.environ["TRACE_FILE"] = os.path.join(tempfile.gettempdir(), "saathi_test_traces.jsonl")
os.environ["LAB_FAILURE_RATE"] = "0"
# A developer's .env (real alert channels, lab partner, coordinator token) must never leak into tests: tests must not send
# real alerts or call a real service.
for _k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "ALERT_EMAIL_TO", "ALERT_EMAIL_FROM", "TWILIO_ACCOUNT_SID",
           "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "ALERT_SMS_TO", "LAB_API_URL", "LAB_API_KEY", "COORDINATOR_TOKEN",
           "REDIS_URL", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
    os.environ[_k] = ""
os.environ["LAB_BACKEND"] = "simulator"
os.environ["FRONTEND_ORIGINS"] = "http://localhost:5173,http://127.0.0.1:5173"
os.environ["ALLOW_MOCK_LLM"] = "1"          # tests exercise the flagged-mock path; production forbids it
os.environ["DATABASE_URL"] = "sqlite:///:memory:"  # never touch the real database file
os.environ.pop("APP_ENV", None)
