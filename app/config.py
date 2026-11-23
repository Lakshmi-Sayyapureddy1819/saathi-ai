"""Runtime configuration and production readiness.

One place answers "what is real and what is simulated in this deployment?". APP_ENV=production refuses to start while
anything the member or the care team depends on is simulated, so a demo shortcut can never silently reach production.

Environment (all optional in development):
  APP_ENV                  development (default) | production
  ALLOW_MOCK_LLM           1 -> with no API key the model client returns a flagged [MOCK] text (tests / offline demos only)
  ALLOW_SIMULATORS         1 -> permit simulated lab partner / log-only alerts even in production (explicit override)
  DATABASE_URL             sqlite:///data/saathi.db (default)   (the Store is the seam for Postgres later)
  LAB_BACKEND              simulator (default in dev) | http
  LAB_API_URL / LAB_API_KEY / LAB_API_TIMEOUT_SECONDS
  TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID                         free care-team alert channel
  SMTP_HOST [SMTP_PORT SMTP_USER SMTP_PASSWORD] ALERT_EMAIL_FROM ALERT_EMAIL_TO   free e-mail alert channel
  TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_FROM ALERT_SMS_TO  optional SMS channel (trial accounts are free)
"""
import os
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)
    app_env: Literal["development", "production"]
    allow_mock_llm: bool
    allow_simulators: bool
    database_url: str
    lab_backend: Literal["simulator", "http"]
    lab_api_url: str = ""
    coordinator_token_set: bool
    frontend_origins_set: bool


def get_settings() -> Settings:
    """Read the environment every call (cheap), so tests and operators can change it without a restart hook."""
    env = os.getenv("APP_ENV", "development").strip().lower()
    if env not in ("development", "production"):
        raise ValueError(f"APP_ENV={env!r} is invalid; use development or production.")
    backend = os.getenv("LAB_BACKEND", "").strip().lower() or ("http" if os.getenv("LAB_API_URL") else "simulator")
    if backend not in ("simulator", "http"):
        raise ValueError(f"LAB_BACKEND={backend!r} is invalid; use simulator or http.")
    return Settings(
        app_env=env,  # type: ignore[arg-type]
        allow_mock_llm=_flag("ALLOW_MOCK_LLM"),
        allow_simulators=_flag("ALLOW_SIMULATORS", default=env != "production"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/saathi.db"),
        lab_backend=backend,  # type: ignore[arg-type]
        lab_api_url=os.getenv("LAB_API_URL", ""),
        coordinator_token_set=bool(os.getenv("COORDINATOR_TOKEN")),
        frontend_origins_set=bool(os.getenv("FRONTEND_ORIGINS")),
    )


def llm_keys_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))


class ComponentStatus(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    mode: Literal["real", "simulated", "disabled"]
    detail: str = ""


class Readiness(BaseModel):
    """Honest self-description of the deployment. `problems` is what blocks a production start."""
    model_config = ConfigDict(frozen=True)
    environment: Literal["development", "production"]
    ready: bool
    components: List[ComponentStatus]
    problems: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)  # degraded but not start-blocking (e.g. partner API unreachable)


_PARTNER_PROBE: dict = {"at": 0.0, "ok": True}


def _partner_reachable() -> bool:
    """Cheap GET <LAB_API_URL>/health (1.5 s timeout), cached 10 s so frequent readiness polling stays cheap."""
    import time
    if time.time() - _PARTNER_PROBE["at"] < 10:
        return bool(_PARTNER_PROBE["ok"])
    import requests
    url = os.getenv("LAB_API_URL", "").rstrip("/")
    try:
        ok = bool(url) and requests.get(f"{url}/health", timeout=1.5).status_code < 500
    except requests.RequestException:
        ok = False
    _PARTNER_PROBE.update(at=time.time(), ok=ok)
    return ok


def readiness() -> Readiness:
    from app.safety.alerts import configured_channel_names  # local import: alerts imports config
    s = get_settings()
    alerts = configured_channel_names()
    partner_up = _partner_reachable() if s.lab_backend == "http" else True
    comps = [
        ComponentStatus(name="llm", mode="real" if llm_keys_configured() else "disabled",
                        detail="provider key present" if llm_keys_configured() else
                        ("mock replies enabled (ALLOW_MOCK_LLM)" if s.allow_mock_llm else "no key: honest 'unavailable' replies")),
        ComponentStatus(name="database", mode="real", detail=s.database_url.split("///")[0] + "///..."),
        ComponentStatus(name="lab_partner", mode="real" if s.lab_backend == "http" else "simulated",
                        detail=("HTTP adapter" if partner_up else "HTTP adapter: PARTNER UNREACHABLE (bookings will fail and hand off)")
                        if s.lab_backend == "http" else "in-process simulator"),
        ComponentStatus(name="emergency_alerts", mode="real" if alerts else "simulated",
                        detail=", ".join(alerts) if alerts else "log only (no channel configured)"),
        ComponentStatus(name="telephony", mode="simulated",
                        detail="outbound/voice-agent calls use simulated STT/TTS; browser voice uses real Web Speech"),
        ComponentStatus(name="coordinator_auth", mode="real" if s.coordinator_token_set else "disabled",
                        detail="shared secret (no per-person identity)" if s.coordinator_token_set else "console disabled"),
    ]
    problems: List[str] = []
    if s.app_env == "production":
        if not llm_keys_configured():
            problems.append("No LLM provider key (GEMINI_API_KEY or OPENAI_API_KEY).")
        if s.allow_mock_llm:
            problems.append("ALLOW_MOCK_LLM must not be enabled in production.")
        if not s.allow_simulators:
            if s.lab_backend != "http":
                problems.append("LAB_BACKEND must be http (set LAB_API_URL / LAB_API_KEY) or set ALLOW_SIMULATORS=1 explicitly.")
            if not alerts:
                problems.append("No emergency alert channel configured (Telegram, SMTP e-mail or Twilio).")
        if s.lab_backend == "http" and not os.getenv("LAB_API_KEY"):
            problems.append("LAB_API_KEY is not set for the HTTP lab backend.")
        if not s.coordinator_token_set:
            problems.append("COORDINATOR_TOKEN is not set (care-team console would be disabled).")
        if not s.frontend_origins_set:
            problems.append("FRONTEND_ORIGINS is not set (CORS would only allow localhost).")
    warnings = [] if partner_up else [f"Lab partner API at LAB_API_URL is unreachable: members' bookings will fail and hand off to a coordinator. Start it with: python -m services.lab_partner"]
    return Readiness(environment=s.app_env, ready=not problems, components=comps, problems=problems, warnings=warnings)
