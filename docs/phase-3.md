# Phase 3: subscriptions, webhooks and custom presets

## Delivered files

| Path | Responsibility |
| --- | --- |
| `apps/api/promptengine/razorpay_provider.py` | Real Razorpay SDK, request timeouts, plan validation and trusted checkout links |
| `apps/api/promptengine/billing.py` | Plan catalog, subscription checkout/status/cancellation and reconciliation CLI |
| `apps/api/promptengine/webhooks.py` | Raw-body signature verification, transactional event/payment deduplication and ordered entitlement changes |
| `apps/api/promptengine/custom_presets.py` | Account-private custom preset CRUD, access control and schema validation |
| `apps/api/promptengine/presets.py` | Resolve owned custom contracts in the existing compiler |
| `apps/api/promptengine/models.py` | Billing attempt, webhook receipt, payment deduplication and custom preset tables |
| `apps/api/migrations/versions/e02df4a6f04c_phase_3_billing_subscriptions_webhooks_.py` | Phase 3 upgrade/downgrade, including wider preset IDs in metrics |
| `apps/api/tests/test_billing.py` | Real SDK over controlled HTTP; actual HMAC and PostgreSQL lifecycle/concurrency tests |
| `apps/api/tests/test_custom_presets.py` | Beta/Pro access, expiry, account isolation and compiling tests |
| `packages/shared-types/src/index.ts` | Billing/custom preset TypeScript contracts |

## Launch and pricing policy

`BILLING_ENABLED=false` is the default. Paid checkout is disabled until the operator
configures and enables it. The beta uses Free accounts with 10 daily AI requests, local
compiling, and custom presets. Local compiling has no AI quota charge but retains its
endpoint rate limit. Turning billing on restricts custom presets to effective Pro accounts;
downgraded users can still delete their stored custom presets.

| Tier | AI quota | Local compiling | Custom presets | Monthly price |
| --- | --- | --- | --- | --- |
| Free | 10 per UTC day | Included | Included in beta; unavailable in paid mode | ₹0 |
| Pro | Configurable; default 100 per UTC day | Included | Up to 50 owned presets | Draft ₹499, configurable |

Pro uses a finite high limit, not an unlimited promise. `PRO_DAILY_AI_LIMIT` must be
11–10,000. `PRO_PRICE_PAISE` is a configurable INR minor-unit amount, default `49900`.
The draft price is a product configuration, not an approved launch price or profitability
claim. Review usage cost before enabling it. No actual payment or subscription has been
created by implementation tests.

The backend fetches the configured Razorpay plan before checkout and requires its item
amount, currency, monthly period and interval to match the configuration. The client
cannot choose price, plan ID, quantity or a different tier. Initial implementation uses
INR monthly billing; international recurring acceptance depends on the merchant's actual
Razorpay account and enabled payment methods, and is not guaranteed by this code.

## API contract

All billing account routes are **web-session only**. Extension tokens cannot purchase,
inspect billing or cancel. Mutating web routes require CSRF and matching Origin.

| Method/path | Request and behavior |
| --- | --- |
| `GET /api/billing/plans` | Public tier catalog and `billing_enabled` flag |
| `GET /api/billing/status` | Own effective tier/quota and latest local subscription metadata |
| `POST /api/billing/subscribe` | Exactly `{ "plan_tier": "pro" }`; returns `{ subscription }` and 201 for a new checkout, 200 for a reused pending link |
| `POST /api/billing/cancel` | `{ "at_cycle_end": true }` by default; use false for immediate cancellation |
| `POST /api/webhooks/razorpay` | Public provider endpoint requiring valid `X-Razorpay-Signature`; no session/CSRF required |
| `GET /api/custom-presets` | Web or extension `refine` scope; own accessible custom presets |
| `POST /api/custom-presets` | Create a validated contract; returns `{ preset }`, 201 |
| `PUT /api/custom-presets/{uuid}` | Replace own contract; returns `{ preset }` |
| `DELETE /api/custom-presets/{uuid}` | Delete own contract, including after downgrade; 204 |

