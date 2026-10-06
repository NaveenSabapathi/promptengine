# PromptLogic enterprise deployment and recovery

This release extends the existing PostgreSQL/Flask/React application. Its production web and API origin is **https://promptlogic.io**. The extension uses this origin by default and requests only its optional host permission in store builds. Chrome MV3, Firefox MV3 and Firefox MV2 packages are generated separately.

## 1. Upgrade an existing installation

Do this in a maintenance window after the pull request passes both CI workflows and is merged. Retain the existing `.deploy.env`, Docker database volume and all secret files. Do not rerun `deploy/init.py` over an initialized installation. Do not use `docker compose down -v` on production.

```bash
cd /srv/promptengine
git fetch origin main
git checkout main
git pull --ff-only
python3 deploy/enterprise-init.py
sh deploy/backup-cron.sh
```

`enterprise-init.py` creates missing TOTP, dataset, mail-hook and replication keys without rotating existing values. File contents must never be printed, committed, or copied into Actions variables. Existing session and database credentials remain in place. **Back up encryption keys with the database:** losing the TOTP key makes existing authenticators unusable; losing the dataset key makes queued training records unreadable.

Set `PUBLIC_DOMAIN=promptlogic.io` in `.deploy.env`. Configure Google/Microsoft callbacks to `https://promptlogic.io/api/auth/google/callback` and `https://promptlogic.io/api/auth/microsoft/callback`. Set a trusted TLS certificate in `deploy/tls`; self-signed certificates are for CI only.

For a locally built maintenance deployment:

```bash
docker compose --env-file .deploy.env build
# Drain requests first; never migrate while an incompatible release accepts writes.
docker compose --env-file .deploy.env stop web api
docker compose --env-file .deploy.env run --rm --no-deps migrate
docker compose --env-file .deploy.env up -d --wait --wait-timeout 180 api web
curl --fail https://promptlogic.io/api/health/ready
```

The new migration is additive: existing accounts remain non-admin, MFA and dataset consent remain disabled, existing prompts/presets remain personal, and paid subscription fields keep their meaning. PostgreSQL DDL is transactional and lock acquisition times out after five seconds instead of waiting indefinitely. Retry a failed migration only after resolving the cause. Downgrade scripts exist for disposable test databases; **do not downgrade production with team, MFA, audit or referral data present**, because those feature tables/columns would be removed.

## 2. Administrator bootstrap and authorization

1. Register a normal account and sign in with email/password or configured Google/Microsoft SSO.
2. Open **Security & privacy**, enter your current password if the account has one, and enroll an authenticator within five minutes of signing in. QR generation happens on the server; no external QR service receives the secret.
3. Confirm the six-digit code and save all eight recovery codes. Only Argon2 hashes are stored. The plaintext recovery codes are displayed once.
4. Grant the first administrator from the trusted host:

```bash
docker compose --env-file .deploy.env exec -T api flask --app wsgi grant-admin admin@your-company.example
```

There is no public admin-role assignment endpoint. Signup rejects `is_admin` and other unexpected account fields. Admin APIs require a web cookie session, a server-side admin role, enabled MFA, and a verification in the last five minutes. Extension tokens cannot call them. Verify a new code in Security when the verification window expires. Used TOTP time steps and recovery codes are rejected under a PostgreSQL row lock; a code cannot succeed twice concurrently.

The dashboard provides total accounts, active web-session accounts, today's AI usage, the last 24 hours of provider token counts and prompt token deltas, API failure rate and mean provider latency. Exact-email lookup returns bounded account lists, effective quota and device records. Plan overrides are bounded to 365 days and 10,000 requests/day and require an operator reason. They do not rewrite subscription state. Device revocation and session revocation apply on the next request. All privileged writes, dataset previews/exports, MFA changes and role bootstrap create audit records. A database trigger rejects audit UPDATE/DELETE; a database owner can still alter schema, so host/database administrator access remains a separate trust boundary. Audit actor foreign keys intentionally prevent silently deleting an account referenced by immutable audit records.

