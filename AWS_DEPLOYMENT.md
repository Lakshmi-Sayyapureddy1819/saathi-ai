# Saathi Care AI on AWS: what was deployed, every step taken, and what is verified

Written 2026-11-23. Times are UTC with IST (UTC+5:30) in brackets. The AWS account ID is deliberately left out of this file; do not
paste it, secrets, or the `.env` into Git.

## 1. At a glance

| Item | Value |
|---|---|
| **AWS Region** | **Asia Pacific (Sydney), `ap-southeast-2`**. Everything is created here. CloudFront is a global service (its console lives under `us-east-1`) but its content is served from this Region's origin. |
| **Account type** | New AWS experience ("project"), signed in with a social provider through `aws login` (profile `saathi-aws`) |
| **Plan and credits** | **Free plan, status ACTIVE, $100.00 USD in credits remaining** (balance read from `aws freetier get-account-plan-state` on 2026-11-23, after the deployment). Credits **expire 2027-05-23**. See section 2. |
| **Public URL (HTTPS)** | https://d1a1ddkuv955vw.cloudfront.net |
| **Stack** | `saathi-care-demo` (CloudFormation), `CREATE_COMPLETE`, created 08:44 UTC (14:14 IST) |
| **Server** | EC2 `i-056bc0473e2d4ec4d`, `t4g.small` (2 vCPU ARM, 2 GiB), Elastic IP 3.104.68.23 |
| **Secrets** | `saathi-care/demo` (read by the app) and `saathi-care/env-full` (full `.env` backup, **not** read by the app) |
| **Estimated cost** | about **$22.8/month (about ₹2,116)**, covered by the credits |
| **State** | Deployed, redeployed once (09:03 UTC, 14:33 IST), healthy, smoke-tested through the public URL. Not load tested. |

## 2. Region and credits (what they mean for you)

- **Region:** `ap-southeast-2` (Sydney) is the Region of your AWS project. Projects on the new AWS experience share one Region and cannot
  create Regional resources elsewhere, so no other Region was used. The AWS Agent Toolkit service itself only exists in `us-east-1`,
  which is why that one setup step used `us-east-1`; it created nothing billable for this app.
- **Credits:** the account is on the **Free plan with $100 in credits**. Usage is charged against the credits first. At about $22.8/month
  the credits last roughly **4.4 months**, but they **expire on 2027-05-23** regardless. After the credits or the plan end, normal charges
  apply to your payment method, or the account is limited, depending on your plan settings; check `https://settings.aws.com/`.
- **Free plan service list:** only some services are allowed. EC2, ECS, ECR, load balancers, CloudFront, S3, Secrets Manager, Systems
  Manager and CloudWatch are allowed; **App Runner is not**, which is why it was not used. A separate "spend limit" policy can block new
  compute if a limit you set is exceeded; none is set by this deployment.
- **Credit balance after deployment:** $100.00, but AWS billing data lags up to about 24 hours, so the real consumption will show
  later. Check **AWS Settings > Billing** and **Cost Explorer**.
- **Not covered by AWS credits:** model usage on Google (Gemini) or OpenAI. That is billed by those providers.

## 3. Everything that was done, in order

### A. Account and tooling setup
1. **Installed AWS CLI v2** (2.42.1) for the current user on Windows. The installer was downloaded, its contents skimmed (it only contacts
   `awscli.amazonaws.com`), and its Authenticode signature verified as signed by AWS before it ran.
2. **Signed in:** `aws configure set region ap-southeast-2` then `aws login --profile saathi-aws`. A browser window opened and you signed in;
   credentials last 12 hours and can be renewed for 90 days.