Subscribe responds with a local attempt UUID, provider subscription ID, status, checkout
URL, paid-cycle end, cancellation flag, configured amount and currency. The checkout link
is a verified HTTPS `rzp.io` URL. Creating or authorizing checkout alone **never grants Pro**.

Checkout reuses created/authenticated subscriptions and rejects a second active/pending/
halted/uncertain attempt with 409. A PostgreSQL partial unique index and entitlement lock
prevent concurrent attempts from creating duplicate provider subscriptions. The durable
attempt is committed before the external request; no database transaction remains open
during subscription creation. SDK retries are disabled and requests have 5-second connect
and 15-second read timeouts.

The provider automatically associates a customer on authorization. The server saves the
customer ID from the verified charge event; it does not invent a customer ID or pass an
unsupported create parameter. Customer notification is disabled in creation; the app
returns the hosted link rather than sending email/SMS.

A timeout can leave a provider subscription created despite no response. The attempt is
marked `uncertain`, and further checkout creation is blocked until reconciliation. Do not
interpret an HTTP failure as proof that the provider did not create a subscription.

Cancellation remains available if new sales are disabled, provided provider credentials
remain configured. Scheduled cycle-end cancellation retains paid access until the
cancelled webhook or entitlement expiry. Immediate provider-confirmed cancellation
reduces access to Free. Cancelling does not automatically issue a refund.

## Webhook security and lifecycle

Set a separate `RAZORPAY_WEBHOOK_SECRET`. The API uses the actual Razorpay SDK's HMAC-SHA256
verifier on the untouched UTF-8 request body **before JSON parsing**. Missing/bad signatures
return 401. It does not trust a checkout redirect, client payment callback, notes containing
an arbitrary user ID, or an unsigned event header to grant access.

Supported events:

- `subscription.charged`: requires a known/matched checkout, its plan ID, an active provider
  subscription, a captured payment in the expected currency for at least the plan amount,
  and an unexpired `current_end`. Upgrade to Pro, apply its quota, and set paid expiry from
  that billing cycle. Actual daily usage is retained rather than erased.
- `subscription.cancelled` and `subscription.halted`: downgrade to Free immediately.
- `subscription.completed` and `subscription.expired`: also downgrade safely.

A signed unsupported event is acknowledged as ignored. A signed unknown subscription
returns 503 without committing a receipt so a retry can resolve an early-delivery race.
Recovery can bind only a durable local checkout UUID from provider notes and the matching
plan ID. It never binds by client-supplied email or an arbitrary user ID.

Receipts have unique event IDs and unique payload digests. The original payload is not
stored. Payment IDs are also unique. A repeated delivery or changed unsigned event ID
cannot reapply a charge. A reused event ID with a different signed body returns 409.
The receipt, payment entry, subscription state and entitlement changes commit together;
errors roll everything back, allowing a later delivery to retry.

Each subscription tracks the latest event timestamp. Older events are acknowledged as
stale. Downgrades win over charges at the same timestamp. Cancelled/completed/expired
subscriptions cannot be resurrected by later charged deliveries; halted subscriptions
can recover through a newer, distinct captured charge. Events for an old subscription
cannot downgrade or upgrade a newer subscription on the account.

Ordering behavior is intentionally conservative. Same-second ambiguities may keep an
account at Free until a verified newer event is received or an operator reconciles it.
There is no automated dunning, invoice creation, refund workflow or grace period in this phase.

## Custom presets

A custom contract uses:

```json
{
  "name": "Support Reply",
  "role": "Customer support manager",
  "required_fields": {"objective": "What should the reply achieve?", "recipient": "Who receives it?"},
  "optional_fields": {"context": "Relevant ticket details"},
  "output_constraints": ["Write a concise, polite reply without invented commitments."]
}
```

