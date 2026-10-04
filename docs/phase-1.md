# Phase 1: database, authentication and entitlements

## Delivered files

| File | Responsibility |
| --- | --- |
| `apps/api/promptengine/__init__.py` | App factory, blueprints, health/usage, error handling, security headers and cleanup command |
| `apps/api/promptengine/config.py` | Environment validation; HTTPS, PostgreSQL and cookie configuration |
| `apps/api/promptengine/extensions.py` | SQLAlchemy, Alembic, JWT and Authlib initialization |
| `apps/api/promptengine/models.py` | All typed relational models, constraints and indexes |
| `apps/api/promptengine/security.py` | Auth decorators, scoped tokens, hashed credentials, JSON validation and PostgreSQL rate limits |
| `apps/api/promptengine/auth.py` | Signup, login, current user and session revocation |
| `apps/api/promptengine/oauth_routes.py` | Google/Microsoft OIDC, PKCE, tenant validation and explicit account linking |
| `apps/api/promptengine/pairing.py` | One-time codes, approval, exchange, device list and revocation |
| `apps/api/promptengine/entitlements.py` | Entitlement evaluation, atomic quota reservation and failure refund |
| `apps/api/promptengine/prompts.py` | Account-isolated saved prompt CRUD and paginated title search |
| `apps/api/promptengine/errors.py` | Consistent API error envelopes |
| `apps/api/wsgi.py` | Gunicorn entry point |
| `apps/api/migrations/versions/54d33aa80060_phase_1_authentication_entitlements_and_.py` | Reversible initial PostgreSQL migration |
| `packages/shared-types/src/index.ts` | Web/extension API response contracts |
| `.env.example` | Configuration template without credentials |
| `compose.dev.yml` | Optional local PostgreSQL service |
| `.github/workflows/phase-1.yml` | PostgreSQL tests, migration checks, formatting and TypeScript validation |

## Database architecture

The four requested core tables are `users`, `entitlements`, `usage_ledger`, and
`saved_prompts`. OAuth-only users have a nullable password hash. Additional tables
are `oauth_identities`, `web_sessions`, `pairing_requests`, `extension_tokens`, and
`rate_limit_buckets`.

All account references use UUID foreign keys with cascading deletes. Emails are
normalized and unique; plan tiers and quota counts have database constraints. Usage
has a composite `(user_id, date)` primary key. Prompt indexes cover account and creation
time plus GIN tag lookup. Expiry indexes support cleanup. All timestamps are timezone-aware.

UUID values are application-generated; direct SQL inserts must provide UUIDs. Passwords
use Werkzeug's scrypt hash; no plaintext password or OAuth provider token is stored.

## Authentication and API contract

All responses are JSON except OAuth redirects and successful prompt deletion.
Errors use `{ "error": { "code": "...", "message": "..." } }`.