## 3. Teams and tenant isolation

Use **Team workspaces** to create a team, select an active workspace, invite colleagues, inspect members and remove access. The server assigns the creator OWNER. Invitations are email-bound, expire after seven days and store only a SHA-256 token digest. Invitation URLs use a fragment to keep the token out of HTTP request URLs and ordinary reverse-proxy logs. The recipient must sign in with the invited email and accept once. Owners can invite ADMIN or MEMBER; administrators can invite MEMBER only. Owners cannot be removed through the member-removal endpoint.

History and custom presets use the active workspace. `X-Team-ID` is an untrusted selector: the server validates membership on every request. Personal queries require both `team_id IS NULL` and the signed-in user ID; team queries require the validated team ID. Members may save history and edit their own entries. Only OWNER/ADMIN can delete shared history or create/edit/delete shared presets. Team selection is held in browser session storage and cleared on sign-out. The extension currently uses personal workspace assets; bearer tokens cannot select a team.

The custom-preset Pro requirement still applies when billing is enabled. Teams do not introduce pooled billing or shared AI quota; each executing user consumes their own quota. Existing SQL row locks serialize quotas across workers and the ledger is retained across paid upgrades.

## 4. Referrals and coupons

Open **Referrals & rewards** to obtain an account-specific signup link and redeem a coupon.

| Reward | Trigger | Per referral | Cumulative cap |
| --- | --- | ---: | ---: |
| Registration | Successful password signup with referral code and acceptable registration signals | 3 access days | 30 days |
| Paid conversion | Verified, bound, captured Razorpay `subscription.charged` event | 10 access days | 50 days |

Rewards extend promotional Pro access in `bonus_expires_at`; subscription cancellation never erases a granted promotion. Referrals cannot reset daily usage or create an unlimited quota. Reward-balance row locks and database constraints enforce cumulative caps; unique referee IDs and deduplicated payments prevent replay awards. OAuth signup attribution is not implemented in this release: use the email signup referral link.

Fraud signals are HMAC hashes with separate domains for IP, browser-generated device ID and verified payment identity. Shared IP/device/payment values block automatic rewards. Device IDs and IPs are risk signals, not proof of identity: shared networks can produce false positives and a determined attacker can change devices/IPs. Missing registration signals block registration rewards. Paid conversion requires a signed provider card fingerprint or UPI VPA for **both** accounts; generic card IDs are not treated as global fingerprints. Missing values leave conversion blocked for inspection. Never accept a browser-submitted payment fingerprint or grant conversion from a checkout response. The ledger shows blocked reasons; there is no unaudited bypass/reward endpoint.

Coupons use 16 cryptographically random uppercase letters/digits, lock `SELECT ... FOR UPDATE`, enforce global and per-account limits, and reject expired codes. Days-extension coupons grant access directly. Percentage/fixed-amount coupons require an administrator-supplied **real monthly Razorpay plan** whose INR amount matches the discount calculation. Monetary coupons reserve a redemption ID; checkout binds that ID to a durable subscription attempt and only a captured webhook grants paid access. The discounted plan applies to recurring cycles for that subscription, rather than a one-time invoice discount. Keep a timed-out attempt for reconciliation; do not reissue a consumed checkout reservation automatically or double-charge a user.

## 5. Dataset collection, asynchronous processing and privacy

Collection is disabled globally by default (`DATASET_ENABLED=false`) and disabled per user. To enable the capability, configure the persisted dataset encryption key and set `DATASET_ENABLED=true`; users must then opt in in Security & privacy. Only subsequent **personal AI refinements** are eligible. Local compilation and all team-scoped requests are excluded.

The refine handler scrubs structured context, final prompt, provider structured response and token metrics before placing an encrypted payload in a durable PostgreSQL outbox. It does not start a request-bound background thread or call a training provider. A separate CLI worker drains bounded batches with locks and rechecks consent/version. The `model_response` field describes the prompt compiler's structured response, not a conversation scraped from ChatGPT/Claude/Gemini. Regex scrubbing covers common emails, phone-like numbers, provider keys, assignments containing secrets and JWTs; it cannot guarantee removal of all PII or confidential content.

