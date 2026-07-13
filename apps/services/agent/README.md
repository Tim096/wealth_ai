# wealth-agent — Task 1 public frontend + API

FastAPI wrapper around `packages/browser_agent`: submit a natural-language web
task, a single Playwright worker thread executes it (jobs are queued), and the
API streams step-by-step progress, the verifier verdict, repair traces,
screenshots and evidence files so every failure is inspectable.

Deploy-time differences live entirely in this directory (existing modules are
imported, never patched): Chromium runs `headless=True`, and the local codex
gateway is bypassed via `AGENT_LLM_MODE=direct`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | UI (task in → live trace, verdict, screenshots) |
| GET | `/api/health` | liveness + planner/queue info (never token-gated) |
| POST | `/api/tasks` | `{"task": "...", "url"?: "", "success"?: ["text_visible:..."], "max_steps"?: 18}` → 202 `{task_id}`; 429 when the queue (10) is full |
| GET | `/api/tasks` | recent tasks |
| GET | `/api/tasks/{id}` | status (`queued/running/pass/fail/unknown/refused/error`), live steps, verifier reason, confidence, answer, verdict telemetry (`observed_evidence`, `missing_evidence`, `llm_cost_usd`, `llm_tokens`, `llm_calls`, `latency_ms`), full structured trace |
| GET | `/api/tasks/{id}/artifacts` | list per-run files (shots / evidence / downloads / run.json) |
| GET | `/api/tasks/{id}/artifacts/{path}` | fetch one artifact |

`GET /api/tasks/{id}` also returns a write-once `contract` object. Once
`contract.frozen` is `true`, `start_url`, `verification_conditions`, and their
`*_source` fields are the exact read-only inputs used by the verifier; the UI
locks task inputs while that run is active.

Once a run completes the record also carries verdict telemetry copied straight
from the `TaskRun` (defaults `[]` / `0` while queued/running): `observed_evidence`
and `missing_evidence` (verifier condition keys, drive the per-condition
checklist), plus `llm_cost_usd`, `llm_tokens`, `llm_calls`, and `latency_ms` for
the cost chip. Deterministic demos (`MockPlanner`) make no LLM calls, so those
four stay `0` / `$0.0000` with only `latency_ms` non-zero.

`url` accepts `mock:v1` / `mock:v2` / `mock:v3` for the bundled offline demo
sites (`data/mock_sites`, served via `file://`). Blank `url`/`success` → the
LLM preflight plans the start URL + verifiable success conditions; open-ended
tasks run anyway and report an honest `unknown`.

## Environment

| Var | Required | Notes |
|---|---|---|
| `OPENAI_API_KEY` | yes | provider key, supplied at deploy time only (never on disk) |
| `AGENT_LLM_MODE` | yes | set `direct` (config default is the local `gateway`) |
| `OPENAI_BASE_URL` | yes | e.g. `https://api.openai.com/v1` (config default is the local gateway) |
| `OPENAI_MODEL` | no | set explicitly for direct mode (config default is OAuth-specific) |
| `AGENT_VISION` | no | leave unset → auto-escalate on stuck |
| `SEC_EDGAR_USER_AGENT` | no | agent tasks may hit EDGAR |
| `PORT` | no | injected by Zeabur (8080) |
| `ACCESS_TOKEN` | no | when set, `/api/*` (except health) requires `X-Access-Token` or `?token=`; DEFAULT UNSET for graders |
| `AGENT_QUEUE_LIMIT` | no | pending-job cap, default 10 |

Without a key the worker falls back to the deterministic `MockPlanner`
(mock sites only) and says so in `/api/health`.

## Local build + run + smoke

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

Runtime notes: artifacts live on ephemeral disk under `runs/agent_service/`;
Chromium needs ~1 GB RAM; one worker thread serializes Playwright, so
concurrency == queue.