| Method | Path | Authentication | Request / behavior |
| --- | --- | --- | --- |
| POST | `/api/auth/signup` | Public + exact web Origin | `{email,password}`; 12–128 character password; creates free entitlement and session; 201 |
| POST | `/api/auth/login` | Public + exact web Origin | `{email,password}`; cookie session; 200 |
| GET | `/api/auth/me` | Web cookie | Current account |
| POST | `/api/auth/logout` | Web cookie + CSRF | Revoke current session and clear cookies |
| GET | `/api/auth/google/login` | Public | Redirect to Google |
| GET | `/api/auth/microsoft/login` | Public | Redirect to Microsoft |
| GET | `/api/auth/{provider}/callback` | OAuth state | Verified identity → cookie session → `/workspace` |
| POST | `/api/auth/{provider}/link` | Web cookie + CSRF | Explicitly link provider; redirect to provider |
| GET | `/api/usage` | Web cookie or `usage:read` token | Tier, UTC date, limit, used and remaining |
| POST | `/api/extension/pairing` | Public, rate limited | `{device_name}`; returns five-minute pairing code and device secret; 201 |
| POST | `/api/extension/pairing/inspect` | Web cookie + CSRF | `{code}`; display device name and permissions before approval |
| POST | `/api/extension/pairing/approve` | Web cookie + CSRF | `{code}`; one-time approval |
| POST | `/api/extension/pairing/exchange` | Pairing credentials | `{pairing_id,code,device_secret}`; one-time scoped bearer token |
| GET | `/api/extension/tokens` | Web cookie | Device token metadata, never token plaintext |
| DELETE | `/api/extension/tokens/{id}` | Web cookie + CSRF | Revoke own device token |
| GET | `/api/prompts` | Web cookie or `prompts:read` | `q` searches title literally; `page` 1–10000, `per_page` 1–100 |
| POST | `/api/prompts` | Web cookie + CSRF or `prompts:write` | `{title,content,tags?}`; 201 |
| GET | `/api/prompts/{id}` | Web cookie or `prompts:read` | Own prompt only |
| PUT | `/api/prompts/{id}` | Web cookie + CSRF or `prompts:write` | Replace title/content/tags |
| DELETE | `/api/prompts/{id}` | Web cookie + CSRF or `prompts:write` | Delete own prompt; 204 |
| GET | `/api/health/live` | Public | Process health |
| GET | `/api/health/ready` | Public | Database/schema readiness; unavailable → 503 |

Prompt title length: 1–200; content: 1–50,000; up to 20 tags of 1–50 characters.
Requests exceeding 64 KiB are rejected. Account-inaccessible objects return 404.
`/api/refine`, `/api/compile` and generation metrics are now implemented in Phase 2;
see [Phase 2](phase-2.md) for the current contract.

### Web sessions

JWTs live only in HttpOnly cookies at `/api`; production cookies are Secure and
SameSite=Lax. Sessions expire after 12 hours and are checked against PostgreSQL on
every request, allowing logout to invalidate a copied JWT immediately. There is no
refresh token in Phase 1; the user signs in again after expiry.

For every mutating web request, send `X-CSRF-TOKEN` from the readable
`csrf_access_token` cookie and an Origin matching `WEB_ORIGIN`. The JWT cookie is
HttpOnly; the separate CSRF cookie is intentionally readable. Signup/login require
Origin even before a session exists. Test/cURL clients must send these headers too.

Production web and API share one HTTPS origin. For local development the UI can use
`http://localhost:5173` and API `http://localhost:5000`; fetch with `credentials: 'include'`.
CORS permits only the configured web origin. Extension bearer requests do not use
cookies and do not require CSRF. Perform them from the extension context with explicit
API host permissions, never from the chat page content script. Pairing credentials
and tokens must not appear in URLs, telemetry or page DOM.

### Google setup

Create a Google Cloud OAuth web application. Configure exact redirect URIs:

- Development: `http://localhost:5000/api/auth/google/callback`
- Production: `https://YOUR_DOMAIN/api/auth/google/callback`

Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` on the API. Configure consent,
test users or publishing as appropriate. The backend requests `openid email profile`
and verifies Google ID tokens. Google emails must be verified when creating a new account.

### Microsoft setup

Register a Microsoft Entra application and configure a **Web** redirect URI:

- Development: `http://localhost:5000/api/auth/microsoft/callback`
- Production: `https://YOUR_DOMAIN/api/auth/microsoft/callback`