```bash
docker compose --env-file .deploy.env exec -T api flask --app wsgi dataset-worker
docker compose --env-file .deploy.env exec -T api flask --app wsgi cleanup-telemetry
```

Revocation removes that user's queued and stored dataset records transactionally. Retention cleanup removes dataset/operational telemetry older than 30 days; run it daily. Dataset previews and rating/export actions require admin MFA and are audited. NDJSON exports contain OpenAI-style `messages` objects, include only users still consenting, require quality ratings of at least 3 by default, and are bounded to 10,000 records. Review scrubbed content before assigning ratings. Exports are downloads only: this application does not upload files or launch fine-tuning jobs. Revocation cannot retract files already exported or a downstream trained model; control exports through your organization's access and deletion processes.

## 6. Outbound mail hook

Invitations and optional coupon emails create a database outbox entry. Nothing is sent until an operator configures a trusted `MAIL_HOOK_URL=https://...` and the secret file `deploy/secrets/mail_hook_secret`, then runs `flask --app wsgi mail-worker`. This is a signed integration hook, not an SMTP stub.

The hook receives JSON `{id,recipient,subject,body}`, an HMAC-SHA256 `X-PromptLogic-Signature` over the exact bytes and an `Idempotency-Key` equal to the outbox UUID. Verify the signature, persist the idempotency key before sending, and return 2xx only after durable acceptance. Redirects are rejected. Network requests time out, attempts are capped at five, and delivery is at least once, so downstream deduplication is required. No secret/body is written to the application's telemetry. Protect and retain operational outbox data according to your messaging policy.

## 7. Scheduled verified backups

Create private, access-controlled backup storage and install the host cron entries from `deploy/cron.example`. Use a privileged deployment operator with Docker access; do not expose backup/restore through HTTP. Ensure the script path, log paths and cron timezone are appropriate for the host.

```bash
sh deploy/backup-cron.sh
# Inspect the success marker without opening the database dump.
cat backups/last-success
```

Each run takes an exclusive scheduler lock, creates a consistent PostgreSQL custom-format dump to a temporary file, atomically renames it, writes a checksum, restores it into a disposable database with `--single-transaction --exit-on-error`, and checks schema/account tables. It never tests by replacing production. Controlled releases wait for the backup scheduler lock and require a fresh verified rescue backup; normal cron runs skip an overlapping run. Local completed archives older than 30 days are pruned only after verification and successful optional offsite upload. Failures leave the previous success marker unchanged and exit nonzero. Alert when the marker is older than 26 hours; configure your host monitor/log collector to alert on cron failures.

For encrypted offsite storage install `restic`, initialize a repository on a different failure domain and supply `RESTIC_REPOSITORY` and `RESTIC_PASSWORD_FILE` through a root-owned cron environment wrapper. Do not place credentials in the example cron file. When configured, the job includes the dump, checksum, `.deploy.env`, encryption/provider secrets, TLS and release recovery state, checks the repository, and retains 14 daily, eight weekly and 12 monthly snapshots. Keep the restic decryption key independently; no automated process should be able to destroy every backup copy. Configure storage-side immutability/versioning and external access restrictions. With no restic configuration only local backups run: that is insufficient for host loss.

Test remote restoration periodically on an isolated host. Check dump checksum, restore all secrets with their private permissions, restore the matching release and database, then verify user/prompts/billing records before routing traffic. A daily backup has an RPO of up to 24 hours plus scheduler delay; it does not guarantee zero lost writes.

## 8. Secondary PostgreSQL

The optional overlay creates a streaming, read-only PostgreSQL secondary with a separate volume and dedicated least-privilege replication login. Neither database publishes a host port.

