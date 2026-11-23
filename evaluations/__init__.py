# This file makes the 'evaluations' directory a Python package.

import os as _os
_os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")  # eval runs must not write the real DB
_os.environ.setdefault("ALLOW_MOCK_LLM", "1")  # with no API key the evals report N/A for LLM metrics
# Evals run hundreds of red-flag and booking scenarios: they must never message the care team or call a real lab service.
for _k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "ALERT_EMAIL_TO", "ALERT_EMAIL_FROM", "TWILIO_ACCOUNT_SID",
           "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "ALERT_SMS_TO", "LAB_API_URL", "LAB_API_KEY", "REDIS_URL",
           "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
    _os.environ[_k] = ""
_os.environ["LAB_BACKEND"] = "simulator"
