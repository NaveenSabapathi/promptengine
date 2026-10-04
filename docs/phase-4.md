# Phase 4 — Corporate React web application

## What is implemented

The app calls the real Phase 1–3 API. It has no fake accounts, mock generation path, local payment success flag, or client-side quota enforcement as the source of truth.

| Route | Workflow |
| --- | --- |
| `/` | Public landing page, six-preset feature overview, live plan configuration and beta-aware pricing |
| `/signup`, `/login` | Validated email/password forms, Google and Microsoft login availability, browser-friendly OAuth errors |
| `/workspace` | Split-pane compiler; six presets and private custom presets; tone, Build/Compact mode, preset context fields; local or AI execution; measured token change; clarification questions and assumptions; copy and explicit save |
| `/history` | Server-side title search, pagination, prompt details, copy, editing, reuse, and confirmed deletion |
| `/settings` | Account details, explicit provider linking, UTC quota, 30-day content-free generation totals, real checkout link, subscription status, and confirmed period-end cancellation |
| `/presets` | Account-private custom preset create/update/delete; backend enforces free-beta or effective Pro access |
| `/settings/extensions` | Inspect and approve a six-digit extension code, list devices, confirm access revocation |

Extension packaging and content injection remain Phase 5. This phase completes the web side of pairing.

## Files

- `apps/web/index.html`, `package.json`, `tsconfig.json`, `vite.config.ts`, `components.json`: Vite/React/Tailwind and shadcn-compatible aliases/configuration.
- `apps/web/src/main.tsx`, `App.tsx`, `auth.tsx`: routing, error boundary, authenticated shell, and server session bootstrap.
- `apps/web/src/lib/api.ts`: same-origin fetch boundary, HttpOnly cookie credentials, separate CSRF header, API error parsing and 45-second timeout; no automatic retries for mutations.
- `apps/web/src/lib/utils.ts`: class merging, date/currency formatting, clipboard fallback, and checkout URL validation.
- `apps/web/src/components/ui/button.tsx`, `input.tsx`: locally owned, adapted shadcn-style React primitives; Radix Slot and class-variance-authority button variants.
- `apps/web/src/components/common.tsx`, `styles.css`: shared states and responsive corporate design, focus styles and reduced-motion support.
- `apps/web/src/pages/Landing.tsx`, `Login.tsx`, `Workspace.tsx`, `History.tsx`, `Settings.tsx`, `Presets.tsx`, `Extensions.tsx`: the screens listed above.
- `apps/web/src/lib/api.test.ts`, `pages/Workspace.test.tsx`, `pages/Settings.test.tsx`: frontend behavior tests.
- `apps/web/playwright.config.ts`, `tests/workflows.spec.ts`: browser tests using actual Flask and PostgreSQL endpoints.
- `apps/api/promptengine/auth.py`: public capability booleans and current account's linked providers.
- `apps/api/promptengine/oauth_routes.py`: CSRF-protected provider linking can return an authorization URL to an SPA requesting JSON; traditional redirect clients retain their existing behavior.
- `apps/api/promptengine/__init__.py`: browser callback failures redirect to `/login?error=<code>`; JSON clients retain API error responses. No provider tokens or private messages are placed in the URL.
- `apps/api/tests/test_web_contracts.py`, `test_oauth.py`: capability, error redirect, account-linking, CSRF/state/PKCE tests.

## Local setup

Use Node.js 22.12+ or Node.js 24 and Python 3.12+. Install the lockfiles. Start PostgreSQL using `compose.dev.yml` and export `.env` as documented in the repository README. PostgreSQL must be real; SQLite is unsupported.

```bash
python -m venv .venv
.venv/bin/pip install -r apps/api/requirements.lock.txt
npm ci
# In one terminal, after exporting .env:
cd apps/api
../../.venv/bin/flask --app wsgi db upgrade
../../.venv/bin/flask --app wsgi run --port 5000
# In another terminal, from repository root:
npm run dev
```

Open `http://localhost:5173`. Use `localhost` consistently; switching between `localhost` and `127.0.0.1` in the browser changes the cookie host. Vite proxies `/api` without rewriting the browser Origin. Flask `WEB_ORIGIN` must match the browser URL. JWT cookies are HttpOnly and `/api` scoped. Only the separate CSRF cookie is readable by JavaScript. Production uses secure cookies and same-origin HTTPS.