Set `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, and `MICROSOFT_TENANT`:

| Tenant setting | Supported users |
| --- | --- |
| `common` | Organizational and personal Microsoft accounts |
| `organizations` | Work/school accounts |
| `consumers` | Personal Microsoft accounts |
| Tenant UUID | One organization's tenant |

Choose matching supported account types in Entra. The backend validates the signed
tenant UUID and exact corresponding v2 issuer; arbitrary issuers are rejected. Accounts
without an `email` ID-token claim cannot register automatically and receive an actionable
validation error. They can sign in with email/password and explicitly link the provider.

Both providers use authorization-code flow with S256 PKCE, state and nonce; signature,
audience, issuer and expiry are verified. Outbound requests have a 10-second timeout.
Credentials are server-only. Callback redirects use fixed configured origins, not user input.

Identities are keyed by `(provider, issuer, subject)`. **Never automatically link by email.**
Microsoft email is a contact label and can change. If an email already exists, return
`account_link_required`; the user signs in through the existing method and explicitly
links the provider. Linking checks that the initiating web session is still active.

Live Google/Microsoft consent and callback testing requires real OAuth app registrations;
those credentials are not included. Automated tests verify actual signed OIDC tokens
and callback state with fixture keys; they do not prove provider console configuration.

### Extension pairing

1. Extension requests a code and stores `pairing_id` plus `device_secret` privately.
2. User signs into the web app, enters the code, inspects device/permissions, and approves.
3. Extension exchanges all three credentials for an opaque, 30-day bearer token.
4. Store the bearer token in extension-local storage; only token hashes exist server-side.
5. A reused/expired code or missing/wrong secret fails. An unapproved request returns 409.
6. The user can list and revoke device tokens from web settings. Expired tokens require pairing again.

Tokens grant `refine`, `prompts:read`, `prompts:write`, and `usage:read`; they cannot approve
other devices, access web account routes, or perform future billing operations. The web
approval UI and extension popup are built in later phases. Phase 1 tests exercise the real API flow.

## Quota reservation and Phase 2 integration

Free defaults to 10 requests per UTC day. Pro uses a finite configured daily limit;
Phase 3 will choose and enforce the commercial policy. Expired Pro entitlements fall
back to the Free limit immediately, independent of a billing webhook arriving.

`@requires_auth('refine')` is the outer decorator. Validate Phase 2 request data before
invoking an execution function decorated with `@requires_entitlement`. That function:

1. Locks the user's entitlement row to synchronize with plan changes.
2. Atomically inserts/increments the daily ledger with `ON CONFLICT DO UPDATE` and a limit condition.
3. Commits the reservation **before** calling AI, then releases all database locks.
4. Refunds the reserved slot if execution raises or returns an error response.

A hard process termination after reservation may consume one slot conservatively;
Phase 2 can add durable generation jobs/reconciliation if needed. Local compiling
will bypass AI reservation. Do not increment quota again in Phase 2.

## Operations and validation

Run migrations once before starting workers; don't run `create_all()` in production.
Run `flask --app wsgi cleanup-auth` daily to remove expired sessions, device tokens,
pairing requests and rate-limit buckets. Login and pairing limits live in PostgreSQL,
so they hold across Gunicorn processes; IP limits rely on accurate proxy configuration.
Only set `TRUST_PROXY=true` behind one trusted ingress, with direct API access blocked.

Database exceptions return 503 without logging SQL parameters or content. Production
configuration fails closed for missing/short/equal secrets, non-PostgreSQL URLs, HTTP,
or different web/API origins. Never expose `.env` or the database port publicly.

The test suite uses the initial migration, then truncates all application tables in a
dedicated PostgreSQL test database. It covers session CSRF/revocation/expiry, quotas
under concurrent requests, failed-call refunds, pairing race/replay/expiry, token
permissions, tenant isolation, provider setup errors, signed OIDC validation, explicit
linking and OAuth state expiry. CI also runs migration downgrade/upgrade and drift checking.

## Remaining phases and launch gates

- Phase 2: six presets, AI structured generation, timeouts and token metrics.
- Phase 3: Razorpay SDK/subscriptions, verified idempotent webhooks and commercial limits.
- Phase 4: corporate React workspace, landing/auth screens, pairing approval UI, history/billing.
- Phase 5: Chrome/Firefox packaging, secure pairing UI, assistant adapters and clipboard fallback.
- Phase 6: complete Docker/Gunicorn/Nginx deployment, HTTPS and live provider validation.

Email verification and password reset/recovery are not implemented in this phase.
The final public launch should include them, plus live provider tests, HTTPS validation,
backups and monitoring. The API foundation should not be marketed as the finished SaaS.