```bash
python3 deploy/enterprise-init.py
sh deploy/enable-replication.sh
docker compose --env-file .deploy.env -f docker-compose.yml -f docker-compose.replica.yml exec -T secondary psql -U postgres -d postgres -c 'SELECT pg_is_in_recovery(), pg_last_wal_replay_lsn(), pg_last_xact_replay_timestamp();'
docker compose --env-file .deploy.env exec -T db psql -U postgres -d postgres -c 'SELECT application_name, state, sent_lsn, replay_lsn FROM pg_stat_replication;'
```

The enable script creates/updates the replication role from a generated private secret, allows SCRAM-authenticated replication on the isolated database network, restarts the primary with WAL senders enabled, and takes `pg_basebackup -R -X stream` for an empty secondary. Run in a maintenance window because the primary restart can interrupt sessions. Keep the overlay in subsequent manual Compose commands so the primary WAL settings persist. The enable script records `SECONDARY_ENABLED=true` in `.deploy.env`; controlled releases automatically retain that overlay. Set an alert on replica absence, replay lag and storage capacity. WAL retention is bounded to 512 MB; if the replica is disconnected too long, reinitialize it into a new empty secondary volume from the healthy primary. Do not use an indefinitely retained replication slot without disk monitoring.

This overlay runs on the same host: it protects against certain primary-process/volume failures, **not host or region loss**. For disaster recovery use a secondary on another host/managed service, mutually authenticated TLS and network restrictions. Replication is asynchronous, so a failover may lose unreplicated committed writes. It also copies deletions/corruption; retain backups independently. Application authorization/quota/payment writes always use the primary; this release does not route session checks to a potentially stale replica.

There is no automatic failover. Fence/stop the old primary and application writers, measure last replay state, promote exactly one secondary, change the primary connection/routing, verify recovery, then rebuild the old primary as a replica. Never promote while the old primary can still accept writes. This requires an operator and tested infrastructure-specific fencing; do not claim multi-host HA from the single-host overlay.

## 9. CI and controlled CD

`Application validation` runs PostgreSQL pytest (including quota/coupon/recovery races and tenant/auth boundaries), migration drift and downgrade/upgrade checks, TypeScript, Vitest, real browser insertion and installed-extension tests. `Production container validation` builds actual images and tests HTTPS/cookies/CSRF, backup/restore, recovery checks and the secondary. Store packages are attached as CI artifacts.

Protect `main` with required checks for both workflows and review approvals. Connector credentials cannot configure GitHub administration/secrets; set these in repository settings. Add a protected GitHub environment named `production`, with a deployment branch restricted to main and required reviewers if your organization requires them.

`Validated production release` is a manual promotion workflow. Enter a **full main commit SHA**. It refuses to publish/deploy unless both push CI workflows succeeded for that exact commit, builds API/web images tagged by SHA in GHCR with SBOM/provenance, then uses pinned SSH host keys to run the host release script. Configure:

| Setting | Location | Value |
| --- | --- | --- |
| `DEPLOY_HOST` | production environment variable | DNS name/IP of deployment host |
| `DEPLOY_USER` | production environment variable | Restricted deployment operator |
| `DEPLOY_SSH_KEY` | production environment secret | SSH private key for that operator |
| `DEPLOY_KNOWN_HOSTS` | production environment secret | Host public key verified independently |
| `API_IMAGE` | host `.deploy.env` | `ghcr.io/naveensabapathi/promptengine-api` |
| `WEB_IMAGE` | host `.deploy.env` | `ghcr.io/naveensabapathi/promptengine-web` |

Use `/srv/promptengine` on the host, install Docker Compose/Git/restic as needed, and authenticate host pulls with a narrowly scoped registry credential if images are private. Keep server Git access read-only. SSH keys should be restricted to the deployment entry point and your CI network policy where possible; Docker access is privileged, not a sandbox. The workflow does not transfer production database/provider secrets from GitHub to the server.

