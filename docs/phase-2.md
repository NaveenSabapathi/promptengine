# Phase 2: prompt compiler and generation metrics

## Delivered files

| Path | Responsibility |
| --- | --- |
| `apps/api/promptengine/presets.py` | Six versioned preset contracts, required/optional fields and output constraints |
| `apps/api/promptengine/compiler.py` | Strict input validation, trusted compiler instructions, deterministic local compiler and exact text token counts |
| `apps/api/promptengine/ai_provider.py` | Real OpenAI SDK request, strict JSON Schema, output validation and error translation |
| `apps/api/promptengine/generation.py` | Preset catalog, AI/local endpoints, quota integration and metrics summaries |
| `apps/api/promptengine/models.py` | Content-free generation measurements with account foreign key and indexes |
| `apps/api/migrations/versions/b65352810b54_phase_2_content_free_generation_metrics.py` | Generation metrics upgrade/downgrade |
| `apps/api/tests/test_generation.py` | Real SDK over fixture HTTP, PostgreSQL persistence, scope/quota/error/privacy tests |
| `packages/shared-types/src/index.ts` | Typed preset, compiler and metrics contracts |

Phase 1 auth, extension scopes and saved prompt APIs remain available. No AI output is
saved automatically as a prompt. The user explicitly saves it with `/api/prompts`.

## Preset contract

`GET /api/presets` returns the six presets, schema version, allowed tones and modes.
Required fields describe information needed for a complete prompt, rather than a reason
to reject incomplete tasks. Each missing field can produce a placeholder and question.

| Preset ID | Required information |
| --- | --- |
| `coding` | objective, stack, deliverable |
| `website_briefs` | objective, audience, pages |
| `business_proposals` | objective, audience, scope |
| `marketing` | objective, audience, channel |
| `research` | objective, scope, timeframe |
| `professional_comm` | objective, recipient, channel |

The catalog also exposes optional fields and preset-specific output constraints.
Allowed tones: `professional`, `concise`, `friendly`, `technical`, `persuasive`.
Modes are case-sensitive: `Build`, `Compact`.

## Endpoints

| Method/path | Access | Behavior |
| --- | --- | --- |
| `GET /api/presets` | Public | Versioned preset catalog |
| `POST /api/refine` | Web cookie + CSRF or extension `refine` scope | AI-powered compiler; reserves one daily AI request |
| `POST /api/compile` | Web cookie + CSRF or extension `refine` scope | Deterministic server template; no AI call or AI quota consumption |
| `GET /api/generation-metrics?days=30` | Web cookie or extension `usage:read` | Account-isolated summaries by engine over a rolling 1–365 day period |

Both POST endpoints accept the same body:

```json
{
  "raw_input": "Build a service management portal for a computer repair shop.",
  "preset": "coding",
  "tone": "technical",
  "mode": "Build",
  "fields": {
    "stack": "Flask, PostgreSQL and React",
    "deliverable": "Runnable code with exact file paths",
    "constraints": "Admin and staff roles; secure authentication"
  }
}
```

`raw_input` and `preset` are required. Tone defaults to `professional`; mode to `Build`;
fields to `{}`. Unknown properties and fields are rejected. Raw text is preserved exactly
for token measurement; it must contain non-whitespace text and no NUL, with a 20,000-character
limit. Field values are strings of 1–4,000 characters, with a combined 20,000-character limit.
The total task/field budget is 12,000 tokens. The Phase 1 body limit of 64 KiB also applies.

A success returns:

```json
{
  "prompt": "The compiled prompt ready to copy...",
  "missing_fields": [],
  "clarification_questions": [],
  "assumptions": [],
  "generation_id": "UUID",
  "engine": "ai",
  "metrics": {
    "raw_tokens": 120,
    "generated_tokens": 90,
    "token_difference": 30,
    "reduction_percent": 25,
    "is_reduction": true,
    "tokenizer": "o200k_base",
    "tokenizer_model": "gpt-4o-mini",
    "scope": "plain_text_only",
    "preset_version": "2026-10-04.1"
  },
  "provider_usage": {
    "input_tokens": 700,
    "output_tokens": 130,
    "model": "gpt-4o-mini-2024-07-18"
  },
  "quota_reservation": {"date": "2026-10-04", "used": 1, "limit": 10}
}
```

Numbers above illustrate the contract; they are not claimed measurements. Local compilation
has `engine: "local"`, null provider usage values and null quota reservation. The reservation
snapshot reports usage when the slot was admitted; `/api/usage` returns current daily usage.

## Compiler behavior

Build covers role, task, context, constraints, deliverables and acceptance criteria.
Compact asks the model to reduce redundancy while preserving material instructions;
it does not promise a smaller result. The deterministic compiler preserves raw task/code
whitespace and has no semantic inference. It uses the raw task as the objective and lists
other required structured fields as missing when they are not supplied.

