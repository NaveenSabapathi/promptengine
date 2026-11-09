# Phase 7: precision refinement

Status: implemented on a review branch; integration and browser gates still pending.
No migrations or production deployment are included.

## API compatibility

`POST /api/compile` and `POST /api/refine` accept `target_model`, `variables`,
`conversation_context`, `selected_text`, and `domain_constraints`.
Supported targets: chatgpt-4o, openai-reasoning, claude-3-7-sonnet,
gemini-2-5-pro, perplexity-search, midjourney-v7, video-gen. These select prompt
formatting guidance; they do not change the configured OpenAI provider model.

Inputs use `{{name}}` or `{{name:default}}`. Explicit nonempty values override
defaults; unresolved variables remain visible. Both interfaces show variable
inputs and interactive clarification controls.

Clients sending a target receive structured clarification questions. Legacy
requests keep string questions. `metrics` remains available alongside the
`token_metrics` alias. New fields include quality_score, raw_quality_score,
score_breakdown, detected_variables and redacted_entities_count.

Precision scores are deterministic structural heuristics (four 0–25 components),
not assessments of correctness or measured model performance. Template formatting
can raise a score without resolving all missing facts.

`POST /api/refine/iterate` accepts the original compile input plus `prior_draft`,
`answers` keyed by question ID, `variables`, and `engine` (`local` default or `ai`).
Local iterations preserve the supplied draft and replace placeholders or append
answers. AI iterations include the draft and answers as task data. A generation
ID alone is insufficient: generation metrics deliberately contain no prompt text.
Existing session/CSRF, extension scope, quota, and database-backed rate limits apply.

## Redaction

System and user messages are redacted immediately before provider transmission.
Built-in patterns cover common API keys, labeled secrets, JWTs, SSNs, card-like
numbers, email and phone numbers. `REDACTION_PATTERNS` is a JSON array of up to 20
administrator-supplied regex strings (maximum 512 characters each). Matches become
`[REDACTED]`; each regex has a 50ms timeout and invalid patterns fail closed.
Pattern matching can have false positives and does not detect every possible secret.
Local-only compiling does not transmit content and does not redact it.

## Verification in this workspace

- Shared-types build and all workspace TypeScript checks: passed.
- Web production build: passed.
- Extension production build / browser packages: passed.
- Web unit tests: 19 passed.
- Extension unit tests: 27 passed.
- Isolated precision compiler/redaction tests: 8 passed.
- Ruff lint and formatting checks: passed.
- Full API suite: blocked by missing dedicated PostgreSQL connection.
- Both Playwright suites: blocked at API startup; no browser assertions completed.
- Attempt to start an isolated packaged PostgreSQL server failed with
  `PermissionError: [Errno 1] Operation not permitted` on socket creation.

Existing GitHub application-validation CI provisions PostgreSQL and runs the
full API and browser suites. These must pass before merging or advancing to
Phase 8. The <1.5s iteration objective has not been verified under deployment
load; external AI latency cannot be guaranteed by this implementation.