`release.sh` serializes deployments, rejects tracked host changes, verifies the commit is on main, runs a verified rescue backup, records previous code/image SHA and backup path, pulls new images before stopping serving processes, runs a forward migration and starts services behind health checks. Migration/startup failure preserves the DB and stops serving processes for operator recovery. It never automatically downgrades schemas or restores an old dump over newer customer writes. The current and previous release records live under private `deploy/state`.

## 10. Recovery runbook

1. Fence writers and stop web/API/workers. Keep the old database volume intact; take a rescue dump if the database still responds.
2. Inspect `deploy/state/pending` or `previous`, CI results and server/container logs. Avoid logs that expose SQL parameters or secret files.
3. If the DB/schema is intact and compatible, restart the last compatible image SHA. Reverting application code does not undo migrations; never assume an old release supports new tenant/MFA state.
4. If data restoration is necessary, select a verified matching archive, validate its checksum and test it on an isolated database first. Identify writes/payments after the backup timestamp and plan reconciliation.
5. Run the explicit destructive restore only during maintenance:

```bash
sh deploy/restore.sh --replace-database /absolute/path/to/verified.dump
```

The script makes a rescue backup, stops web/API, and restores in one transaction. A failed restore does not leave a partly applied database. It leaves services stopped. Do not run scheduled dataset/mail workers concurrently with restoration; disable their cron entries until recovery completes. Rebuild the secondary after a restore so its history matches the recovered primary.

6. Restore the corresponding encryption/session/provider secrets and code release, verify schema, user counts, representative histories, entitlements, MFA, webhooks and quotas; run the documented Razorpay reconciliation workflow for provider/database drift.
7. Bring API/web up with health checks, re-enable workers, rotate/revoke session and extension credentials if compromise caused the incident, and record the recovery timestamp and observed RPO/RTO.

No configuration can promise that nothing will ever break or that every lost state is recoverable. Database integrity constraints, atomic operations, retained release state, verified offsite backups and practiced recovery bound the risk. Infrastructure credentials, DNS/TLS, offsite repository policy, monitoring and production rollout remain operator configuration.

## 11. Browser store packaging

```bash
npm ci
npm run build:extension
npm run test:extension
npm run lint:firefox --workspace @promptengine/extension
cd apps/extension
node scripts/store-archive.mjs
```

Archives: `dist/store/promptlogic-chrome-0.2.0.zip`, `promptlogic-firefox-0.2.0.zip`, and `promptlogic-firefox-mv2-0.2.0.zip`. Submit Chrome MV3 to the Chrome Web Store and Firefox MV3 to AMO; keep MV2 only where Mozilla permits/supports that target. Mozilla signing and review and Chrome store approval happen through your developer accounts, not through this repository. Keep the existing Firefox add-on ID stable for updates. Increment extension version before each later upload.

Production optional host permissions contain only `https://promptlogic.io/*`. The popup defaults both API/web origins to that URL and asks for explicit consent before connecting. Supported chat insertion uses a user-initiated active-tab grant, only inserts plain text, never clicks Send, and falls back to copy. For local development use `EXTENSION_DEVELOPMENT=true npm run build:extension`; those wider-host packages are rejected by the store archive script and must not be submitted.

Before submission publish the operator-approved privacy notice/contact information at a stable public URL, fill out both stores' data-use declarations to match account/authentication and submitted prompt handling (including optional consented training), provide screenshots and reviewer pairing/login instructions, and verify the deployed HTTPS application end to end. Firefox declares authentication information and personal communications because it transmits paired credentials and user-entered tasks. Static React runtime sanitizer warnings in `web-ext lint` require reviewer explanation; there is no extension-origin dynamic script fetching or remotely hosted executable code. No store approval or legal-policy compliance is claimed by a successful build.

## References

- [PostgreSQL backup/standby recovery](https://www.postgresql.org/docs/16/continuous-archiving.html)
- [pg_basebackup](https://www.postgresql.org/docs/16/app-pgbasebackup.html)
- [PyOTP security checklist](https://pyauth.github.io/pyotp/)
- [Chrome Web Store user-data policy](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq)
- [Firefox built-in data consent](https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/)
