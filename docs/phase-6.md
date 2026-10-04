# Phase 6 — Production deployment

## Files and behavior

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | PostgreSQL, one-shot migrations, Gunicorn API and TLS/static frontend; private DB/API ports, readiness ordering, persistent database volume |
| `apps/api/Dockerfile` | Python 3.12, locked dependencies, cached tokenizer, non-root application image |
| `apps/api/gunicorn.conf.py` | Two processes/four threads by default, graceful termination, bounded worker recycling and query-free logs |
| `apps/api/promptengine/environment.py`, `wsgi.py` | Explicit `_FILE` secret loading and encoded database credentials |
| `apps/web/Dockerfile` | Node/Vite build stage and non-root Nginx runtime; no Node server in production |
| `deploy/nginx/` | HTTP redirect, TLS 1.2/1.3, SPA routing, immutable hashed assets, same-origin `/api` proxy, overwritten forwarding headers and dynamic Docker DNS |
| `deploy/init.py`, `deploy/postgres/010-app.sh` | Generate independent secrets and initialize an application database owner without superuser, role-creation or replication privileges |
| `deploy/backup.sh`, `restore.sh` | PostgreSQL custom-format backup and explicit maintenance restore |
| `deploy/smoke.py` | Disposable test deployment: actual HTTPS/auth/CSRF/compiler, backup/restore, rate limits, log redaction and API replacement |
| `.github/workflows/deployment.yml` | Build/run the real production containers and execute recovery checks |

This is a single-host deployment. It does not promise zero-downtime releases, database failover, automatic scaling, or a configured external monitoring provider. Images use explicit major/minor base tags and locked application dependencies; resolve and record image digests for a release if immutable supply-chain pinning is required.

## Host prerequisites

