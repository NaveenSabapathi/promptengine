# PromptEngine — Complete Installation and Setup Manual

**Application:** PromptEngine web workspace, Flask API and Chrome/Firefox extension  
**Repository:** <https://github.com/NaveenSabapathi/promptengine>  
**Documentation date:** 4 October 2026  
**Coverage:** implemented Phases 1–6, including the production container stack

This manual takes an operator from a fresh checkout to a working installation. Follow the local development path for coding and evaluation, or the production path for a public HTTPS deployment. Provider setup is optional initially: email/password login and local compilation work without Google, Microsoft, OpenAI or Razorpay credentials.

Commands are for Bash on Linux, macOS or Windows WSL unless another shell is named. Production examples use Ubuntu 24.04 LTS and the sample hostname `prompt.example.com`. Replace it everywhere with a hostname you control. Never enter the sample hostname in a live provider registration.

## Contents

1. [Application overview and installation paths](#1-application-overview-and-installation-paths)
2. [Requirements and information to collect](#2-requirements-and-information-to-collect)
3. [Download the application](#3-download-the-application)
4. [Local development installation](#4-local-development-installation)
5. [Production VPS installation](#5-production-vps-installation)
6. [Configuration reference](#6-configuration-reference)
7. [Google login setup](#7-google-login-setup)
8. [Microsoft login setup](#8-microsoft-login-setup)
9. [OpenAI setup and token accounting](#9-openai-setup-and-token-accounting)
10. [Razorpay subscriptions and webhooks](#10-razorpay-subscriptions-and-webhooks)
11. [Chrome and Firefox extension installation](#11-chrome-and-firefox-extension-installation)
12. [First-use application walkthrough](#12-first-use-application-walkthrough)
13. [Validation and automated tests](#13-validation-and-automated-tests)
14. [Day-to-day operations and TLS renewal](#14-day-to-day-operations-and-tls-renewal)
15. [Database backup and restore](#15-database-backup-and-restore)
16. [Updates, rollback and credential changes](#16-updates-rollback-and-credential-changes)
17. [Troubleshooting](#17-troubleshooting)
18. [Launch checklist and current boundaries](#18-launch-checklist-and-current-boundaries)
19. [File map and official references](#19-file-map-and-official-references)

## 1. Application overview and installation paths

### 1.1 What is installed

| Component | Technology | Responsibility |
| --- | --- | --- |
| Web application | React, TypeScript, Vite, Tailwind, shadcn-style components | Landing page, authentication, prompt workspace, history, settings, billing and device approval |
| API | Flask, SQLAlchemy, Alembic | Accounts, authentication, preset compilation, AI requests, quotas, prompt storage and billing |
| Database | PostgreSQL 16 | Persistent accounts, entitlement/usage records, prompts, custom presets and billing/auth metadata |
| Production API server | Gunicorn | Multiple application workers and graceful shutdown |
| Public server | Nginx | HTTPS termination, static frontend, SPA routes and `/api` reverse proxy |
| Browser extension | React/TypeScript WebExtension | Paired workspace, explicit insertion into supported chat editors and clipboard fallback |

The production request path is: browser → HTTPS Nginx → static frontend or Flask API → PostgreSQL and optional external providers. PostgreSQL and Gunicorn are not published as host ports. Only Nginx publishes HTTP/HTTPS.

The extension calls the API from its own context using a scoped token. It does not copy the web session JWT or store a model/provider secret. Insertion receives plain prompt text; the extension never clicks Send.

### 1.2 Choose a path

| Goal | Follow |
| --- | --- |
| Run and edit the app on your computer | Sections 3–4, then optional provider/extension sections |
| Publish on a new Linux VPS | Sections 3 and 5–11, then operational sections |
| Install on a VPS already hosting other websites | Read 5.2 first; this stack expects to own public ports 80/443 |
| Use everything free initially | Keep `BILLING_ENABLED=false`; add OpenAI only if AI refinement is desired |
| Test recurring billing | Use a separate HTTPS staging installation and Razorpay test-mode settings |
| Install only the browser extension | Section 11; an already running PromptEngine server is still required |

### 1.3 Local and production configuration are separate

Local development uses `.env` and optionally `compose.dev.yml`. Production uses `.deploy.env`, `deploy/secrets/`, `deploy/tls/` and `docker-compose.yml`.

Do not reuse the development database volume, development secrets or a test database as production. Do not run the disposable container smoke script against a customer database.

## 2. Requirements and information to collect

### 2.1 Development requirements

| Requirement | Version / condition |
| --- | --- |
| Python | 3.12 or newer; production image uses 3.12 |
| Node.js | 22.12+ or 24; production frontend build uses Node 22 |
| npm | Included with a supported Node installation; use the checked-in npm lockfile |
| PostgreSQL | 16; real PostgreSQL is required, SQLite is unsupported |
| Git | For checkout and release tracking |
| Docker + Compose | Needed if using the supplied local database or container tests |
| Browser | Current Chrome/Chromium or Firefox; see extension minimums in Section 11 |

On Windows, use WSL2 Ubuntu 24.04 for the commands in this manual. Install Docker Desktop with WSL integration if you choose the supplied Docker database. Keep the project in the WSL Linux home directory for normal file permissions. Run Python, npm and Docker from the same WSL environment. The development browser can remain on Windows.

This manual's automated browser test commands assume `.venv/bin/...` paths and therefore require Linux/WSL/macOS rather than a native Windows virtual environment.

### 2.2 Production requirements

Start with a Linux VPS with approximately 2 vCPU, 4 GB RAM and enough disk for Docker images, PostgreSQL and backups. This is a planning baseline, not a capacity guarantee; monitor actual workload. Database storage and off-host backups need their own sizing.

The production host needs Docker Engine, Compose v2 plugin 2.24+, Git, Python 3, OpenSSL, curl and a certificate tool such as Certbot. Host Node.js and a host Python virtual environment are not required to run the containers. Building extension packages separately requires Node/npm.

### 2.3 Collect before production setup

Record these values privately:

- Public hostname and DNS administrator access.
- VPS address, SSH account, actual SSH port and deployment directory.
- Whether ports 80/443 are already used.
- Which optional providers should be enabled.
- Google web OAuth client ID/secret, if used.
- Microsoft application ID/client-secret value and tenant policy, if used.
- OpenAI project API key and usage budget, if used.
- Razorpay mode, key ID/secret, matching monthly plan and webhook secret, if used.
- Backup destination, retention policy and an operator responsible for restore drills.

The application has no built-in super-admin portal or special first-user bootstrap. The first account is a normal Free account. Operator configuration is performed on the server and in provider consoles.

## 3. Download the application

For a new checkout:

```bash
git clone https://github.com/NaveenSabapathi/promptengine.git
cd promptengine
git switch main
git pull --ff-only
```

Confirm the deployment files exist:

```bash
test -f docker-compose.yml
test -f apps/api/Dockerfile
test -f apps/web/Dockerfile
test -f deploy/init.py
git rev-parse HEAD
```

Record the commit used for production. An operator can deploy a reviewed tag or specific commit instead of following a moving branch.

A downloaded source ZIP may also be used. Extract it, enter the folder containing `package.json` and `docker-compose.yml`, and run the matching setup path. ZIP installations do not support Git update commands until replaced by or associated with a checkout. A source ZIP contains neither runtime credentials nor trusted certificates.

## 4. Local development installation

### 4.1 Verify tools

From the repository root:

```bash
python3 --version
node --version
npm --version
docker --version
docker compose version
```

If you use an existing PostgreSQL server instead of Docker, the last two commands are optional. Configure an application database and an account with migration rights on that server.

For Ubuntu 24.04 development, install the host Python/Git prerequisites if needed:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip git curl ca-certificates
```

Install a supported Linux Node.js release using [Node.js installation instructions](https://nodejs.org/en/download). With WSL, install Node and Python inside Ubuntu rather than reusing Windows executables. Set up WSL using [Microsoft’s WSL instructions](https://learn.microsoft.com/en-us/windows/wsl/install); for the Docker database, install Docker Engine as in Section 5.3 or enable Docker Desktop integration for that WSL distribution.

### 4.2 Install dependencies

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r apps/api/requirements.lock.txt
npm ci
cp .env.example .env
chmod 600 .env
```

Use `npm ci`, not an unreviewed lockfile update. The monorepo root installs workspace dependencies for the web app, extension and shared types.

### 4.3 Generate local configuration without displaying secrets

This example creates development credentials and writes a fresh `.env`. It replaces the copied template, so run it before adding provider settings. It refuses to replace a customized file.

```bash
python3 - <<'PY'
from pathlib import Path
import secrets

path = Path('.env')
template = Path('.env.example').read_text()
if path.exists() and path.read_text() != template:
    raise SystemExit('A customized .env already exists; edit it instead.')
password = secrets.token_urlsafe(32)
text = template.replace(
    'DATABASE_URL=postgresql+psycopg://promptengine:change-me@localhost:5432/promptengine',
    f'DATABASE_URL=postgresql+psycopg://promptengine:{password}@localhost:5432/promptengine',
)
text = text.replace('SECRET_KEY=\n', 'SECRET_KEY=' + secrets.token_urlsafe(48) + '\n', 1)
text = text.replace('JWT_SECRET_KEY=\n', 'JWT_SECRET_KEY=' + secrets.token_urlsafe(48) + '\n', 1)
text += f'\nPOSTGRES_PASSWORD={password}\n'
path.write_text(text)
path.chmod(0o600)
print('Development settings written; no credentials printed.')
PY
```

Keep `APP_ENV=development`, `WEB_ORIGIN=http://localhost:5173`, `API_ORIGIN=http://localhost:5000`, `TRUST_PROXY=false`, and `BILLING_ENABLED=false` for the initial local installation. Optional provider keys may remain blank.

`.env` is not automatically loaded by the supplied Flask requirements. Load it explicitly in each terminal that starts the API or performs database commands:

```bash
set -a
. ./.env
set +a
```

Only source a file you trust. Keep dotenv values Bash-compatible: quote values containing spaces or shell metacharacters. Generated values above are URL-safe and need no extra quoting. With a manually chosen database password, URL-encode its password component in `DATABASE_URL`.

### 4.4 Start local PostgreSQL

With the environment loaded:

```bash
docker compose -f compose.dev.yml up -d
docker compose -f compose.dev.yml ps
```

The development database is `promptengine`, the user is `promptengine`, and port 5432 is bound only to host loopback. The generated `.env` supplies its password.

If port 5432 is occupied, either use your existing PostgreSQL instance or choose another loopback host port in `compose.dev.yml` and update `DATABASE_URL` to match. Do not change the container's internal PostgreSQL port unnecessarily.

Changing `POSTGRES_PASSWORD` after the volume exists does not rotate its database role password. Keep the original value or perform a deliberate PostgreSQL password change. Do not remove a volume containing data to solve an authentication error.

### 4.5 Apply migrations and cache the tokenizer

```bash
cd apps/api
../../.venv/bin/flask --app wsgi db upgrade
../../.venv/bin/flask --app wsgi db current
../../.venv/bin/flask --app wsgi warm-tokenizer
```

`warm-tokenizer` downloads/caches the vocabulary used for text token counts. It does not submit your task to a model. Its initial run needs network access.

Do not use `db.create_all()` or manually create application tables instead of Alembic migrations.

### 4.6 Start the API — terminal one

Keep the terminal in `apps/api`, with the environment already loaded:

```bash
../../.venv/bin/flask --app wsgi run --host 127.0.0.1 --port 5000
```

The Flask development server is for local development. Use the production Gunicorn/Nginx stack for a public service.

### 4.7 Start the frontend — terminal two

Open another terminal in the repository root:

```bash
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to Flask. Use `localhost` consistently in the browser; changing the browser hostname to `127.0.0.1` changes cookie scope and no longer matches the configured web origin.

### 4.8 Verify the local installation

From a third terminal:

```bash
curl --fail http://localhost:5000/api/health/live
curl --fail http://localhost:5000/api/health/ready
curl --fail http://localhost:5173/api/auth/capabilities
```

Expected health response is `{"status":"ok"}`. Capability output initially has disabled providers and AI if keys are blank. Then create an account in the browser, select local compilation and generate a prompt. Follow Section 12 for the complete walkthrough.

To stop development, stop the API/Vite terminals with Ctrl+C. Stop the database with:

```bash
docker compose -f compose.dev.yml stop db
```

This retains its data.

## 5. Production VPS installation

### 5.1 Prepare a deployment account and private checkout

Use a dedicated operator account with the necessary administrative rights. The examples use `deploy` and `/opt/promptengine`; adapt them to an existing account instead of creating duplicates.

On a fresh host, an administrator may run:

```bash
sudo adduser deploy
sudo usermod -aG sudo deploy
sudo install -d -m 0750 -o deploy -g deploy /opt/promptengine
```

Configure SSH key access according to your server's existing procedure. Keep a working SSH session while changing access controls.

Once logged in as the deployment account:

```bash
git clone https://github.com/NaveenSabapathi/promptengine.git /opt/promptengine
cd /opt/promptengine
git switch main
git pull --ff-only
git rev-parse HEAD
```

Do not serve this checkout as a public document root. Nginx serves only the compiled frontend copied into its image.

### 5.2 Check existing VPS services before binding ports

```bash
sudo ss -ltnp
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Inspect port 80 and 443 usage. This Compose stack expects to be the public TLS ingress. A new DNS subdomain does not allow two separate services to bind the same IP and ports.

If your VPS already runs Nginx or other stacks on 80/443, choose a separate server/IP or design an integration with the existing ingress. Do not stop other sites or overwrite `/etc/nginx` blindly. The supplied internal Nginx overwrites forwarding headers and assumes one trusted proxy; putting another proxy in front without redesigning trust/client-IP handling can make rate limits treat multiple users as one client.

`HTTP_BIND`, `HTTPS_BIND`, `HTTP_PORT` and `HTTPS_PORT` can change host bindings for controlled staging. Changing those values alone is not a complete multi-site/public-origin integration. Production callbacks and public origins in this stack assume normal HTTPS port 443.

### 5.3 Install Docker on a fresh Ubuntu host

If Docker is already installed and working, verify its version and leave the existing installation intact. For a fresh host, use the [official Ubuntu installation instructions](https://docs.docker.com/engine/install/ubuntu/) to configure Docker's apt repository. Then install and verify:

```bash
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
```

These packages require the official Docker repository; Ubuntu's default repositories alone may not provide them. Do not remove an existing runtime without reviewing its running workloads.

For the `deploy` account to run the manual's commands without `sudo`:

```bash
sudo usermod -aG docker deploy
```

Log out and back in, then run `docker info` and `docker compose version`. Membership of the Docker group gives administrative control over the host; grant it only to deployment operators.

Install basic tools on the host if missing:

```bash
sudo apt install git python3 openssl curl ca-certificates dnsutils
```

### 5.4 Configure DNS and network access

Create an A record for `prompt.example.com` pointing to your VPS IPv4 address. Add an AAAA record only if IPv6 routing is configured. Verify:

```bash
dig +short A prompt.example.com
dig +short AAAA prompt.example.com
```

Allow inbound TCP 80 and 443 in the VPS provider's firewall/security group. Retain access to the actual SSH port. If applying host UFW rules, set the current SSH port first; for example use 2212 only when your SSH server actually listens there:

```bash
ADMIN_SSH_PORT=22
sudo ufw allow "${ADMIN_SSH_PORT}/tcp"
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw status verbose
```

Enable UFW only after confirming SSH and other required services are allowed. Docker-published ports can bypass ordinary UFW rules; this is why the Compose file publishes no DB/API port. Review Docker's firewall documentation for broader host restrictions.

If using a DNS/CDN proxy, begin with DNS-only records for initial diagnosis. Additional proxy layers require a reviewed client-IP and TLS trust configuration; do not set `TRUST_PROXY` or trust arbitrary client headers as a shortcut.

### 5.5 Initialize production settings

From `/opt/promptengine` as the deployment account:

```bash
python3 deploy/init.py --domain prompt.example.com
```

Initialization creates:

| Path | Contents |
| --- | --- |
| `.deploy.env` | Public hostname, port bindings, image release tag, public client IDs and billing policy |
| `deploy/secrets/postgres_password` | Application database credential |
| `deploy/secrets/postgres_admin_password` | Separate DB administrator credential; not mounted into the API |
| `deploy/secrets/session_secret` | Server session signing secret |
| `deploy/secrets/jwt_secret` | Distinct JWT signing secret |
| Other `deploy/secrets/*` files | Blank placeholders for optional provider secrets |
| `deploy/tls/` | Private directory for TLS certificate/key copies |

Generated secrets are independent and are not printed. Secret directories are private to their host owner. Individual mounted files are readable inside non-root containers. These paths are excluded from Git and Docker build contexts.

Initialization refuses to replace an existing configuration. For an existing installation, edit its files; do not delete and regenerate them to perform an update.

Edit the non-secret configuration:

```bash
nano .deploy.env
```

For the initial free launch, leave `BILLING_ENABLED=false`. You can bring the application online before enabling any external provider.

### 5.6 Obtain a trusted TLS certificate

Install Certbot using the [official instructions](https://certbot.eff.org/instructions) for your OS. Standalone issuance requires the hostname to resolve to this host and port 80 to be reachable and unused during issuance. The stack should not be started yet.

```bash
sudo certbot certonly --standalone -d prompt.example.com
sudo install -m 0444 /etc/letsencrypt/live/prompt.example.com/fullchain.pem deploy/tls/fullchain.pem
sudo install -m 0444 /etc/letsencrypt/live/prompt.example.com/privkey.pem deploy/tls/privkey.pem
```

Keep `deploy/tls/` private. Certificates are individual bind mounts and never baked into the web image. Both files must exist before startup. Copying a certificate onto the host is not the same as installing a renewal process; complete Section 14.3.

Do not use `deploy/init.py --self-signed` for a customer-facing installation. That option creates a short-lived test certificate for isolated validation.

### 5.7 Validate, build and start

```bash
docker compose --env-file .deploy.env config --quiet
docker compose --env-file .deploy.env build
docker compose --env-file .deploy.env up -d --wait --wait-timeout 120
docker compose --env-file .deploy.env ps -a
docker compose --env-file .deploy.env exec -T web nginx -t
```

Expected state:

- `db`: running and healthy.
- `migrate`: exited successfully with code 0; it is a one-shot job, not a server.
- `api`: running and healthy.
- `web`: running and healthy.

The stack starts PostgreSQL, initializes its separate application owner on a fresh volume, runs Alembic once, starts Gunicorn, then starts Nginx. An unsuccessful migration blocks API startup. Migration commands are not run inside each worker.

The database persists in a named Docker volume. Production must retain this volume through rebuilds and restarts.

### 5.8 Verify the public application

```bash
curl --fail https://prompt.example.com/api/health/live
curl --fail https://prompt.example.com/api/health/ready
curl --fail https://prompt.example.com/api/auth/capabilities
curl -I http://prompt.example.com/workspace
curl -I https://prompt.example.com/workspace
```

Expected behavior: HTTP redirects to HTTPS; health endpoints return `status: ok`; `/workspace` serves the React app rather than a server 404. Open the site normally, check that its certificate is trusted, then sign up and run local compilation.

Do not work around an unexpected certificate failure by permanently disabling verification. Check DNS, the hostname on the certificate, certificate expiry and the mounted chain.

## 6. Configuration reference

### 6.1 Development settings

| Setting | Required / default | Meaning |
| --- | --- | --- |
| `APP_ENV` | `development` locally | Cookie and origin validation mode |
| `DATABASE_URL` | Required | `postgresql+psycopg://...` connection URL |
| `SECRET_KEY` | Required; random, at least 32 characters | Session signing |
| `JWT_SECRET_KEY` | Required; distinct from `SECRET_KEY` | JWT signing |
| `WEB_ORIGIN` | `http://localhost:5173` | Exact browser origin |
| `API_ORIGIN` | `http://localhost:5000` | OAuth callback/API origin |
| `TRUST_PROXY` | `false` locally | Enable only behind the intended trusted ingress |
| `POSTGRES_PASSWORD` | Local Docker DB only | Must match the password in `DATABASE_URL` |

Production sets `APP_ENV=production` and matching HTTPS web/API origins automatically through Compose. Origins must contain no path, query, credentials or fragment.

### 6.2 Production public configuration — `.deploy.env`

| Setting | Default / example | Meaning |
| --- | --- | --- |
| `PUBLIC_DOMAIN` | Your hostname | Used for public origins and Nginx server name |
| `RELEASE_TAG` | `local` initially | Tag for built `promptengine-api` and `promptengine-web` images |
| `HTTP_BIND`, `HTTPS_BIND` | `0.0.0.0` | Host bind addresses |
| `HTTP_PORT`, `HTTPS_PORT` | `80`, `443` | Host port bindings |
| `TLS_CERT_DIR` | `./deploy/tls` | Directory containing certificate/key copies |
| `GUNICORN_WORKERS`, `GUNICORN_THREADS` | `2`, `4` | Worker/thread counts; each must be 1–16 |
| `GOOGLE_CLIENT_ID` | Blank initially | Google web client ID |
| `MICROSOFT_CLIENT_ID` | Blank initially | Microsoft application/client ID |
| `MICROSOFT_TENANT` | `common` | Microsoft supported-account policy |
| `BILLING_ENABLED` | `false` | Enable new paid checkout and paid-mode preset policy |
| `RAZORPAY_KEY_ID` | Blank initially | Key ID for the selected merchant environment |
| `RAZORPAY_PRO_PLAN_ID` | Blank initially | Matching monthly INR plan |
| `PRO_PRICE_PAISE` | `49900` | Draft monthly price in INR minor units |
| `PRO_DAILY_AI_LIMIT` | `100` | Finite Pro daily AI quota |
| `RAZORPAY_TOTAL_COUNT` | `120` | Number of monthly billing cycles per created subscription |

The Free quota is 10 AI requests per UTC day. Midnight UTC is 05:30 in India. This is a daily AI request quota, not a provider token budget. Local compilation does not consume AI quota but remains rate limited.

### 6.3 Production secret files

| File under `deploy/secrets/` | Corresponding API setting |
| --- | --- |
| `session_secret` | `SECRET_KEY_FILE` |
| `jwt_secret` | `JWT_SECRET_KEY_FILE` |
| `postgres_password` | Encoded into the API database URL |
| `postgres_admin_password` | Database service only |
| `openai_key` | `OPENAI_API_KEY_FILE` |
| `google_secret` | `GOOGLE_CLIENT_SECRET_FILE` |
| `microsoft_secret` | `MICROSOFT_CLIENT_SECRET_FILE` |
| `razorpay_secret` | `RAZORPAY_KEY_SECRET_FILE` |
| `razorpay_webhook_secret` | `RAZORPAY_WEBHOOK_SECRET_FILE` |

Edit a secret with a local editor or `sudoedit`, rather than typing it into a shell command:

```bash
sudoedit deploy/secrets/openai_key
sudo chmod 0444 deploy/secrets/openai_key
```

Use the corresponding filename for each provider. Enter only the value, not `KEY=value`, surrounding quotes or a JSON object. Optional files can stay empty. Maintain the private directory mode 0700 and file mode 0444; Compose file mounts preserve host permissions.

Secrets are read at process startup. After changing provider configuration or secret files, recreate the API during the intended maintenance window:

```bash
docker compose --env-file .deploy.env up -d --no-deps --force-recreate --wait api
```

Recreate the API after atomic editor replacements because a file bind mount can retain the previous inode. Session/JWT or DB password changes need the additional procedures in Section 16. Do not supply both a literal secret and its `_FILE` setting.

### 6.4 Model settings

The Compose deployment fixes `OPENAI_MODEL=gpt-4o-mini` and `OPENAI_TIMEOUT_SECONDS=20`. Application configuration accepts `gpt-4o-mini` or its approved `gpt-4o-mini-2024-07-18` snapshot and a provider timeout between 1 and 25 seconds. Other models require a reviewed code/configuration change. Adding a setting to `.deploy.env` has no effect unless the Compose service actually references it.

## 7. Google login setup

### 7.1 Create the web OAuth client

1. Open Google Cloud/Google Auth Platform using your organization's Google account.
2. Create or select the project that will own this application.
3. Configure application branding and audience/consent settings.
4. For external testing, add the intended test users; complete publishing/verification steps appropriate to your application before wider release.
5. Create an OAuth client of type **Web application**.
6. Add the exact authorized redirect URI for each environment you operate.

| Environment | Redirect URI |
| --- | --- |
| Local | `http://localhost:5000/api/auth/google/callback` |
| Production example | `https://prompt.example.com/api/auth/google/callback` |

The callback belongs to Flask, not the Vite page or extension. Do not use `/workspace` or the frontend's port 5173 as the callback. See Google's [OpenID Connect setup](https://developers.google.com/identity/openid-connect/openid-connect).

### 7.2 Configure the application

For development, edit `.env`:

```dotenv
GOOGLE_CLIENT_ID=YOUR_WEB_CLIENT_ID
GOOGLE_CLIENT_SECRET=YOUR_CLIENT_SECRET
```

For production, set `GOOGLE_CLIENT_ID` in `.deploy.env` and write the secret value into `deploy/secrets/google_secret`. Keep provider secrets on the server. Recreate the API after the change.

### 7.3 Verify login and linking

1. Confirm `/api/auth/capabilities` reports `providers.google: true`.
2. Open Login and choose Google.
3. Authenticate as an allowed test/organization user.
4. Confirm return to `/workspace` and the correct account in Settings.
5. Log out and repeat once to verify a normal new session.

If an email/password account already uses that email, sign into the existing account first and connect Google in Settings. The application intentionally does not merge identities by matching email. A disabled button means missing server configuration; a callback error often means a URI/audience/consent mismatch.

## 8. Microsoft login setup

### 8.1 Register an Entra application

1. Open the Microsoft Entra admin center with application-registration privileges.
2. Register an application for PromptEngine.
3. Choose the supported account types matching your tenant policy below.
4. Add a **Web** platform redirect URI, not an SPA or native-app redirect.
5. Record the Application/client ID.
6. Create a client secret and record its **Value**, not its identifier. Record its expiry for rotation.

| Environment | Web redirect URI |
| --- | --- |
| Local | `http://localhost:5000/api/auth/microsoft/callback` |
| Production example | `https://prompt.example.com/api/auth/microsoft/callback` |

See [Microsoft application registration](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app) and [redirect configuration](https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-redirect-uri). Console navigation labels can change; the required platform and URI are the important values.

### 8.2 Match the tenant policy

| `MICROSOFT_TENANT` | Intended accounts |
| --- | --- |
| `common` | Work/school and personal accounts |
| `organizations` | Work/school accounts |
| `consumers` | Personal Microsoft accounts |
| A tenant UUID | Accounts from that specific tenant |

Choose compatible account types in the registration. For a single-organization installation, use that organization's tenant UUID and registration policy. Do not use `common` with an incompatible single-tenant registration and expect cross-tenant sign-in.

### 8.3 Configure and verify

For development, set the client ID, secret and tenant in `.env`. For production, set `MICROSOFT_CLIENT_ID` and `MICROSOFT_TENANT` in `.deploy.env`; put the secret value in `deploy/secrets/microsoft_secret`. Recreate the API.

Confirm `providers.microsoft: true` in capabilities, then test a permitted account. Verify both intended account categories if using `common`.

Some Microsoft accounts do not provide an `email` claim suitable for automatic registration. Such a user should create/sign into an email/password account and explicitly connect Microsoft from Settings. Existing-email matches also require explicit linking. Linking does not copy a Microsoft provider token into the browser extension.

## 9. OpenAI setup and token accounting

### 9.1 Configure a server API key

1. Create or select the OpenAI API project for this service.
2. Configure the project's billing and appropriate spend controls.
3. Generate a project API key with the access needed to call the configured model.
4. Store it on the API server only.

A ChatGPT subscription does not substitute for an OpenAI API key. Follow the [OpenAI API authentication documentation](https://developers.openai.com/api/reference/overview).

Local: set `OPENAI_API_KEY` in `.env`, reload the environment and restart Flask. Production: edit `deploy/secrets/openai_key`, preserve its permissions and recreate the API.

### 9.2 Verify AI refinement

Confirm `ai_enabled: true` in `/api/auth/capabilities`. Sign in, choose AI in the workspace, enter a small task and generate once. Check the response, quota change and missing-field/assumption cards. A capability flag confirms configuration exists; it does not prove that a key is valid or billing is available.

When OpenAI is unavailable or times out, the API returns an error, normally a clear 503 provider-unavailable response. It does not silently fabricate an AI result. Use local compilation while investigating. Avoid repeatedly clicking generation after an uncertain request.

### 9.3 Understand token cards

The app counts raw input and generated prompt text using the GPT-4o-mini tokenizer. Build mode can add tokens by adding useful instructions. Compact mode can reduce text, but reduction is not guaranteed.

Metrics do not include all surrounding chat history, tools or provider request framing, and are not exact Claude/Gemini billable-token estimates. The difference is a text-token change, not guaranteed monetary savings. Generated task content is not stored in generation metrics. Explicitly saved prompts are stored in the account's library.

You do not need to host a model to use this implementation. Local compilation is deterministic code on the Flask server; AI refinement calls OpenAI through the backend.

## 10. Razorpay subscriptions and webhooks

### 10.1 Keep the first launch free

Leave `BILLING_ENABLED=false` until recurring billing is configured and validated. This disables new paid checkout and permits Free beta accounts to use custom presets. AI requests still have the Free daily limit, and OpenAI usage can still incur provider costs.

The default Pro price is a draft ₹499 per month, not an approved commercial commitment. Review pricing and operating costs before enabling it.

### 10.2 Use a separate test environment

Configure Razorpay test keys and a test plan in an isolated HTTPS staging deployment. Do not change a production customer database between test and live merchant environments. Merchant subscription capabilities and recurring/international payment eligibility depend on the actual account.

Create a plan with:

```json
{
  "period": "monthly",
  "interval": 1,
  "item": {
    "name": "PromptEngine Pro",
    "amount": 49900,
    "currency": "INR"
  }
}
```

This is a plan configuration example, not a command that creates a live charge. Use Razorpay's [plan creation workflow/API](https://razorpay.com/docs/api/payments/subscriptions/create-plan/). If you choose a different price, match that amount in `PRO_PRICE_PAISE` exactly. The implemented checkout supports monthly interval-one INR plans; do not configure a yearly or another-currency plan without modifying the implementation.

### 10.3 Configure keys and policy

For production/staging public configuration:

```dotenv
BILLING_ENABLED=false
RAZORPAY_KEY_ID=YOUR_SELECTED_ENVIRONMENT_KEY_ID
RAZORPAY_PRO_PLAN_ID=YOUR_MATCHING_PLAN_ID
PRO_PRICE_PAISE=49900
PRO_DAILY_AI_LIMIT=100
RAZORPAY_TOTAL_COUNT=120
```

Write the matching API secret into `deploy/secrets/razorpay_secret` and a separate webhook signing secret into `deploy/secrets/razorpay_webhook_secret`. Do not substitute the API secret for the webhook secret. Test-mode IDs/keys and live-mode IDs/keys must match their environments.

For local development, the equivalent literal settings are `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` in `.env`. Webhook delivery still needs a reachable HTTPS staging endpoint; a provider cannot call your private localhost directly.

### 10.4 Register the webhook

Register:

```text
https://prompt.example.com/api/webhooks/razorpay
```

Select these handled events:

- `subscription.charged`
- `subscription.cancelled`
- `subscription.halted`
- `subscription.completed`
- `subscription.expired`

Use the exact configured webhook signing secret. The backend verifies the original request body's `X-Razorpay-Signature` before applying any event. An unauthenticated browser request without that signature is expected to fail; it is not a valid webhook test.

### 10.5 Enable and test the complete lifecycle

After staging configuration is ready, set `BILLING_ENABLED=true` and recreate the API. Then:

1. Create/sign into a test user and open Settings/Billing.
2. Start one Pro checkout and complete Razorpay's test authorization/payment flow.
3. Confirm a signed charged event reaches the webhook successfully.
4. Refresh Settings and confirm effective Pro access, quota and paid expiry.
5. Confirm a duplicate event does not grant a second payment or duplicate entitlement update.
6. Validate renewal behavior supported by your test environment.
7. Request cancellation in Settings and confirm its period-end behavior.
8. Validate halted/cancelled/expired events and effective downgrade.

A checkout URL or browser return is not proof of payment. Pro is granted only from a validated charged event. Pro quota is finite; it is not an unlimited claim. Cancellation does not automatically issue a refund.

### 10.6 Recover an uncertain checkout

If the subscription creation request times out, the provider might still have created it. Do not start another checkout or manually grant Pro. Find the relevant local checkout UUID and provider subscription ID, verify they match in provider notes, then use:

```bash
docker compose --env-file .deploy.env exec -T api \
  flask --app wsgi reconcile-checkout LOCAL_CHECKOUT_UUID sub_PROVIDER_ID
```

This command validates the association and resolves checkout metadata. It does not invent a captured payment or bypass the signed charged event. See [Phase 3 billing behavior](phase-3.md) for event ordering and deduplication details.

For live launch, create/configure live-mode keys, plan and webhook in the production environment, validate them, then enable paid sales. Retain working cancellation credentials when temporarily disabling new purchases.

## 11. Chrome and Firefox extension installation

### 11.1 Build all packages

On a development/build machine, from the repository root:

```bash
npm ci
npm run build:extension
```

| Browser target | Directory | Minimum / distribution |
| --- | --- | --- |
| Chrome MV3 | `apps/extension/dist/chrome` | Chrome 114+; unpacked development installation |
| Firefox MV3 | `apps/extension/dist/firefox` | Desktop Firefox 140+; unsigned temporary installation |
| Firefox MV2 | `apps/extension/dist/firefox-mv2` | Desktop Firefox 140+; alternative manifest target |

Firefox manifests declare Android 142+ for consent compatibility, but Android operation has not been verified. These requirements reflect the packaged manifests, not a claim that every future browser/vendor UI has been validated.

The packages contain no deployment URL or provider secret. Each installed browser is configured and paired separately.

### 11.2 Install Chrome

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Select **Load unpacked**.
4. Select the `dist/chrome` folder containing `manifest.json`.
5. Pin PromptEngine using Chrome's extension menu.
6. Open the toolbar popup.

If given a packaged ZIP, extract it first. Select the folder with `manifest.json` at its root, not the ZIP itself or the entire source monorepo.

### 11.3 Install Firefox temporarily

1. Open `about:debugging#/runtime/this-firefox`.
2. Choose **Load Temporary Add-on**.
3. Select `manifest.json` in `dist/firefox` or `dist/firefox-mv2`.
4. Open the extension popup and review browser data-consent prompts.

Temporary add-ons disappear after Firefox restarts. Normal distribution requires Mozilla signing. A Chrome-style ZIP is not automatically a signed Firefox release. Signing/store publication is a separate release step; it has not been performed by this project setup.

### 11.4 Configure and pair

In the popup, enter:

| Setting | Local | Production |
| --- | --- | --- |
| API server address | `http://localhost:5000` | `https://prompt.example.com` |
| Web app address | `http://localhost:5173` | `https://prompt.example.com` |
| Browser name | A useful device label | A useful device label |

Use origins only, without `/api`, `/workspace`, paths or query strings. Production requires HTTPS. Review the data notice, check consent and choose **Connect workspace**. Grant access to the selected API host when the browser requests it.

Then:

1. Choose **Create pairing code**.
2. Open the approval page and sign into your web account.
3. Enter the six-digit code in `/settings/extensions`.
4. Choose **Review browser**, inspect the device and approve it.
5. Return to the popup and choose **I approved this browser**.
6. Confirm the paired workspace and quota appear.

Pairing codes last five minutes and are single-use. The resulting browser token lasts 30 days and can be revoked. Pair again after expiry. Changing either workspace origin clears local authentication and requires pairing again.

### 11.5 Generate and insert safely

Open a supported HTTPS chat tab on `chatgpt.com`, legacy `chat.openai.com`, `claude.ai` or `gemini.google.com`. Open PromptEngine from the toolbar, compile/refine your task, and click Insert.

Existing nonempty drafts require a second **Replace draft** confirmation. Choose the copy option instead to preserve that draft. Insertion creates plain text and registers input events; it never submits the chat. Review the text in the assistant before you send it yourself.

Unsupported pages, changed composers, denied tab access or unavailable editing operations use clipboard fallback. If clipboard permission fails, select and copy the generated output manually. Do not add broad permanent chat permissions to work around a changed editor.

For longer generation, choose **Open editor in a tab**; it keeps the original target tab. Keep the popup open while generating. Draft/results use temporary extension session storage and are not automatically saved to History.

### 11.6 Disconnect and upgrade

Use confirmed **Disconnect this browser** in the popup to revoke the token and clear local access. If the API is unreachable, local access clears; revoke the device later from web Settings. Web device revocation also blocks an existing extension token.

After rebuilding a Chrome package, click Reload on `chrome://extensions`. For Firefox temporary installs, reload/reinstall the add-on. Manifest or permission changes may require user approval. Test signed-in ChatGPT/Claude/Gemini editors before a public extension release because their DOM structures can change.

## 12. First-use application walkthrough

### 12.1 Create and verify your account

1. Open the web app and choose Signup.
2. Use a real email label and a password of 12–128 characters.
3. Confirm navigation to the workspace.
4. Open Settings and verify the account email and Free quota.
5. Sign out and sign in again to confirm session behavior.

Web sessions last 12 hours and use an HttpOnly JWT cookie. The separate readable CSRF cookie is intentional. There is no implemented password reset/recovery, email-verification or account-email-change flow; do not assume an outbound mail system is configured.

### 12.2 Build a prompt

1. Select one of six default presets: Coding, Website Briefs, Business Proposals, Marketing, Research or Professional Communication.
2. Enter the objective and raw command, then available context fields.
3. Choose tone and Build or Compact mode.
4. Choose local compilation initially, or AI refinement when configured.
5. Generate and review the output, missing information, clarification questions and assumptions.
6. Copy it to your target assistant or explicitly save it with title/tags.

Saving is optional and account-private. Generation metrics contain token counts and metadata, not raw task text. History contains only prompts the user explicitly saved.

### 12.3 Use History and presets

Open History, search by title, inspect a saved prompt, edit/reuse it and verify deletion confirmation. Search is server-side title search; it is not full-content search.

Create a custom preset from Presets. Include an `objective` field and an output constraint. Custom presets are available to Free users during the free beta; after billing is enabled, creation/use requires effective Pro access. The backend enforces ownership and a maximum of 50 custom presets per account.

### 12.4 Verify Settings and devices

Settings shows current quota, linked providers, generation totals and subscription metadata where configured. Pair a browser through device settings, confirm it appears with the intended name, revoke it, and confirm the extension can no longer make authenticated requests. This is a useful first operational check.

## 13. Validation and automated tests

### 13.1 Non-database checks

From the repository root with dependencies installed:

```bash
.venv/bin/ruff check apps/api
.venv/bin/ruff format --check apps/api
npm run typecheck
npm run build
npm run test:web
npm run build:extension
npm run test:extension
npm run lint:firefox --workspace @promptengine/extension
```

Firefox lint currently reports no errors and two documented React bundle warnings. See the Phase 5 guide for the warning explanation.

### 13.2 API integration tests — disposable database only

Tests truncate all application tables. Create a separate database with `test` in its name. For the local Docker database:

```bash
docker compose -f compose.dev.yml exec -T db \
  createdb -U promptengine promptengine_test
```

Run tests using the same connection credentials but the new database name. With local `.env` loaded, set the test URL from the existing URL without exposing its password:

```bash
export TEST_DATABASE_URL="${DATABASE_URL%/*}/promptengine_test"
cd apps/api
../../.venv/bin/pytest -q
cd ../..
```

The supplied local database's initialization account can create that test database. The production application role cannot create databases; do not broaden its permissions to run tests in production.

The Phase 6 verified API suite had 95 passing tests, including file-secret behavior. Counts can change in later releases; the workflow result for your commit is the source of truth.

### 13.3 Browser workflows

Stop normal development servers first; tests start their own servers on ports 5000/5173. Use an isolated browser test database whose name contains `test`. In a test shell:

```bash
export APP_ENV=development
export DATABASE_URL="${DATABASE_URL%/*}/promptengine_test"
export WEB_ORIGIN=http://localhost:5173
export API_ORIGIN=http://localhost:5000
export BILLING_ENABLED=false
export OPENAI_API_KEY=
export GOOGLE_CLIENT_ID=
export GOOGLE_CLIENT_SECRET=
export MICROSOFT_CLIENT_ID=
export MICROSOFT_CLIENT_SECRET=
npx playwright install --with-deps chromium
npm run test:e2e --workspace @promptengine/web
npm run build:extension
npm run test:browser --workspace @promptengine/extension
npm run test:installed --workspace @promptengine/extension
```

Retain the distinct session/JWT secrets loaded from the local configuration. Web and installed-extension tests use actual Flask/PostgreSQL. Composer fixtures simulate service-shaped pages and do not sign into live assistants. Installed Chrome testing requires full Chromium with extension support; a serverless headless-shell binary is insufficient.

### 13.4 Production container validation

The separate GitHub Actions workflow `Production container validation` builds and starts the actual Docker stack with disposable credentials and explicitly trusted test TLS. It verifies HTTPS, cookies/CSRF, SPA/assets, compiler, non-superuser DB privileges, limits, query-free logs, backup/restore and API replacement.

`deploy/smoke.py` is locked to `promptengine.test` and modifies/restores its database. Do not use it as a health check for a real customer installation. For production health monitoring use `/api/health/ready` instead.

Successful CI does not prove your DNS, live certificate renewal, OAuth consent or merchant account is configured correctly. Complete the manual provider and public-host checks for your installation.

## 14. Day-to-day operations and TLS renewal

### 14.1 Service status and logs

From the production checkout:

```bash
docker compose --env-file .deploy.env ps -a
docker compose --env-file .deploy.env logs --tail 100 api
docker compose --env-file .deploy.env logs --tail 100 web
docker compose --env-file .deploy.env logs --tail 100 migrate
```

Logs omit query strings, auth headers and request bodies. Keep normal production logging; enabling SQL/HTTP debug output can expose data. Container logs rotate at three 10 MB files per service.

Health checks distinguish Nginx availability, application process liveness and database/schema readiness. A Docker health check does not automatically restart an unhealthy but still-running process. Configure external HTTPS/readiness and certificate-expiry alerts, plus disk/CPU/memory/database monitoring.

After a host reboot, long-running services use `unless-stopped` restart policy. Confirm health and ingress afterward. The migration job is not a long-running service; do not expect it to rerun on every reboot.

### 14.2 Daily expired-auth cleanup

Run:

```bash
docker compose --env-file .deploy.env exec -T api flask --app wsgi cleanup-auth
```

This removes expired sessions, extension tokens, pairing records and rate-limit buckets. To schedule it as the deployment operator, add an appropriate cron entry, for example:

```cron
15 3 * * * cd /opt/promptengine && /usr/bin/docker compose --env-file .deploy.env exec -T api flask --app wsgi cleanup-auth >> /opt/promptengine/housekeeping.log 2>&1
```

Check `command -v docker` before using that path and configure rotation for the host log. Confirm the host timezone with `timedatectl`; cron follows the host's timezone, while application quota boundaries remain UTC.

### 14.3 Renew and deploy TLS correctly

The certificate tool renews its own certificate lineage. Nginx uses the copies in `deploy/tls`, so renewed certificates must also be copied and the web container recreated. Reloading Nginx alone is insufficient after a host file is atomically replaced and the container retains an old file mount.

For a standalone Certbot certificate, a maintenance renewal sequence is:

1. Stop only PromptEngine's `web` container so port 80 is free.
2. Renew the selected certificate lineage.
3. If renewal succeeds, install both certificate files into `deploy/tls`.
4. Recreate/start `web` even if renewal fails, using the still-valid previous copies.
5. Check the public certificate and HTTPS readiness.

Use `sudo certbot certificates` to identify the actual lineage/certificate name. `--cert-name` can differ from the domain if multiple lineages were created. Example operator commands during the maintenance window:

```bash
docker compose --env-file .deploy.env stop web
sudo certbot renew --cert-name prompt.example.com
# If the renewal command succeeded:
sudo install -m 0444 /etc/letsencrypt/live/prompt.example.com/fullchain.pem deploy/tls/fullchain.pem
sudo install -m 0444 /etc/letsencrypt/live/prompt.example.com/privkey.pem deploy/tls/privkey.pem
# Run this restart even if renewal failed; retain the prior copies in that case:
docker compose --env-file .deploy.env up -d --no-deps --force-recreate --wait web
curl --fail https://prompt.example.com/api/health/ready
```

Do not put these conditional comments into an unattended script and assume failure handling is automatic. Build a tested host renewal unit with an unconditional restart/failure alert, or use DNS validation and a deployment hook for renewal without stopping the web container. The repo does not install a host Certbot timer/hook for you.

A renewal dry-run must also free port 80 for a standalone challenge. Verify your automation and alerts before expiry. See [Certbot renewal and hooks](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates).

## 15. Database backup and restore

### 15.1 Take a backup

```bash
cd /opt/promptengine
sh deploy/backup.sh
```

The script prints a successful dump path under `backups/`. It uses PostgreSQL custom format and a temporary file renamed only after success. The host directory is private and dump files use mode 0600.

A backup can be taken while the application is running. A successful command confirms dump creation, not successful restoration. Test recovery periodically.

### 15.2 Schedule and protect backups

A sample deployment-account cron entry:

```cron
0 2 * * * cd /opt/promptengine && sh deploy/backup.sh >> /opt/promptengine/backup.log 2>&1
```

Add failure monitoring, encrypted off-host copying and a retention policy. Do not store the only backup on the same VPS disk. Database dumps contain personal account data and saved prompts; restrict who can download them.

Back up the following separately using encrypted storage:

- `.deploy.env` and the deployed commit/release tag.
- `deploy/secrets/`, including stable signing and DB credentials.
- Certificate configuration/renewal arrangements and any required TLS copies.
- Backup/monitoring schedule configuration.

The database dump alone does not contain provider secrets or an entire deployment configuration. Avoid placing backup files in the public frontend directory.

### 15.3 Inspect and restore during maintenance

Use an absolute dump path and a matching application release/schema. Take a fresh backup of the current database before intentionally replacing it.

```bash
sh deploy/restore.sh --replace-database /absolute/path/to/promptengine-backup.dump
```

The script stops web/API, restores into PostgreSQL and leaves serving services stopped. A restore failure also leaves them stopped for investigation. Inspect records and migration state before restarting:

```bash
docker compose --env-file .deploy.env exec -T db \
  psql -U promptengine -d promptengine -c 'SELECT version_num FROM alembic_version;'
docker compose --env-file .deploy.env up -d --wait --wait-timeout 120 api web
curl --fail https://prompt.example.com/api/health/ready
```

Check a saved prompt and account workflow afterward. A schema from a newer application may not work with an older image. Do not use destructive migration downgrades as a routine rollback shortcut.

`docker compose down` retains the named database volume. **`docker compose down -v` deletes it.** Use the latter only for deliberately disposable installations.

## 16. Updates, rollback and credential changes

### 16.1 Prepare a reviewed release

Record the current commit, image release tag and backup location. Confirm the next release passed application and container CI. Keep runtime settings/secrets intact.

```bash
cd /opt/promptengine
git status --short
git rev-parse HEAD
sh deploy/backup.sh
git fetch origin
git switch main
git pull --ff-only
```

Do not discard operator edits or local code changes automatically. Resolve them before continuing. A reproducible release may use a reviewed tag/commit instead of `main`.

Set a unique `RELEASE_TAG` in `.deploy.env` before building, for example your release identifier. Retain prior image tags for rollback. Do not prune images/volumes indiscriminately.

### 16.2 Apply an update with a maintenance window

```bash
docker compose --env-file .deploy.env build
docker compose --env-file .deploy.env stop web api
docker compose --env-file .deploy.env run --rm --no-deps migrate
docker compose --env-file .deploy.env up -d --force-recreate --wait --wait-timeout 120
```

Proceed to the final `up` only if migrations succeeded. An interactive shell does not automatically stop after a command failure. Do not run concurrent releases. Verify status, public health, login, generation, history and pairing after the update.

This procedure has a maintenance interruption; it is not a zero-downtime deployment. Nginx uses Docker DNS to recover from a changed API container address.

### 16.3 Roll back deliberately

If the database schema is compatible, check out the previous release, restore its `RELEASE_TAG`, and start its retained images with `--no-build`. If the schema is incompatible, restore the matching database backup during maintenance as well. Retain stable runtime secrets unless performing a planned credential rotation.

Do not run a previous application against an unknown newer schema, and do not claim rollback is complete until you verify real workflows.

### 16.4 Change provider and signing secrets

Provider secret replacement: edit the file, preserve its mode, recreate the API and perform one real provider check. Monitor provider-secret expiry, particularly Microsoft registrations.

Session/JWT signing-secret replacement: expect existing web sessions to become invalid. Coordinate the change and test login. Extension tokens are opaque server-checked tokens, not web JWTs; revoke devices explicitly when their access should end.

Database password rotation requires changing the PostgreSQL role password and the matching host secret together. Editing a password file alone does not update an initialized database. Plan downtime or a reviewed rotation procedure and back up first. The separate PostgreSQL administrator credential is never the application's connection credential.

## 17. Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Startup rejects missing/short/equal secrets | Invalid API signing settings | Check configuration sources; use distinct random session/JWT values |
| Startup rejects database URL | Wrong dialect/URL | Use `postgresql+psycopg://`; SQLite is unsupported |
| `Cannot read ..._FILE` | Missing mount or permissions | Confirm host file exists and private directory/file modes are correct; recreate container after file replacement |
| `Configure only ... or ..._FILE` | Both literal and file configured | Choose one source; production Compose expects file sources |
| DB password authentication fails | URL/file mismatch or existing volume's password differs | Verify intended connection and perform deliberate rotation; do not delete the data volume |
| `migrate` exits nonzero | DB connectivity, permissions or migration failure | Inspect migration logs; keep serving services stopped until resolved |
| `migrate` exited 0 | Normal one-shot completion | No fix required |
| API readiness is 503 | DB/schema unavailable | Check DB health and migration completion |
| Web port bind fails | Another host service owns 80/443 | Review existing ingress; do not stop unrelated apps blindly |
| Nginx cannot read certificate | Missing/mis-mounted files or permissions | Check both copied files, mount sources and private parent layout |
| Public TLS validation fails | DNS mismatch, expired/wrong certificate or incomplete chain | Check actual hostname and fullchain; deploy renewed files and recreate web |
| Nginx 502 after API replacement | Upstream not healthy or DNS recovery interval | Check API; allow DNS refresh; inspect logs if persistent |
| Local signup/login 403 or cookies appear missing | Origin/hostname mismatch | Use browser `localhost:5173`, matching `WEB_ORIGIN`, and the Vite proxy |
| Mutation fails CSRF | Missing session/CSRF or stale cookie | Sign in again; ensure browser sends cookies and readable CSRF header |
| Google/Microsoft button disabled | Missing ID or secret in backend | Fill both, reload environment/recreate API; check capabilities |
| OAuth redirect URI mismatch | Wrong scheme/hostname/port/path | Copy the exact Flask callback URI into the provider console |
| OAuth state expires | Approval flow delayed/session changed | Restart sign-in; keep configured host/origin stable |
| `account_link_required` | Email already belongs to an existing account | Sign in with the existing method and link in Settings |
| Microsoft lacks a usable email claim | Provider account claim limitation | Register/sign in with email/password, then explicitly link Microsoft |
| AI option disabled | OpenAI key blank | Configure it or use local compilation |
| AI unavailable/503 | Key/billing/model/network/timeout issue | Check provider account and server outbound access; use local compilation while diagnosing |
| AI quota exhausted | Daily UTC limit reached | Check usage and next UTC day; local compilation remains available |
| Many users hit one IP limit | Additional ingress obscures client IP | Review trusted proxy design; never trust arbitrary forwarded headers |
| Paid upgrade disabled | Free launch policy | Enable only after complete merchant setup |
| Billing plan mismatch | Wrong amount/currency/interval/plan mode | Match monthly interval-one INR plan and minor-unit price |
| Payment completed but account remains Free | Signed charged webhook missing/rejected/delayed | Inspect provider delivery and webhook configuration; do not grant from browser redirect |
| Checkout uncertain | Provider may have created subscription after timeout | Reconcile the exact local/provider IDs; avoid duplicate purchase attempts |
| Webhook returns 401 | Missing/wrong signature or secret | Verify provider webhook secret and unmodified body forwarding |
| Extension says connect/pair again | Origin changed, token expired or revoked | Check settings and create a fresh pairing request |
| Pairing exchange fails | Expired/unapproved/used code or wrong secret | Review and approve a new code within five minutes |
| Extension installation rejects ZIP | ZIP not extracted/wrong manifest target | Select the browser-specific unpacked manifest folder |
| Firefox extension disappears | Temporary installation | Reload temporarily or distribute a signed add-on |
| Insert copies instead | Unsupported page, composer changed or active-tab access denied | Open toolbar on target chat; copy/paste and review the adapter before release |
| Existing draft remains | Replacement confirmation not approved | Preserve it or explicitly choose Replace draft |
| Backup succeeded but off-host copy failed | Only local dump exists | Repair transfer and alerts; a same-disk copy is not disaster recovery |
| Container unhealthy but not restarted | Health status alone is not restart automation | Investigate and alert; restart only after identifying the cause |

### Useful diagnostics

```bash
docker compose --env-file .deploy.env ps -a
docker compose --env-file .deploy.env logs --tail 100 db migrate api web
docker compose --env-file .deploy.env exec -T web nginx -t
docker compose --env-file .deploy.env exec -T api flask --app wsgi db current
df -h
docker system df
```

Share sanitized status/error codes when seeking help. Do not paste secret files, database URLs with passwords, cookies, access tokens, provider callback codes or full customer prompt content.

## 18. Launch checklist and current boundaries

### 18.1 Installation acceptance

- [ ] Reviewed code/release recorded; application/container CI passed for that revision.
- [ ] DNS points to the intended host and trusted TLS validates publicly.
- [ ] Certificate renewal deploys new copies and restarts web; expiry alert tested.
- [ ] DB/API ports are not publicly published.
- [ ] PostgreSQL, API and web healthy; migration completed successfully.
- [ ] Stable signing/DB secrets retained privately and backed up separately.
- [ ] Signup/login/logout, local compilation, explicit save/history/reuse tested.
- [ ] Selected Google/Microsoft providers validated with real permitted accounts.
- [ ] OpenAI key/budget and one small refinement tested if enabled.
- [ ] Billing stays disabled, or merchant plan/webhooks/cancellation tested before enabling.
- [ ] Chrome pairing/insertion/revocation tested; Firefox signing/runtime checks planned.
- [ ] Off-host backups and a restore drill completed.
- [ ] HTTPS readiness, expiry, disk and backup-failure monitoring configured.
- [ ] Cleanup/maintenance responsibilities and host timezone documented.

### 18.2 Current product boundaries

The implemented system includes authentication, prompt compilation, quotas, saved prompts, custom presets, recurring billing integration, paired extensions and single-host deployment. It does not currently implement password reset/recovery, account email change, email verification, a super-admin console, automated dunning/invoicing/refunds, multi-host high availability, or automatic extension-store publication.

Public availability should be matched to these limitations and to your operational support process. Do not present configuration flags, CI fixtures or unsigned packages as proof of completed live provider onboarding. Token differences are text measurements, not guaranteed money savings.

## 19. File map and official references

### 19.1 Main files

| Path | Purpose |
| --- | --- |
| `.env.example` | Local API configuration template |
| `compose.dev.yml` | Local PostgreSQL only |
| `docker-compose.yml` | Production services, networks, mounts and startup ordering |
| `deploy/init.py` | Private production initialization |
| `deploy/postgres/010-app.sh` | Fresh-volume administrator/application role separation |
| `apps/api/Dockerfile`, `gunicorn.conf.py`, `wsgi.py` | Production API image and startup |
| `apps/api/promptengine/config.py`, `environment.py` | Validation and file-secret loading |
| `apps/api/migrations/` | Alembic schema versions |
| `apps/web/Dockerfile` | Build and serve compiled frontend |
| `deploy/nginx/` | HTTPS/static/API proxy configuration |
| `apps/extension/scripts/package.mjs` | Browser-specific manifest/package generation |
| `deploy/backup.sh`, `restore.sh` | Backup and maintenance recovery |
| `deploy/smoke.py` | Disposable CI-only full-stack recovery test |
| `.github/workflows/phase-1.yml`, `deployment.yml` | Application and production-container validation |

Phase guides remain useful for detailed API contracts: [1 — Auth/database](phase-1.md), [2 — Compiler](phase-2.md), [3 — Billing](phase-3.md), [4 — Web](phase-4.md), [5 — Extension](phase-5.md), [6 — Deployment](phase-6.md).

### 19.2 Official provider/platform references

- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/)
- [Docker startup ordering](https://docs.docker.com/compose/how-tos/startup-order/)
- [Certbot installation](https://certbot.eff.org/instructions)
- [Certbot renewal hooks](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates)
- [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)
- [Microsoft app registration](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app)
- [Microsoft Web redirect configuration](https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-redirect-uri)
- [OpenAI API authentication](https://developers.openai.com/api/reference/overview)
- [Razorpay plan creation](https://razorpay.com/docs/api/payments/subscriptions/create-plan/)
- [Chrome active-tab access](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab)
- [Firefox built-in data consent](https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/)
- [Playwright installed-extension testing](https://playwright.dev/docs/chrome-extensions)

Provider portals and external installation requirements can change. The exact callback URLs, application configuration keys and package manifests in the deployed commit remain authoritative for this application.
