# PromptEngine

A preset-driven prompt workspace and companion Chrome/Firefox extension.

**Phases 1–5 implemented:** PostgreSQL + Flask core, email/password and Google/Microsoft
OpenID Connect authentication, revocable web sessions, extension pairing, scoped
extension tokens, atomic daily AI quotas, saved prompt APIs, six presets, OpenAI refinement,
local compiling, content-free token metrics, Razorpay subscriptions/webhooks, custom presets, and a responsive React workspace with history and billing.

The web application and API are implemented. Chrome/Firefox extension packages are implemented. Production deployment (Phase 6) remains. No fake AI, OAuth, or payment responses are served.

## Repository layout

| Path | Purpose |
| --- | --- |
| `apps/api/promptengine/` | Flask app factory, PostgreSQL models and real API handlers |
| `apps/api/migrations/` | Versioned Alembic upgrade and downgrade |
| `apps/api/tests/` | Integration and security tests using actual PostgreSQL |
| `apps/web/` | React/Vite web application (Phase 4) |
| `apps/extension/` | React/TypeScript Chrome MV3 and Firefox MV3/MV2 extensions |
| `packages/shared-types/src/index.ts` | TypeScript API contracts |
| `docs/phase-1.md` | Auth, quota, pairing and OAuth setup |
| `docs/phase-2.md` | Presets, AI/local compilation and token metric contracts |
| `docs/phase-3.md` | Billing, verified webhooks, custom presets and free launch policy |
| `docs/phase-4.md` | Web application, provider login, browser tests and setup |
| `docs/phase-5.md` | Extension builds, installation, pairing, insertion and release checks |

## Run the API

Requires Python 3.12+, PostgreSQL 16+, and Node.js 22+ for TypeScript checks.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r apps/api/requirements.lock.txt
cp .env.example .env
```

Edit `.env`: provide `DATABASE_URL`, two distinct randomly generated secrets,
and optional Google/Microsoft client credentials. Use a PostgreSQL account with
DDL rights for migrations. The runtime account can use narrower DML permissions.

An optional local database is available with:

```bash
POSTGRES_PASSWORD=your-local-database-password docker compose -f compose.dev.yml up -d
```

Use the same password in `DATABASE_URL`. Then load the environment and run migrations:

```bash
set -a
. ./.env
set +a
cd apps/api
flask --app wsgi db upgrade
flask --app wsgi warm-tokenizer
flask --app wsgi run --host 127.0.0.1 --port 5000
```

`GET /api/health/live` checks the process; `GET /api/health/ready` verifies the database
and migrated schema. The API does not create database tables at startup.

For a configured HTTPS environment, start with `APP_ENV=production` and serve
`gunicorn --bind 0.0.0.0:5000 --workers 2 wsgi:app` behind a trusted reverse proxy.
Full production Docker/Nginx configuration is Phase 6.

## Validation

Tests **truncate tables** in a dedicated test database. Never use a real account database.

```bash
cd apps/api
TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/promptengine_test pytest -q
cd ../..
ruff check apps/api
ruff format --check apps/api
npm ci
npm run typecheck
```

GitHub Actions runs PostgreSQL integration tests, migration checks, Python lint/format,
TypeScript checks, frontend tests, production builds, and browser workflows. See [Phase 1 guide](docs/phase-1.md) for configuration and boundaries.

Configure `OPENAI_API_KEY` for `/api/refine`; `/api/compile` uses no AI quota or model calls.
See the [Phase 2 guide](docs/phase-2.md) for token-accounting boundaries and provider setup.

Paid checkout is disabled by default (`BILLING_ENABLED=false`). See the [Phase 3 guide](docs/phase-3.md)
for test-mode setup, draft pricing, reconciliation and paid-launch requirements.

## Phase 4 web application

See [Phase 4 setup and workflows](docs/phase-4.md). Run `npm ci` and `npm run dev` from the repository root after starting Flask/PostgreSQL. Production build: `npm run build` (`apps/web/dist`). Provider credentials stay in the API environment.

## Phase 5 browser extension

See [Phase 5 installation and security boundaries](docs/phase-5.md). Build all browser targets with `npm run build:extension`. Chrome loads `apps/extension/dist/chrome`; Firefox loads `dist/firefox` or `dist/firefox-mv2`. Pair with your web workspace and use explicit Insert or Copy actions. No Send action is automated.