Local compiling works without an OpenAI key. AI refinement stays disabled in the selector until the backend has a key. It can still report a clear provider error if the key is invalid or the provider times out. Generation content is temporary until explicitly saved. No prompt text or authentication data is persisted in localStorage/sessionStorage.

## Google/Microsoft configuration

Set the server-only provider client IDs and secrets from `.env.example`. Register these exact local callback URLs:

- Google: `http://localhost:5000/api/auth/google/callback`
- Microsoft: `http://localhost:5000/api/auth/microsoft/callback`

For production use your HTTPS `API_ORIGIN` with the same paths; `WEB_ORIGIN` should be the same public origin. Microsoft tenant policy follows `MICROSOFT_TENANT` (common, organizations, consumers, or an explicit tenant UUID). Provider settings and app consent must be configured by the account owner. Buttons are disabled until both corresponding backend credentials exist.

If a provider email already belongs to an email/password account, sign in with the existing method and connect the provider in Settings. The backend never links accounts by email alone. The SPA follows only validated HTTPS provider authorization URLs; Authlib retains state, PKCE and nonce validation.

No password-reset or account-email-change endpoint exists in the current backend, so this phase does not show pretend forms for those operations.

## Billing behavior

Landing and billing prices come from `/api/billing/plans`. The default ₹499 monthly Pro price is a draft; the configured plan is the source of truth. When `BILLING_ENABLED=false`, the UI clearly labels planned pricing, has no enabled upgrade action, and offers free-beta custom presets. AI daily usage remains the configured free quota, with unlimited local compilation subject to API rate limits.

Checkout calls `/api/billing/subscribe` once and follows only its validated HTTPS `rzp.io` link. Pro is granted only by verified server webhooks. Refresh after returning from payment; the Settings screen also refreshes on window focus. Uncertain checkout attempts display a reconciliation message and block a new purchase. Cancellation is confirmed in the UI and requested for the end of the current billing period. Revocation/deletion also require explicit confirmation.

## Token reporting

Cards show raw text tokens, generated text tokens, and measured tokens reduced or added. Token counts use the backend's GPT-4o-mini tokenizer. They are not exact Claude/Gemini billable tokens and do not include tool/context framing. A Build prompt can increase length; the UI does not present added tokens as savings. The 30-day summary is a net plain-text difference across generation events, including local and AI events, rather than a monetary saving.

## Verification

Phase 4 validation passed: 89 PostgreSQL API tests, 12 frontend behavior tests, two real-API Chromium workflows, TypeScript type checks, production build, Ruff lint/format and Alembic model consistency. Automated axe checks found no violations on the tested landing page and workspace. Desktop and 390px mobile screenshots were visually reviewed. Provider consent and payment transactions were not exercised live.

```bash
npm run typecheck
npm run build
npm run test:web
.venv/bin/ruff check apps/api
.venv/bin/ruff format --check apps/api
# Existing PostgreSQL integration suite:
cd apps/api
TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost/promptengine_test ../../.venv/bin/pytest -q
```

Browser tests use a dedicated PostgreSQL database whose name contains `test`. They start their own Flask and Vite servers; ports 5000 and 5173 must be available. Set the following environment before running from the repository root:

```bash
export APP_ENV=development
export SECRET_KEY=browser-test-session-secret-at-least-32-characters
export JWT_SECRET_KEY=browser-test-distinct-jwt-secret-at-least-32-characters
export DATABASE_URL=postgresql+psycopg://user:password@localhost/promptengine_test
export WEB_ORIGIN=http://localhost:5173 API_ORIGIN=http://localhost:5000
export BILLING_ENABLED=false OPENAI_API_KEY=
export GOOGLE_CLIENT_ID= GOOGLE_CLIENT_SECRET= MICROSOFT_CLIENT_ID= MICROSOFT_CLIENT_SECRET=
npx playwright install --with-deps chromium
npm run test:e2e --workspace @promptengine/web
```

Optional `PLAYWRIGHT_CHROMIUM_EXECUTABLE` selects an already installed Chromium binary. Optional `WEB_SCREENSHOT_DIR` captures desktop/mobile review images. The browser test creates a test user, saved prompt, custom preset, and extension device; use only an isolated test database. It does not create payments or call live OpenAI/provider login endpoints.

Live Google/Microsoft consent and Razorpay transactions still require credentials and merchant/provider configuration. Docker Compose, Gunicorn and Nginx production packaging are reserved for Phase 6.
