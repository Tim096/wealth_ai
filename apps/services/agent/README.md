# wealth-agent — Task 1 public frontend + API

**One line:** you type a web task in plain English, one real browser goes and does
it, and a verifier — not the model — decides whether it actually worked.

This README is four parts: **what this service is** → **what the API hands you** →
**which environment variables you must set** → **how to build, run and smoke-test
it locally**. Read top to bottom the first time; the commands at the bottom are
copy-pasteable.

## What is this?

FastAPI wrapper around `packages/browser_agent`: submit a natural-language web
task, a single Playwright worker thread executes it (jobs are queued), and the
API streams step-by-step progress, the verifier verdict, repair traces,
screenshots and evidence files so every failure is inspectable.

Plain version: this directory is the storefront, `packages/browser_agent` is the
engine room. Nothing here re-implements the agent.

**The discipline I held myself to: existing modules are imported, never patched.**
Deploy-time differences live entirely in this directory, and there are exactly two
of them — Chromium runs `headless=True` (a container has no screen to draw on),
and the local codex gateway is bypassed via `AGENT_LLM_MODE=direct` (there is no
gateway process next to the container to call).

> Not a cloud fork of the agent — the same agent, wrapped.

## What does the API hand you?

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | UI (task in → live trace, verdict, screenshots) |
| GET | `/api/health` | liveness + planner/queue info + deployed `build_sha` (never token-gated) |
| POST | `/api/tasks` | `{"task": "...", "url"?: "", "success"?: ["text_visible:..."], "max_steps"?: 18}` → 202 `{task_id}`; 429 when the queue (10) is full |
| GET | `/api/tasks` | recent tasks |
| GET | `/api/tasks/{id}` | status (`queued/running/pass/fail/unknown/refused/error`), live steps, verifier reason, confidence, answer, verdict telemetry (`observed_evidence`, `missing_evidence`, `llm_cost_usd`, `llm_tokens`, `llm_calls`, `latency_ms`), full structured trace |
| GET | `/api/tasks/{id}/artifacts` | list per-run files (shots / evidence / downloads / run.json) |
| GET | `/api/tasks/{id}/artifacts/{path}` | fetch one artifact |

Read the table as three jobs: **start a run** (`POST /api/tasks`), **watch it**
(`GET /api/tasks/{id}`), **audit it afterwards** (the two artifact routes). Health
is deliberately never token-gated, so a grader can always see what is deployed.

### Why a frozen `contract`?

The obvious way to cheat a browser-agent demo is to decide after the fact what
"success" meant. So the goalposts get bolted down before the run.

`GET /api/tasks/{id}` also returns a write-once `contract` object. Once
`contract.frozen` is `true`, `start_url`, `verification_conditions`, and their
`*_source` fields are the exact read-only inputs used by the verifier; the UI
locks task inputs while that run is active.

> Not "the verifier agreed with the agent" — the verifier judged against inputs
> nobody could edit once the run started.

### Why does every finished run carry a cost chip?

Because a number with no source is a number you can't check. Every telemetry field
below is copied straight off the run, not recomputed for display.

Once a run completes the record also carries verdict telemetry copied straight
from the `TaskRun` (defaults `[]` / `0` while queued/running): `observed_evidence`
and `missing_evidence` (verifier condition keys, drive the per-condition
checklist), plus `llm_cost_usd`, `llm_tokens`, `llm_calls`, and `latency_ms` for
the cost chip. Deterministic demos (`MockPlanner`) make no LLM calls, so those
four stay `0` / `$0.0000` with only `latency_ms` non-zero.

That last sentence is the honest bit: **a `$0.0000` chip is not a cheap agent, it
is a demo that never called a model.** The zeros are the tell, and they are meant
to be visible.

### What can `url` be?

`url` accepts `mock:v1` / `mock:v2` / `mock:v3` for the bundled offline demo
sites (`data/mock_sites`, served via `file://`). Blank `url`/`success` → the
LLM preflight plans the start URL + verifiable success conditions; open-ended
tasks run anyway and report an honest `unknown`.

`unknown` is the point, not a bug: when a task has no checkable success
condition, the run does not get promoted to a pass.