The AI compiler can infer fields from an unambiguous raw task. It receives user data as a
separate JSON user message, while the system message contains trusted preset/tone/mode
instructions. Instructions ask it to compile rather than execute the task, preserve supplied
facts, avoid invented evidence or commitments, and expose unknowns. JSON isolation and
instructions reduce prompt injection risk but do not prove semantic correctness; users
must review the output before executing it in another assistant.

The real SDK uses Chat Completions with `response_format.type = json_schema`, `strict: true`,
all four required properties and `additionalProperties: false`. The API validates the result
again: nonempty prompt, known missing-field keys, no duplicate missing fields, and bounded
question/assumption arrays. A fenced whole response is rejected. The default is the requested
`gpt-4o-mini`; the approved dated snapshot is also configurable. There is no silent model switch.

Reference: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Token accounting and privacy

Raw and generated text are tokenized with the configured GPT-4o-mini vocabulary using
`tiktoken`. These are exact token counts **for those strings and that vocabulary**. They do
not measure Claude/Gemini tokenization or include the target chat's system messages, history,
attachments or output. Optional structured fields are not added to the raw-text baseline.

`token_difference = raw_tokens - generated_tokens`. A negative value is an increase.
`reduction_percent` is signed, and `is_reduction` is true only for a positive difference.
Do not display a negative difference as positive savings. This compares text size, not
meaning-equivalent quality, money saved, or future follow-up requests avoided.

OpenAI's returned usage is recorded separately: it includes the compiler request and the
structured JSON response, so it differs from the plain-text metrics. Refinement itself has
an API cost; do not equate plain-text reduction with net financial savings. Summary totals
cover successful generations only; failed provider attempts may still incur provider costs.

`generation_metrics` stores account ID, preset/version, engine, mode, allowed tone,
model/tokenizer, numeric token counts and latency. It contains **no raw task, generated prompt,
field values, questions or assumptions**. It does not store hashes of prompt content either.
The database computes the signed difference, preventing inconsistent saved measurements.
Responses contain prompt content for the user's workspace; explicit saved-prompt storage is separate.

The API sends raw input and fields to OpenAI only on `/api/refine`. `store=false` disables
optional completion storage; it does not promise zero provider retention. Do not enable
request-body debug logging in production. Keys remain server-side.

## Quotas and errors

Input validation, token-budget checks and missing-key detection happen before reserving
quota. The existing atomic PostgreSQL entitlement check admits at most the daily limit.
Database locks are released before network execution. Success consumes one slot; timeouts,
provider errors, refusals, invalid output and persistence failures refund it. A process kill
can conservatively consume a slot, as documented in Phase 1. No automatic provider retries
are made. Endpoint rate limits are separate from AI quotas: 20 AI or 30 local attempts/minute/user.

| Condition | Status/code |
| --- | --- |
| Invalid input/preset/fields | 400 |
| Task token budget exceeded | 413 `input_too_large` |
| Missing credentials/session | 401; invalid scope → 403 |
| Daily quota or endpoint rate limit reached | 429 |
| Provider refusal/content filter | 422 `ai_refused` |
| Invalid or truncated provider output | 502 |
| Provider timeout | 503 `ai_timeout` |
| Missing API key | 503 `ai_not_configured` |
| Provider/network/rate limit/configuration error | 503 |
| Database unavailable | 503 |

## Setup and verification

Install the updated lock file, set `OPENAI_API_KEY` for AI refinement, and run the second migration:

```bash
pip install -r apps/api/requirements.lock.txt
# Load .env as described in README, then:
cd apps/api
flask --app wsgi db upgrade
flask --app wsgi warm-tokenizer
```

`OPENAI_MODEL` defaults to `gpt-4o-mini`. `OPENAI_TIMEOUT_SECONDS` defaults to 20 and accepts
1–25 seconds. `warm-tokenizer` caches the public model vocabulary before serving requests;
the first load may download vocabulary, but sends no user data and calls no AI model.
For offline operation preserve this cache using `TIKTOKEN_CACHE_DIR`. Phase 6 should warm
it during the container build. Local compilation needs no OpenAI key.

Tests run the real OpenAI SDK with a controlled HTTP transport; they verify the serialized
request contract and simulate external errors without mocking PostgreSQL, quota logic,
compiler implementation or tokenization. They cover all six presets/modes, Unicode/special
text, negative token differences, privacy, scopes, quota exhaustion, failure refunds and
account isolation. They do not prove live model quality or real API-key/model access.
A paid live smoke test remains necessary once an API key is configured.

Phase 3 (Razorpay subscriptions and webhooks) is the next approval gate.
