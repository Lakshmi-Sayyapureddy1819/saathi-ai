"""Emergency alerts to the care team (the escalation that follows a RED_CRISIS in the safety gate).

Real channels, all with a free tier:
  Telegram bot   TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID                      (free; message the on-call care-team chat)
  SMTP e-mail    SMTP_HOST [SMTP_PORT SMTP_USER SMTP_PASSWORD] ALERT_EMAIL_FROM ALERT_EMAIL_TO   (e.g. Gmail app password)
  Twilio SMS     TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_FROM ALERT_SMS_TO (optional; trial accounts are free)
Every configured channel is tried (not "first wins"): an emergency should reach people by every route available.

Properties that matter for a safety path:
- Never blocks the member's reply: delivery runs on a small worker pool; the gate returns immediately.
- Never raises into the gate. Each attempt (with one retry) is recorded in the audit table; if no channel delivers, a
  CRITICAL log line says so and the audit row status is `failed` (visible in /api/readiness as `alerts_failed`).
- Privacy: the message carries the member id, the crisis CATEGORY and an opaque tag. Never the member's own words.
- With no channel configured it logs only (allowed in development; APP_ENV=production refuses to start, see config.py).
"""
import logging
import os
import smtplib
import time
from concurrent.futures import Future, ThreadPoolExecutor
from email.message import EmailMessage
from typing import List, Optional, Protocol

import requests
from pydantic import BaseModel, ConfigDict

from app.persistence.store import AlertRow, Store

ATTEMPT_TIMEOUT_S = float(os.getenv("ALERT_TIMEOUT_SECONDS", "8"))
RETRY_DELAY_S = 1.0
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alerts")


class Channel(Protocol):
    name: str

    def send(self, text: str) -> None:
        """Deliver or raise. No return value: success means no exception."""


class TelegramChannel:
    name = "telegram"

    def __init__(self, token: str, chat_id: str):
        self.token, self.chat_id = token, chat_id

    def send(self, text: str) -> None:
        r = requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                          json={"chat_id": self.chat_id, "text": text}, timeout=ATTEMPT_TIMEOUT_S)
        if r.status_code != 200:
            raise RuntimeError(f"Telegram returned {r.status_code}")  # body omitted: the URL carries the bot token


class SmtpChannel:
    name = "email"

    def __init__(self, host: str, port: int, user: str, password: str, sender: str, to: str):
        self.host, self.port, self.user, self.password, self.sender, self.to = host, port, user, password, sender, to

    def send(self, text: str) -> None:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = "[Saathi] URGENT: member safety escalation", self.sender, self.to
        msg.set_content(text)
        with smtplib.SMTP(self.host, self.port, timeout=ATTEMPT_TIMEOUT_S) as smtp:
            if self.port != 25:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)


class TwilioChannel:
    name = "twilio_sms"

    def __init__(self, sid: str, token: str, sender: str, to: str):
        self.sid, self.token, self.sender, self.to = sid, token, sender, to

    def send(self, text: str) -> None:
        r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json",
                          data={"To": self.to, "From": self.sender, "Body": text[:1500]},
                          auth=(self.sid, self.token), timeout=ATTEMPT_TIMEOUT_S)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Twilio returned {r.status_code}")


def configured_channels() -> List[Channel]:
    env = os.environ.get
    out: List[Channel] = []
    if env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"):
        out.append(TelegramChannel(env("TELEGRAM_BOT_TOKEN", ""), env("TELEGRAM_CHAT_ID", "")))
    if env("SMTP_HOST") and env("ALERT_EMAIL_TO") and env("ALERT_EMAIL_FROM"):
        out.append(SmtpChannel(env("SMTP_HOST", ""), int(env("SMTP_PORT", "587")), env("SMTP_USER", ""),
                               env("SMTP_PASSWORD", ""), env("ALERT_EMAIL_FROM", ""), env("ALERT_EMAIL_TO", "")))
    if env("TWILIO_ACCOUNT_SID") and env("TWILIO_AUTH_TOKEN") and env("TWILIO_FROM") and env("ALERT_SMS_TO"):
        out.append(TwilioChannel(env("TWILIO_ACCOUNT_SID", ""), env("TWILIO_AUTH_TOKEN", ""), env("TWILIO_FROM", ""),
                                 env("ALERT_SMS_TO", "")))
    return out


def configured_channel_names() -> List[str]:
    return [c.name for c in configured_channels()]


class AlertAttempt(BaseModel):
    model_config = ConfigDict(frozen=True)
    channel: str
    ok: bool
    detail: str = ""


class AlertReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    delivered: bool
    attempts: List[AlertAttempt]


def _safe(text: str) -> str:
    return text.replace(os.getenv("TELEGRAM_BOT_TOKEN", "\0"), "<token>")[:160]


def deliver(member_id: str, category: str, text: str, channels: Optional[List[Channel]] = None,
            store: Optional[Store] = None, sleep=time.sleep) -> AlertReport:
    """Try every channel (one retry each), record every attempt, never raise."""
    channels = configured_channels() if channels is None else channels
    attempts: List[AlertAttempt] = []

    def audit(channel: str, status: str, detail: str) -> None:
        if store is not None:
            try:
                store.record_alert(AlertRow(member_id=member_id, category=category, channel=channel, status=status,
                                            detail=detail, at=time.time()))
            except Exception:  # noqa: BLE001 - auditing must not break the alert itself
                logging.exception("could not write the alert audit row")

    if not channels:
        logging.critical("EMERGENCY ALERT (no delivery channel configured, log only): %s", text)
        audit("log", "no_channel", "no real alert channel configured")
        return AlertReport(delivered=False, attempts=[])
    for ch in channels:
        ok, detail = False, ""
        for attempt in (1, 2):
            try:
                ch.send(text)
                ok, detail = True, f"attempt {attempt}"
                break
            except Exception as e:  # noqa: BLE001 - one bad channel must not stop the others
                detail = _safe(f"{type(e).__name__}: {e}")
                if attempt == 1:
                    sleep(RETRY_DELAY_S)
        attempts.append(AlertAttempt(channel=ch.name, ok=ok, detail=detail))
        audit(ch.name, "sent" if ok else "failed", detail)
    delivered = any(a.ok for a in attempts)
    if not delivered:
        logging.critical("EMERGENCY ALERT NOT DELIVERED by any channel for member %s (%s): %s", member_id, category,
                         "; ".join(f"{a.channel}: {a.detail}" for a in attempts))
    return AlertReport(delivered=delivered, attempts=attempts)


def dispatch_emergency(member_id: str, category: str, tag: str, wait: bool = False,
                       channels: Optional[List[Channel]] = None, store: Optional[Store] = None) -> Optional[Future]:
    """Queue an emergency alert and return at once (the member's reply never waits on a provider).
    `wait=True` blocks until delivery finished (tests, scripts) and returns the finished future."""
    text = (f"[Saathi SAFETY] RED CRISIS for member {member_id} ({category}). Please contact the member now. "
            f"ref={tag} at {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    if store is None:
        try:
            from app.persistence.store import get_store
            store = get_store()
        except Exception:  # noqa: BLE001 - no database must not stop the alert
            store = None
    fut = _POOL.submit(deliver, member_id, category, text, channels, store)
    if wait:
        fut.result()
    return fut
