"""Redaction of user-supplied text before it reaches logs, stdout or trace spans (health data = sensitive).

`redact()` keeps operationally useful facts (length, a correlation tag) without the content. The tag is an HMAC
with a random per-process salt, so it lets you correlate two log lines from the same run but cannot be used to
dictionary-check a short health message offline, and it changes on restart.
"""
import hashlib
import hmac
import os

_SALT = os.urandom(16)


def redact(text: str) -> str:
    tag = hmac.new(_SALT, text.encode("utf-8"), hashlib.sha256).hexdigest()[:8]
    return f"<redacted len={len(text)} tag={tag}>"
