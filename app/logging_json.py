"""One-line JSON log records for containers (CloudWatch Logs Insights can query these fields).

Enabled by passing `--log-config deploy/uvicorn_log_config.json` to uvicorn; local development keeps the plain format.
Privacy: this formatter only serialises what callers already log. The application never logs member message text (it logs
redacted markers such as `<redacted len=N tag=...>`), and this module does not add request bodies or headers.
"""
import json
import logging
import time


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