3. **Verified:** `aws sts get-caller-identity` returned the project account.
4. **Agent Toolkit for AWS:** `aws configure agent-toolkit --yes --region us-east-1 --profile saathi-aws` installed 25 AWS skills and
   configured the AWS MCP server for Claude Code, Cursor and Gemini CLI. A required follow-up added
   `AWS_MCP_PROXY_PROFILES=saathi-aws` to each `aws-mcp` entry (otherwise the server cannot find credentials). The new-experience AWS
   rules were written to `~/.claude/CLAUDE.md` (a new file; the repo's `CLAUDE.md` was left untouched).

### B. Inspection before any AWS resource existed
5. Read the repository: no Dockerfile, compose or nginx existed; FastAPI backend, React/Vite frontend, SQLite persistence, and
   `InMemorySessionService` for ADK. Findings that shaped the design:
   - ADK sessions and per-session locks live **in process memory**, and state is **one SQLite file**, so the backend can only run as
     **one instance**. After a restart normal chats recover (re-seeded from SQLite); an in-flight coordinator approval is lost, and the app
     already tells the member so.
   - The frontend calls relative `/api/...` when `VITE_API_URL` is empty, so one origin can serve both (no CORS).
   - Voice needs HTTPS (browser microphone rule).
   - Docker is **not installed on the development machine**, so images could not be built or tested locally.
6. Checked the account: Free plan, $100 credits, allowed services, and that no EC2 instances, S3 buckets or CloudFormation stacks existed
   (nothing was touched). A `t4g.small` `--dry-run` returned `DryRunOperation` (would succeed). Default VPC present.
7. Priced everything from the **AWS Pricing API** for `ap-southeast-2` (not from memory): `t4g.small` $0.0212/h, gp3 $0.096/GiB-month,
   public IPv4 $0.005/h, Secrets Manager $0.40/secret, ALB $0.0252/h. INR conversion used a live rate of 92.75 per USD.

### C. Architecture decision and your approval
8. Compared a one-instance EC2 + CloudFront design with ECS Fargate + ALB. Recommended **EC2 + CloudFront** (Fargate would add an ALB, about
   $31/month alone, and gain nothing for a single-instance app).
9. **You approved** Option 1 and chose the secrets policy: OpenAI + Gemini + Langfuse keys only, **no Telegram** (so a test emergency can
   never page your real care-team chat).

### D. Preparation (files created or changed in the repo)
10. Created: `Dockerfile` (backend, non-root, one worker), `Dockerfile.frontend` (Vite build then nginx), `deploy/nginx.conf.template`,
    `.dockerignore`, `docker-compose.yml` (local production-like run, untested), `deploy/uvicorn_log_config.json` + `app/logging_json.py`
    (JSON logs), `deploy/cloudformation.yaml`, `deploy/host/run.sh` (runs on the server), `deploy/deploy.ps1` (Deploy / Update / Status /
    Teardown), and this document. Edited: `app/api.py` (flush trace spans on graceful shutdown), `.env.example`, `README.md`.
11. **Bugs found and fixed on the way:** `resolve_date` silently turned any explicit date ("25 November") into tomorrow (now parses dates and
    weekdays, `tests/test_explicit_dates.py`); an earlier `/api/readiness` that said "ready" while the lab partner was unreachable;
    a bare "yes" after a booking got "I didn't catch that".

### E. Checks before deploying (nothing billable yet)
12. `pytest tests`: **554 passed**. Frontend typecheck clean; production `vite build` with empty `VITE_API_URL`; a scan of the bundle found no
    `127.0.0.1:8000` and no key patterns.
13. CloudFormation: AWS `validate-template` and `cfn-lint` both pass (they caught an unquoted-comma YAML error, fixed). The four CloudFront
    managed-policy IDs used were confirmed real through the API.
14. Started the backend exactly as the container will run it (production mode, `ALLOW_SIMULATORS=1`, one worker, JSON logs): health ok;
    `/api/readiness` honest about simulated parts; CORS limited to the configured origin; chat, emergency, booking, 401/404/422 handling all
    passed; no member message text appeared in the logs.

### F. Deployment attempts
15. **Attempt 1 failed before creating anything:** Windows PowerShell 5.1 treated the expected "stack does not exist" message as a fatal
    error. Fixed in the script.
16. **Attempt 2 created only the secret `saathi-care/demo`, then failed:** unquoted `Name=isDefault,Values=true` reached AWS as a broken filter.
    Fixed by quoting.
17. **Attempt 3** (08:44 UTC / 14:14 IST): secret reused, source tarball built (0.4 MB, 146 files, confirmed to contain no `.env`, `*.db`
    or `*.log`), stack created, tarball uploaded to the stack's private bucket. At your request ("I will deploy") I **stopped my script**;
    CloudFormation kept running by itself and you chose to **keep the stack**.
18. The stack finished: all 10 resources `CREATE_COMPLETE`. The host then installed Docker, built both images, and started the containers at
    08:49 UTC (14:19 IST). No dedicated person watched the build; the first successful health check came a few minutes later.

### G. After deployment
19. **Verified through the public URL** (see section 7). Also confirmed on the host over SSM: both containers up, backend healthy.
20. **Stored your whole `.env`** as the separate secret `saathi-care/env-full` (16 non-empty variables; values never printed). The app host's
    role cannot read it.
21. **Redeploy** (`deploy.ps1 -Action Update`, 09:03 UTC / 14:33 IST): code shipped to the host, images rebuilt, containers recreated, backend
    healthy again, smoke test passed. The script crashed **at the very end** only because Windows could not print a "✓" from the build log (the
    deployment itself had succeeded). Fixed by setting `PYTHONUTF8=1` in the script.

## 4. What is running, and why

```
Browser --HTTPS--> CloudFront (*.cloudfront.net certificate, HTTP->HTTPS redirect, security headers)
                      |  /api/*    not cached, Authorization forwarded, 60 s origin timeout (slow model turns)
                      |  /assets/* cached 1 year;  / (index.html) never cached
                      +--HTTP:80 + secret header X-Origin-Verify--> EC2 t4g.small (Amazon Linux 2023, ARM)
                                                                    ├─ nginx container: React build + proxy /api
                                                                    └─ FastAPI container: ONE uvicorn worker, SQLite on encrypted 30 GiB EBS
Secrets Manager --(host IAM role, at deploy time)--> root-only env files on the host (never in an image or in Git)
CloudWatch Logs /saathi/saathi-care-demo (14 days) <-- both containers, JSON lines
```

- **Why one instance:** ADK sessions and locks are in memory and state is one SQLite file (section 3, step 5).
- **Why CloudFront:** HTTPS without a domain (needed for the microphone) and one origin for UI and API.
- **Why plain HTTP from CloudFront to the server:** a custom domain and certificate would be needed to encrypt that hop; it stays inside AWS.
  The server is reachable **only** from CloudFront (security group restricted to CloudFront's address list, plus a secret header that nginx
  checks). A direct request to the server's IP gets no response.

## 5. What was configured (names only; values are never shown)

Secret **`saathi-care/demo`**, read by the app host. It contains `GEMINI_API_KEY`, `OPENAI_API_KEY`, `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` (copied from your `.env`) and two generated values, `COORDINATOR_TOKEN` and `ORIGIN_VERIFY`.

Added by the host's `deploy/host/run.sh`: `APP_ENV=production`, `ALLOW_SIMULATORS=1`, `LAB_BACKEND=simulator`, `LAB_FAILURE_RATE=0`,
`FRONTEND_ORIGINS=https://d1a1ddkuv955vw.cloudfront.net`, `DATABASE_URL=sqlite:////data/saathi.db`, `TRACE_FILE=/data/traces.jsonl`,
`LANGFUSE_CAPTURE_CONTENT=false`.

**Deliberately not given to the app:** Telegram, SMTP and Twilio keys (a public-demo emergency test must never page a real channel),
`LAB_API_URL`/`LAB_API_KEY` (the cloud uses the built-in simulated lab), Redis.

Secret **`saathi-care/env-full`** holds all 16 non-empty `.env` variables as a backup. Retrieve it only when needed:
`aws secretsmanager get-secret-value --secret-id saathi-care/env-full --region ap-southeast-2 --profile saathi-aws --query SecretString --output text`

## 6. AWS resources and where to see them in the console

| Resource | Name / ID | Console |
|---|---|---|
| CloudFormation stack | `saathi-care-demo` | https://ap-southeast-2.console.aws.amazon.com/cloudformation/home?region=ap-southeast-2#/stacks?filteringText=saathi-care-demo |
| EC2 instance | `i-056bc0473e2d4ec4d` | https://ap-southeast-2.console.aws.amazon.com/ec2/home?region=ap-southeast-2#InstanceDetails:instanceId=i-056bc0473e2d4ec4d |
| CloudFront distribution | `E1F9CMLOPUXFA1` | https://us-east-1.console.aws.amazon.com/cloudfront/v4/home#/distributions/E1F9CMLOPUXFA1 |
| Log group | `/saathi/saathi-care-demo` | https://ap-southeast-2.console.aws.amazon.com/cloudwatch/home?region=ap-southeast-2#logsV2:log-groups/log-group/$252Fsaathi$252Fsaathi-care-demo |
| Secrets | `saathi-care/demo`, `saathi-care/env-full` | https://ap-southeast-2.console.aws.amazon.com/secretsmanager/listsecrets?region=ap-southeast-2 |
| S3 bucket (release tarball) | `saathi-care-demo-sourcebucket-we9ghfy3ekh9` | https://s3.console.aws.amazon.com/s3/buckets/saathi-care-demo-sourcebucket-we9ghfy3ekh9?region=ap-southeast-2 |
| Billing, credits, spend limit | AWS Settings | https://settings.aws.com/ |

Also created by the stack: Elastic IP, security group, IAM role and instance profile, bucket policy. Open the stack's **Resources** tab for
all 10. There is no SSH; to open a shell use EC2 > the instance > **Connect** > **Session Manager**.

## 7. Cost (estimate, not a bill)

| Item | Basis | USD/month | INR/month (92.75 per USD) |
|---|---|---|---|
| EC2 `t4g.small` | $0.0212/h × 730 | 15.48 | 1,436 |
| EBS gp3 30 GiB, encrypted | $0.096/GiB | 2.88 | 267 |
| Public IPv4 (Elastic IP) | $0.005/h | 3.65 | 339 |
| Secrets Manager, 2 secrets | $0.40 each | 0.80 | 74 |
| CloudFront, CloudWatch Logs | assumed inside free allowances | 0 | 0 |
| **Total** | | **about 22.81** | **about ₹2,116** |

The root disk is 30 GiB (not the 20 GiB first quoted) because image builds need the room; the second secret was added at your request.
Variable charges: model-provider usage (billed by Google/OpenAI, not AWS), CloudFront or log volume above the free allowances. A **stopped
instance still bills for the disk and IP** (about $6.5/month); a forgotten stack keeps billing.

## 8. What has been verified (real results) and what has not

| Check | Result |
|---|---|
| `pytest tests` before deploying | 554 passed |
| Frontend typecheck, production build, bundle scan | clean; no localhost URL or key patterns in the bundle |
| CloudFormation `validate-template`, `cfn-lint` | pass |
| Stack | `CREATE_COMPLETE`, 10/10 resources |
| `/api/health` through the public URL | `{"status":"ok"}`, also after the redeploy |
| `/api/readiness` | `environment: production`, `ready: true`, `problems: []`; lab partner and emergency alerts shown as **simulated** |
| Page `/` | 200 (React app served) |
| HTTP to HTTPS | 301 redirect |
| Security headers | HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` present |
| Direct access to the server's IP | no response (blocked; only CloudFront can reach it) |
| Wellness answer, Hinglish answer | worked |
| Emergency message | deterministic emergency response with helplines in 0.4 s; no external alert sent |
| Medicine request / prompt injection | refused diagnosis with a lab-test pointer; no prompt leaked |
| Booking with explicit "yes" | worked; "25 November" kept as 25 November; a second "yes" created no duplicate; booking shows in the session |
| Auth and errors | 401 without token; coordinator endpoint 401 without token; 500-char limit enforced; unknown origin gets no CORS header |
| Host | both containers up, backend `healthy`; about 460 MiB of 1.8 GiB used (backend about 96-122 MiB), so `t4g.small` is enough |
| Redeploy | SSM command `Success`, containers recreated, health 200, smoke test passed |
| **Not verified** | A **human browser pass** of the public site (console errors, network tab, mobile layout, **voice with a real microphone**); whether **Langfuse** actually connected (no log line either way); log entries in **CloudWatch** (checked via `docker logs`, not the CloudWatch console); graceful shutdown on `docker stop`; `docker compose up`; behaviour under load |

## 9. Operating it

```powershell
aws login --profile saathi-aws --region ap-southeast-2             # if the 12-hour session has expired
.\deploy\deploy.ps1 -Action Status                                 # stack state + SiteUrl, InstanceId, bucket
.\deploy\deploy.ps1 -Action Update                                 # ship current code to the host, rebuild, restart (about a minute of downtime)
.\deploy\deploy.ps1 -Action Teardown -ConfirmTeardown              # delete the stack; never runs without the switch
```

- `-Action Deploy` refuses to run while the stack exists; it is only for a fresh start.
- **Teardown deletes all sessions and bookings** (the disk is deleted with the instance) and does **not** delete the secrets; the command to
  delete them is printed.
- **Rollback:** there is no versioned release store. `git checkout <good commit>` and run `-Action Update`; if the host is broken, Teardown and Deploy.
- **Host checks without SSH** (JSON parameter file avoids PowerShell quoting problems):
  `aws ssm send-command --instance-ids i-056bc0473e2d4ec4d --document-name AWS-RunShellScript --parameters file://cmds.json ...`
- **Logs:** CloudWatch group `/saathi/saathi-care-demo`, streams `backend` and `web` (JSON lines).

## 10. Troubleshooting

| Symptom | Likely cause and action |
|---|---|
| 502/504 for the first 5-10 minutes after a deploy | The host is still building images. Wait; then check `/var/log/saathi-userdata.log` and `/var/log/saathi-run.log` over SSM. |
| Build killed ("Killed") | Out of memory on 2 GiB; redeploy with `-InstanceType t4g.medium` (+$15.47/month). Measured use is far below the limit, so this is unlikely. |
| Chat says the model is unavailable | A provider key is wrong. `GET /api/llm-status` shows per-model failures. |
| 403 on the site root | The `X-Origin-Verify` value in the secret and CloudFront disagree (secret changed after stack creation); re-run `Update` or update the stack. |
| Old UI after `Update` | Hard refresh; `index.html` is never cached and `/assets/` files are content-hashed. |
| Script prints an encoding error at the end | Fixed (`PYTHONUTF8=1`); the deployment itself had already succeeded. |

## 11. Security notes

- Inbound is only TCP 80 from CloudFront's address list plus a secret header; no SSH; no `0.0.0.0/0` ingress.
- IMDSv2 required, metadata hop limit 1 (containers cannot read instance credentials), encrypted EBS, private encrypted S3 bucket with a
  TLS-only policy, 14-day log retention.
- The host role can read **one** secret, read the release object, write its own log group, and use SSM Session Manager.
- The backend runs as a non-root user; `.dockerignore` keeps `.env`, `*.db`, `*.log`, tests and docs out of builds.
- No member message text in logs (the app logs redacted markers; checked by searching a test run's log).
- The secret values exist as plain text in two root-only files on the host (`/opt/saathi/*.env`). Anyone with root or SSM access can read them.
  One of my commands earlier printed your local `LAB_API_KEY` value in this chat session; it only protects a local service, but consider
  rotating it.
- Use simulated members only. The lab partner is the in-process simulator and emergency alerts are log-only; both are labelled in
  `/api/readiness`.

## 12. Known issues and limits

1. **Gemini key returns HTTP 403** (on your machine and in the cloud). Every reply is served by the **OpenAI fallback**, and the semantic
   cache's Gemini embeddings also fail (it falls back to word-overlap matching). Replace the key, update `saathi-care/demo`, then run `Update`.
2. One instance, SQLite, in-memory ADK sessions: no scaling, no high availability, no backups. A restart drops only an in-flight
   coordinator approval.
3. CloudFront-to-server traffic is plain HTTP inside AWS; no custom domain, WAF, access logs, alarms or autoscaling.
4. The simulated lab failure rate is 0 on the host (the brief's 15% needs `LAB_FAILURE_RATE=0.15`).
5. Not load tested; the 15-million-interactions-per-month design in `ARCHITECTURE.md` describes a different, larger architecture.
6. The wellness answer to "gentle yoga routine for better sleep" starts with "I don't have that information in our program library" before
   suggesting a practice. That is existing behaviour and was not changed.
7. Nothing in this work has been committed to Git.