Use a Linux host with Docker Engine and the Compose v2 plugin (2.24+), Python 3, Git and OpenSSL. A small starting host is 2 vCPU/4 GB RAM; measure traffic, AI latency and database connection use before changing worker counts. Install Docker using its [official Ubuntu guide](https://docs.docker.com/engine/install/ubuntu/). Docker access grants administrative control of that host.

Choose the real public hostname, point its DNS A/AAAA records to the server, and allow inbound TCP 80/443. Only Nginx publishes ports; do not expose PostgreSQL 5432 or API 8000. This configuration expects Nginx here to own public HTTP/HTTPS. If another app already owns ports 80/443 on your VPS, integrate with that proxy separately or use another host/IP; do not stop unrelated applications. Optional bind/port settings support controlled staging, but production OAuth/origin settings expect public HTTPS on 443.

## Initial configuration

From a checkout of the reviewed release:

```bash
python3 deploy/init.py --domain prompt.your-company.com
```

Replace the example hostname with yours. Initialization refuses to overwrite an existing `.deploy.env` or secret directory. `.deploy.env`, `deploy/secrets`, `deploy/tls` and backups are git-ignored and excluded from Docker build contexts. Keep the checkout under a private deployment account. Secret directories are mode 0700; individual file mounts are mode 0444 so non-root containers can read them. Compose file secrets are host files, not an encrypted external secrets manager.

Edit `.deploy.env` with public OAuth client IDs and billing settings. Fill the respective files in `deploy/secrets` with one line each:

| File | Setting |
| --- | --- |
| `openai_key` | Optional OpenAI API key; blank keeps local compilation working |
| `google_secret` | Google OAuth client secret |
| `microsoft_secret` | Microsoft OAuth client secret |
| `razorpay_secret` | Razorpay API secret |
| `razorpay_webhook_secret` | Distinct Razorpay webhook signing secret |

An administrator can use `sudoedit` for existing read-only secret files. Preserve file mode 0444 after an editor replaces a file. Do not put secrets into Vite environment variables, image build arguments, GitHub commits or command lines. The API also supports `<SECRET_NAME>_FILE` for explicit file-based configuration outside Compose; configuring both a literal and a file fails clearly.

Generated `postgres_password`, `postgres_admin_password`, `session_secret` and `jwt_secret` must be retained across releases. Changing only the password file does **not** change an initialized PostgreSQL user's password. Rotate database credentials deliberately in PostgreSQL and the file together. Rotating session/JWT secrets invalidates existing web sessions; keep a private encrypted backup of configuration and secrets separately from database dumps.

## TLS certificates

Install Certbot using its [official instructions](https://certbot.eff.org/instructions). Before this stack starts, obtain a trusted certificate for your real hostname. Standalone issuance requires port 80 to be available; DNS validation is an alternative for occupied ports.

```bash
sudo certbot certonly --standalone -d prompt.your-company.com
sudo install -m 0444 /etc/letsencrypt/live/prompt.your-company.com/fullchain.pem deploy/tls/fullchain.pem
sudo install -m 0444 /etc/letsencrypt/live/prompt.your-company.com/privkey.pem deploy/tls/privkey.pem
```

The containing TLS directory remains private. Mounts use individual files, so Nginx can read them as UID 101 without traversing the host's private directory. Both files must exist before `up`; Compose refuses to create missing certificate paths. The private key is never copied into an image.

Certificate renewal must also copy updated files and recreate the web container because file bind mounts retain their original inode. For a standalone certificate, stop only this stack's web container while renewing, then copy and start it even if renewal fails; schedule this as a maintenance operation. For uninterrupted challenge handling, configure DNS validation and a deploy hook that copies the two files and runs `up -d --no-deps --force-recreate web`. Verify renewal with Certbot's dry-run and check expiration monitoring. Do not assume the host timer alone refreshes mounted copies. See [Certbot renewal hooks](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates).

`--self-signed` on `deploy/init.py` generates a two-day test certificate only. CI explicitly trusts that certificate; production must use a publicly trusted certificate.

## Start and verify

```bash
docker compose --env-file .deploy.env config --quiet
docker compose --env-file .deploy.env build
docker compose --env-file .deploy.env up -d --wait --wait-timeout 120
docker compose --env-file .deploy.env ps -a
docker compose --env-file .deploy.env exec -T web nginx -t
curl --fail https://prompt.your-company.com/api/health/ready
```

The PostgreSQL administrator password is mounted only into the database service; the API receives a separate password for the non-superuser database owner `promptengine`. The initialization script runs only for an empty volume. An existing volume must already contain these roles/databases; never delete a volume to change credentials.

PostgreSQL must become healthy, then the one-shot `migrate` container must successfully upgrade Alembic before API startup. Migrations do not run concurrently in Gunicorn workers. The tokenizer vocabulary is downloaded at image build time so compiling works in the read-only runtime without an initial vocabulary download. Provider credentials and database access remain runtime-only.

`/api/health/live` is process liveness; `/api/health/ready` checks database/schema access; the web health check checks Nginx itself. Docker health status does not automatically restart an unhealthy running process: set an external HTTPS uptime/readiness alert and investigate failures. Container crash restart policy is `unless-stopped`. Logs rotate at three 10 MB files per service and exclude query strings, bodies and auth headers. Do not enable HTTP/SQL debug logs in production.

Open the site and verify signup, login, history, settings and local generation. Register OAuth callbacks exactly:

- `https://prompt.your-company.com/api/auth/google/callback`
- `https://prompt.your-company.com/api/auth/microsoft/callback`

Complete provider consent/tenant configuration as described in Phase 4; buttons become available only with both client ID and secret. For the extension, set both origins to `https://prompt.your-company.com`, then pair through web Settings.

Free launch remains `BILLING_ENABLED=false`. Enable billing only after real Razorpay plan IDs, matching price, webhook secret and recurring-billing settings are configured. Register `https://prompt.your-company.com/api/webhooks/razorpay` with the events in Phase 3 and perform test/live-mode validation. Provider APIs, customer payment flows and OAuth cannot be validated without your actual credentials and public domain.

## Backup, restore and updates

```bash
sh deploy/backup.sh
```

The script writes a mode-0600 custom-format dump to `backups/` and prints its filename after success. Schedule it using a host timer/cron, encrypt and copy dumps off the host, and apply a retention policy. Dumps include personal account data and saved prompts; they do not include TLS/provider/session secrets. A dump on the same disk is not disaster recovery. Test restoration on a separate deployment.

For a planned release, back up first and build before stopping traffic. Use a unique `RELEASE_TAG` in `.deploy.env` and retain the previous images/settings. For a maintenance update:

```bash
docker compose --env-file .deploy.env build
docker compose --env-file .deploy.env stop web api
docker compose --env-file .deploy.env run --rm --no-deps migrate
docker compose --env-file .deploy.env up -d --force-recreate --wait --wait-timeout 120
```

A failed migration leaves the serving services stopped; inspect it rather than automatically restarting an incompatible old image. Do not run concurrent deployment commands. `up` recreates the migration container in this maintenance workflow, so migration completion gates API startup. Nginx resolves the API through Docker DNS and recovers when its container IP changes. CI tests a forced API replacement.

For restoration, this command intentionally replaces the database and leaves the API/web stopped:

```bash
sh deploy/restore.sh --replace-database /absolute/path/to/backup.dump
```

Use a matching release/schema, verify restored records, then start services. Do not blindly downgrade migrations or restore a newer schema into older application code. Image rollback is safe only when the database schema is compatible; otherwise restore the matching dump during maintenance. `docker compose down` retains the named volume; **`down -v` deletes the database** and is only for disposable tests.

Daily housekeeping can be scheduled as:

```bash
docker compose --env-file .deploy.env exec -T api flask --app wsgi cleanup-auth
```

Use Phase 3's reconciliation command for payment drift according to that guide. No scheduled external messages or payment changes are performed by this phase.

## Validation boundaries

Local checks include Python lint/format, shell syntax, Python compilation and file-secret behavior. This workspace has no Docker daemon. The separate production-container CI workflow builds both images, starts real PostgreSQL/Gunicorn/Nginx, trusts test TLS, checks HTTPS/cookies/CSRF/routing/compiler/limits/log redaction, and performs a real backup/restore and API replacement. It never contacts OpenAI, OAuth providers or Razorpay. Existing application CI continues to run PostgreSQL, web and installed-extension tests.

Startup ordering follows [Docker Compose dependencies](https://docs.docker.com/compose/how-tos/startup-order/); file mounts follow [Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/). Proxy timeouts and worker behavior follow [Gunicorn settings](https://docs.gunicorn.org/en/stable/settings.html) and [Nginx proxy documentation](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).
