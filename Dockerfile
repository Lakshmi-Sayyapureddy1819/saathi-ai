# Backend image (FastAPI + Google ADK 2.11). Secrets are NEVER baked in: they arrive as environment variables at run time.
# ECR Public mirror avoids Docker Hub anonymous-pull rate limits on shared cloud IPs.
FROM public.ecr.aws/docker/library/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Only what the backend reads at run time (see .dockerignore: no .env, no *.db, no logs, no evals).
COPY app ./app
COPY config ./config
COPY prompts ./prompts
COPY data/programs.json data/members.json data/lab_packages.json ./data/
COPY deploy/uvicorn_log_config.json ./deploy/uvicorn_log_config.json

# Non-root user; /data is the persistent volume (SQLite + local trace file).
RUN useradd --system --uid 10001 --home-dir /app saathi && mkdir -p /data && chown -R saathi /data /app
USER saathi
VOLUME ["/data"]

ENV DATABASE_URL=sqlite:////data/saathi.db TRACE_FILE=/data/traces.jsonl APP_ENV=production
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# ONE worker on purpose: ADK sessions and per-session locks live in process memory (see AWS_DEPLOYMENT.md).
CMD ["python", "-m", "uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--timeout-graceful-shutdown", "20", "--log-config", "deploy/uvicorn_log_config.json"]
