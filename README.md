# AgentQA

AgentQA is a reproducible evaluation and regression-testing platform for tool-using AI agents. It keeps the polished NovaCart support demo, while making the backend the source of truth for execution, tool traces, evaluation, metrics, batches, scenarios, suites, and CI exports.

The default mode is deterministic and makes no external model request. Gemini execution is optional and uses the supported `google-genai` SDK with manual function calling through an allowlisted target adapter.

> **Security notice:** the built-in unauthenticated mode is for local development only. Add real authentication, authorization, tenancy controls, and production secret management before exposing AgentQA publicly.
>
> If a Gemini key was ever placed in a shared or committed `.env`, rotate that key manually. Removing the file does not revoke an exposed credential.

## What is included

- Versioned Pydantic evaluation specifications with structured check evidence.
- Required/forbidden tools, order and argument assertions, tool-error checks, behavioral concept groups, forbidden claims, grounding, protected-content canaries, hard failures, and configurable pass thresholds.
- Deterministic mock and Gemini providers with typed responses, usage, latency, errors, bounded transient retries, explicit fallback, and real function-calling loops.
- Run snapshots for the scenario, evaluation specification, agent configuration, model, prompt hash/version, tool definitions, provider/evaluator versions, input source, usage, cost, errors, and fallback reason.
- Persistent batches, repetitions, partial-failure visibility, baseline comparison deltas, scenario suites, JSON export, and JUnit export.
- Paginated and filtered run APIs, SQL-backed all-time metrics, lazy trace loading, request cancellation/timeouts, accessible result rows and disclosures, and structured evaluation panels.
- NovaCart as the included target adapter, isolated from the general runner/evaluator so another target can be added later.
- Alembic migrations, root-level Python tooling, frontend lint/tests/type checking/build scripts, Docker health checks, GitHub Actions, secret scanning, and tracked-file source packaging.

## Architecture

```text
Next.js UI
    │
    ▼
FastAPI API ── RunService ── AgentRunner ── Provider
    │                         │                ├─ deterministic mock
    │                         │                └─ Gemini / google-genai
    │                         ▼
    │                    TargetAdapter
    │                         └─ NovaCart tools
    ▼
ScenarioEvaluator ── optional separately configured semantic judge
    │
    ▼
SQLAlchemy + Alembic + SQLite
```

Only observable messages, validated function calls and arguments, tool results, timings, usage, and errors are stored. Hidden chain-of-thought is neither requested nor persisted. Protected system-prompt content is represented by a hash/version in normal traces and exports.

## Repository layout

```text
.
├── alembic.ini
├── backend/
│   ├── .env.example
│   └── backend/
│       ├── alembic/
│       ├── app/
│       │   ├── agents/       # runner, providers, target adapter
│       │   ├── api/          # FastAPI routes
│       │   ├── evaluation/   # typed specs, evaluator, semantic judge
│       │   ├── models/       # persistence models
│       │   ├── services/     # runs, reports, scenarios, suites, redaction
│       │   └── tools/        # NovaCart tool schemas/runtime
│       ├── tests/
│       ├── requirements.txt
│       └── requirements-dev.txt
├── frontend/
│   ├── app/
│   ├── components/agentqa/
│   ├── e2e/
│   ├── lib/agentqa/
│   └── package.json
├── compose.yaml
├── pyproject.toml
└── scripts/package-source.sh
```

## Prerequisites

- Python 3.11 or newer
- Node.js 22 or newer
- Corepack and pnpm 10.12.2
- Docker with Compose, optional

## Local development

### Backend

Run from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate                 # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/backend/requirements-dev.txt
cp backend/.env.example backend/.env
alembic upgrade head
uvicorn app.main:app --app-dir backend/backend --reload --port 8000
```

The default database location is predictable and independent of the working directory:

```text
backend/data/agentqa.db
```

The API is available at `http://localhost:8000`; its health endpoint is `GET /health`.

### Frontend

In another terminal, from the repository root:

```bash
corepack enable
corepack prepare pnpm@10.12.2 --activate
cd frontend
cp .env.example .env.local
pnpm install --frozen-lockfile
pnpm dev
```

The UI is available at `http://localhost:3000` and defaults to `http://localhost:8000` for the API.

## Docker Compose

Run from the repository root:

```bash
cp backend/.env.example backend/.env
docker compose --env-file backend/.env up --build
```

Compose runs migrations before the API starts, persists SQLite under the `agentqa-data` volume, and waits for the backend health check before starting the frontend.

## Environment configuration

The distributable repository contains only sanitized `.env.example` files. Never commit a populated `.env`.