Require `objective`, up to six required and six optional field definitions with distinct
keys, and 1–6 output constraints. Names and roles have bounded lengths; keys use lowercase
letters, digits and underscores. Up to 50 presets per account are allowed, with concurrent
creation serialized to enforce the cap. Access is checked for effective, unexpired Pro
when paid mode is enabled. Other users receive 404 for inaccessible objects.

Responses use IDs of the form `custom_<uuid>`. Send that ID as `preset` to existing
`/api/compile` or `/api/refine`; field validation and missing-field checks use the owned
contract. CRUD paths use the plain UUID. Custom definitions are stored explicitly as user
settings. Generation metrics still contain no actual task/prompt content. The recorded
preset version is the compiler schema version; custom definition snapshots are not archived.

## Setup

1. Install `apps/api/requirements.lock.txt` and run `flask --app wsgi db upgrade`.
2. Keep `BILLING_ENABLED=false` for the free launch.
3. In Razorpay test mode, enable Subscriptions and create a monthly, interval-one INR plan
   matching `PRO_PRICE_PAISE`. Set its ID in `RAZORPAY_PRO_PLAN_ID`.
4. Set test-mode `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` and a separate webhook secret.
5. Configure the HTTPS webhook URL `https://YOUR_DOMAIN/api/webhooks/razorpay` for the five
   handled events. Match the secret exactly; do not substitute the API key secret.
6. Enable billing only in the intended environment, then validate a test payment, webhook,
   renewal, cancellation, duplicate delivery and access expiry. Never reuse test plan IDs
   with live keys. The default cycle count is 120 months; configure as needed.

Live merchant onboarding, recurring/international payment eligibility, tax treatment and
final pricing need operator confirmation before public paid launch. These have not been
validated by fixture tests, and no real merchant credentials are included.

Useful configuration:

```dotenv
BILLING_ENABLED=false
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_PRO_PLAN_ID=
RAZORPAY_WEBHOOK_SECRET=
PRO_PRICE_PAISE=49900
PRO_DAILY_AI_LIMIT=100
RAZORPAY_TOTAL_COUNT=120
```

## Recover an uncertain checkout

Look up the provider subscription in Razorpay by the durable checkout note, then run:

```bash
cd apps/api
flask --app wsgi reconcile-checkout CHECKOUT_UUID sub_PROVIDER_ID
```

The command fetches the real provider subscription and checks its ID, plan and exact local
checkout note. It only resolves `creating`/`uncertain` attempts, and never grants Pro by
itself. Replay the verified `subscription.charged` event from Razorpay for paid access.
For a provider-created subscription with no completed payment, the recovered hosted link
can be reused. If no subscription exists, do not blindly attach a random ID or clear the
attempt: investigate the provider's logs before resetting it administratively.

## Validation and boundaries

Tests exercise actual SDK serialization over controlled HTTP and actual HMAC verification,
plus PostgreSQL locking/constraints. They cover plan price mismatch, checkout reuse and
concurrency, creation timeout/reconciliation, duplicate/stale/superseded events, captured
payment checks, downgrade/recovery, cancellation, scope isolation, custom preset ownership
and expiry. Fixture tests do not prove real recurring payment mandates or merchant setup.

Downgrading removes the Phase 3 billing/custom tables. Numeric generation history is
retained, with long custom-preset IDs relabeled `custom_archived` before narrowing the
Phase 2 column. Back up before a production downgrade; this is a destructive schema rollback.

UI checkout, pricing presentation and account settings are implemented in Phase 4.
Chrome/Firefox extension packaging is Phase 5, and production deployment remains Phase 6.

Primary integration references:

- [Razorpay create subscription](https://razorpay.com/docs/api/payments/subscriptions/create-subscription/)
- [Razorpay webhook validation](https://razorpay.com/docs/webhooks/validate-test/)
- [Razorpay webhook best practices](https://razorpay.com/docs/webhooks/best-practices/)