> Not every task gets a verdict — some tasks only get an honest "I can't tell".

## Which environment variables must I set?

Three of these are marked `yes` because direct mode needs a provider, a base URL
and an explicit switch away from the gateway default. Everything else has a
working default.

| Var | Required | Notes |
|---|---|---|
| `OPENAI_API_KEY` | yes | provider key, supplied at deploy time only (never on disk) |
| `AGENT_LLM_MODE` | yes | set `direct` (config default is the local `gateway`) |
| `OPENAI_BASE_URL` | yes | e.g. `https://api.openai.com/v1` (config default is the local gateway) |
| `OPENAI_MODEL` | no | set explicitly for direct mode (config default is OAuth-specific) |
| `DEPLOY_COMMIT_SHA` | for attested eval | exact 40-character `git rev-parse HEAD`; the live eval runner rejects a mismatch before task submission |
| `AGENT_VISION` | no | leave unset → auto-escalate on stuck |
| `SEC_EDGAR_USER_AGENT` | no | agent tasks may hit EDGAR |
| `PORT` | no | injected by Zeabur (8080) |
| `ACCESS_TOKEN` | no | when set, `/api/*` (except health) requires `X-Access-Token` or `?token=`; DEFAULT UNSET for graders |
| `AGENT_QUEUE_LIMIT` | no | pending-job cap, default 10 |

Two of these rows carry a judgement call worth naming out loud:

- `DEPLOY_COMMIT_SHA` — the eval runner refuses to submit a task if the deployed
  sha does not match. **Not "we believe the deployment is current" — a mismatch
  stops the eval before it can produce a flattering number.**
- `ACCESS_TOKEN` — deliberately unset by default. Convenience for graders bought
  with an open API: I would rather a reviewer get straight in than have the demo
  gated behind a secret I have to hand out.

Without a key the worker falls back to the deterministic `MockPlanner`
(mock sites only) and says so in `/api/health`. It says so — that matters. A
keyless deployment still runs and still looks alive; the health endpoint is what
stops that from being mistaken for the real thing.

## How do I build, run and smoke-test it locally?

Run these in order. The first block builds and starts the container; the second
proves the whole chain — health → submit → verdict → artifacts.

```sh
cd E:/Side_Project/wealth
docker build -f apps/services/agent/Dockerfile -t wealth-agent .
docker run --rm -p 8080:8080 \
  -e AGENT_LLM_MODE=direct \
  -e OPENAI_BASE_URL=https://api.openai.com/v1 \
  -e OPENAI_MODEL=gpt-4.1-mini \
  -e OPENAI_API_KEY=sk-... \
  wealth-agent

curl -sf http://localhost:8080/api/health
TID=$(curl -sf -X POST http://localhost:8080/api/tasks -H 'Content-Type: application/json' \
  -d '{"task":"Search MockShop for \"widget\" and see the results","url":"mock:v2"}' | jq -r .task_id)
sleep 20 && curl -sf http://localhost:8080/api/tasks/$TID | jq '{status,verifier,confidence}'
curl -sf http://localhost:8080/api/tasks/$TID/artifacts | jq .
# real-web egress + LLM chain:
curl -sf -X POST http://localhost:8080/api/tasks -H 'Content-Type: application/json' \
  -d '{"task":"Search Wikipedia for \"Reliability engineering\" and open the article"}'
```

Why two task submissions and not one? The `mock:v2` run tests the container
offline — no network, no model bill. The Wikipedia run is the only one that
proves real-web egress and the live LLM chain actually work from inside the
container. Passing the first tells you nothing about the second.

### What are the limits I can't design away?

| Limit | What it means for you |
|---|---|
| Artifacts live on ephemeral disk under `runs/agent_service/` | evidence survives the run, not the container — download what you need |
| Chromium needs ~1 GB RAM | a small instance will not run this |
| One worker thread serializes Playwright | concurrency == queue: jobs wait, they do not run side by side |

These are stated as plain facts, not softened: a single Playwright worker thread
means **the queue is the concurrency model.** Once the pending-job cap
(`AGENT_QUEUE_LIMIT`, default 10) is full, `POST /api/tasks` returns 429 — by
design, not by accident.