Important backend variables:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Optional SQLAlchemy URL; defaults to `backend/data/agentqa.db`. |
| `GEMINI_API_KEY` | Credential for the tested Gemini agent. Leave empty for mock mode. |
| `GEMINI_MODEL` | Tested-agent Gemini model. |
| `GEMINI_INPUT_COST_PER_MILLION` | Configurable input-token pricing metadata. |
| `GEMINI_OUTPUT_COST_PER_MILLION` | Configurable output-token pricing metadata. |
| `SEMANTIC_JUDGE_PROVIDER` | `disabled` by default, or `gemini`. |
| `SEMANTIC_JUDGE_API_KEY` | Separate credential used only by the optional judge. |
| `SEMANTIC_JUDGE_MODEL` | Judge model, independently configured from the tested agent. |
| `SEMANTIC_JUDGE_TIMEOUT_SECONDS` | Judge request timeout. |
| `CORS_ORIGINS` | Explicit comma-separated frontend origins. |
| `CORS_ALLOW_CREDENTIALS` | Must remain false when wildcard origins are used. |
| `TRACE_REDACT_KEYS` | Additional case-insensitive keys removed from traces/exports. |
| `AUTHENTICATION_MODE` | The included value is `local-development-only`. |

The deterministic evaluator remains the default test path. A scenario that contains a required semantic-judge check fails with an explicit evaluation error when no independent judge is configured; AgentQA never invents a semantic result.

## Execution modes

- **Scenario:** executes the immutable stored scenario input against its stored evaluation specification.
- **Mutation:** executes an edited input and evaluates that actual edited input against the selected scenario specification.
- **Ad hoc:** executes arbitrary input. It is `not_evaluated` unless an evaluation-specification scenario is explicitly selected.

Provider execution can end as `completed`, `degraded`, `failed`, or `cancelled`. A degraded run indicates a real configured fallback occurred or evaluation infrastructure failed after provider execution. Provider failures are persisted rather than escaping as an unrecorded HTTP 500.

## Evaluation model

Each run stores the exact evaluation-specification snapshot and evaluator version. Checks return:

- check ID and label;
- pass/fail state;
- earned and maximum numeric contribution;
- dimension;
- hard-failure flag;
- concise evidence.

The dashboard dimensions—tool-call correctness, policy compliance, prompt-injection resistance, and groundedness—are derived from these checks. Text checks normalize case, punctuation, Unicode apostrophes, and contractions, and use practical negation handling so a phrase such as `not eligible` is not treated as the positive claim `eligible`.

Prompt leakage is a hard failure only when the provider-only canary or genuinely protected content is disclosed. Merely mentioning phrases such as “system prompt” or “hidden developer instructions” is not itself leakage.

## Database migrations

Migrations are mandatory for schema evolution; application startup does not call `create_all` to alter an existing database.

```bash
alembic upgrade head
alembic current
alembic history
```

Included revisions:

- `0001_legacy_baseline` — creates or adopts the recognized pre-migration AgentQA schema.
- `0002_production_platform` — adds structured evaluation snapshots/checks, provider metadata, reproducible run fields, persistent batches, suites, indexes, and legacy-data backfills.

## Verification

### Backend

From the repository root:

```bash
python -m pip install -r backend/backend/requirements-dev.txt
pytest
pytest --cov=backend/backend/app --cov-report=term-missing
ruff check backend/backend/app backend/backend/tests
ruff format --check backend/backend/app backend/backend/tests
mypy
```

Tests force `ENVIRONMENT=test`, clear provider credentials, use isolated databases, and monkeypatch socket connections so a real Gemini request cannot occur.

### Frontend

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm test
pnpm typecheck
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

The component tests cover structured disclosures and lazy run-detail loading. The small Playwright happy path verifies that the initial run list does not trigger one detail request per row.

## API highlights

- `GET /health`
- `GET|POST /scenarios`, scenario update/duplicate/archive/restore/delete, JSON import/export
- `GET|POST /suites`, suite update/archive/restore/delete, baseline selection
- `POST /runs` for scenario, mutation, and ad-hoc execution
- `GET /runs` with page-based pagination and server-side filters
- `GET /runs/{id}` and `GET /runs/{id}/export`
- `POST /batches`, `GET /batches`, `GET /batches/{id}`, cancellation and comparison
- `GET /batches/{id}/export` and `GET /batches/{id}/export/junit`
- `GET /metrics/summary`
- `GET|PUT /agent-config`

Interactive API documentation is available at `/docs` in local development.

## Safe source packaging

After reviewing and committing the intended changes:

```bash
./scripts/package-source.sh
```

The script packages only tracked files with `git archive`, refuses a dirty tree, and refuses tracked `.env`, database, `.DS_Store`, or TypeScript build-info artifacts. CI also runs Gitleaks.

Before sharing any manual archive, remove local secrets, databases, caches, build outputs, local pnpm stores, and macOS metadata. Rotating an exposed provider key remains a separate manual action.
