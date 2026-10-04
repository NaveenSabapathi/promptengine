# Phase 5 — Chrome and Firefox WebExtension

## Deliverables and source files

| File | Responsibility |
| --- | --- |
| `apps/extension/popup.html` | Packaged extension page, also usable as a persistent tab editor |
| `apps/extension/src/App.tsx` | Workspace configuration, consent, pairing, local/AI compilation, quota, presets, context fields, output, token change, explicit save/copy/insert, disconnect confirmation |
| `apps/extension/src/main.tsx`, `styles.css` | React startup/error boundary and corporate popup styling |
| `apps/extension/src/platform.ts` | Promise-based WebExtension API and privileged storage access restriction |
| `apps/extension/src/storage.ts` | Settings, opaque token and pending pairing in local extension storage; temporary drafts/results in session storage; strict origin and approval URL validation |
| `apps/extension/src/api.ts` | Scoped bearer authentication, no web cookies, exact endpoint allowlist, no redirects, no automatic retries, timeout/error handling and revoked-token cleanup |
| `apps/extension/src/adapter.ts` | Self-contained on-demand content script function; exact HTTPS host validation, composer selection, native text editing, input events, existing-draft protection |
| `apps/extension/src/insert.ts` | Chrome/Firefox MV3 scripting API and Firefox MV2 serialized-function adapter; clipboard fallback |
| `apps/extension/public/background.js` | Privileged storage initialization only; no credentials, tracking or network access |
| `apps/extension/public/icons/` | Locally generated terminal-mark PNG icons |
| `apps/extension/vite.config.ts`, `tsconfig.json`, `playwright.config.ts` | Build and test configuration |
| `apps/extension/scripts/package.mjs` | Distinct browser manifests; no remote code or embedded provider secrets |
| `apps/extension/src/*.test.ts`, `*.test.tsx` | Popup, API, permission, storage boundary, insertion and clipboard tests |
| `apps/extension/tests/adapters-browser.mjs` | Native Chromium composer fixtures; service pages are intercepted locally |
| `apps/extension/tests/installed.spec.ts` | Installed-extension test for full Chromium against actual Flask/PostgreSQL |
| `apps/api/promptengine/pairing.py` | New authenticated browser-token self-revocation endpoint |
| `apps/api/tests/test_pairing.py` | Token self-revocation, web-session isolation and revoked-token rejection |

## Build and installation

Use the root npm lockfile and Node.js 22.12+ or Node.js 24. The API remains Flask/PostgreSQL from earlier phases.

```bash
npm ci
npm run build:extension
```

Output:

- `apps/extension/dist/chrome`: Chrome Manifest V3, minimum Chrome 114.
- `apps/extension/dist/firefox`: Firefox Manifest V3.
- `apps/extension/dist/firefox-mv2`: Firefox Manifest V2 alternative. Both Firefox packages require desktop Firefox 140+ and declare Firefox Android 142+ for built-in data consent compatibility. Android operation has not been verified.

For Chrome, open `chrome://extensions`, enable Developer mode, select **Load unpacked**, and choose `dist/chrome`. Pin PromptEngine so opening its toolbar popup grants temporary active-tab access. Do not try to install the Firefox package in Chrome.

For Firefox development, open `about:debugging#/runtime/this-firefox`, select **Load Temporary Add-on**, and choose the Firefox package's `manifest.json`. Temporary installation lasts until Firefox restarts. Normal Firefox distribution requires Mozilla signing; these source/review packages are unsigned.

Archives contain `manifest.json` at the root. Unzip before loading unpacked. Store submission is not performed by this phase.

## Server configuration and pairing

The extension does not assume a domain you have not deployed. Enter your actual HTTPS API server origin and web app origin, and a browser name. Origins must not contain a path, query, credentials or fragment. HTTP is allowed only for `localhost` or `127.0.0.1` development.

Local example:

- API server: `http://localhost:5000`
- Web app: `http://localhost:5173`

Review the data notice and click **Connect workspace**. A browser permission prompt requests access only to the chosen API hostname. Browser match patterns cover all ports on a host; API requests still use the exact configured origin. Changing either API or web origin clears authentication, pending pairing, and session drafts before a new connection is used. An old host grant is removed when the hostname changes.

1. Click **Create pairing code**. The pending code and device secret are saved before opening another tab.
2. Open the approval page, sign in on the web app using email, Google or Microsoft, and review/approve the code.
3. Reopen the extension and click **I approved this browser**. There is no automatic polling or unsolicited account approval.
4. The API exchanges the one-time code/device secret for a scoped `pe_ext_` token. No web JWT or account password is copied into the extension.

Codes expire after five minutes. Expired or consumed codes require a new pairing attempt. If the extension closes during an exchange and its response is lost, a token can appear in web device settings without being saved locally; revoke that orphaned device and pair again.

## Authentication, storage and privacy

The opaque scoped access token is stored in `chrome.storage.local` / `browser.storage.local`, with its server expiry, token ID and scopes. It is revocable in web Settings or via confirmed extension disconnect. `/api/extension/disconnect` accepts only an extension token and revokes exactly that token; it does not log out the user's web account. If disconnect cannot reach the server, local access is cleared and the UI explains that web Settings must revoke server access.

Chrome local storage access is restricted to trusted extension contexts before credentials are read/written when the API is available. No token or pairing secret is passed to content scripts, placed in tab URLs, embedded in source, or stored in browser sync storage. The injected function receives only prompt text and an explicit draft-replacement decision. It has no storage, network, messaging, or Send operation.

Drafts and generated results use extension `storage.session`, scoped to the token ID. They survive popup closure but are temporary and clear on disconnect or browser restart. They are not automatically saved to the server's prompt library. Settings and pending pairing data are local, persistent extension state.

Every request uses `credentials: omit`, a scoped Authorization header where needed, and `redirect: error`. Pairing creation/exchange and public capability/catalog calls never include an existing bearer token. Revoked/expired tokens return the extension to pairing. An older failed request cannot clear a newly paired token.

Prompts submitted for **local compilation** go to your configured Flask server, which does deterministic compiling without a model request. **AI refinement** additionally sends task content to the backend's configured OpenAI provider. Saved prompts are account-private. The backend logs content-free generation metrics and quota counts. The extension does not send chat history, URLs of visited chats, existing chat drafts or browsing history to the backend, and has no tracking/analytics SDK.

Firefox manifests declare required authentication and personal-communication transmission and the minimum versions needed for Mozilla's built-in consent. This is not a claim of zero data transmission. A final store privacy policy and owner review of store declarations are required before publication.

## Editor and insertion behavior

The popup mirrors the web compiler: six presets plus entitled custom presets, tone, Build/Compact mode, preset fields, local or AI generation, quota display, clarification questions, assumptions, token counts and explicit save/copy. Counts use the backend's GPT-4o-mini text tokenizer and show added tokens honestly. They are not exact billable Claude/Gemini tokens.

Keep the popup open while generating. For longer work, use **Open editor in a tab**; it retains the original target tab ID. Temporary drafts/results let you reopen the popup after generation. Changing the browser's active tab does not silently redirect an already-open editor to a different conversation.

Supported HTTPS hosts: `chatgpt.com`, legacy `chat.openai.com`, `claude.ai`, and `gemini.google.com`. Hostnames are matched exactly, then checked again inside the injected function. There are no always-on content scripts or persistent chat host grants in production manifests.

The adapter detects service-specific textarea/contenteditable composers, excludes hidden/disabled/inert editors, and refuses ambiguous matches. Existing non-empty drafts require **Replace draft** confirmation; **Keep draft & copy** preserves them. Textareas use the native prototype value setter and input/change events to support React-controlled input. Contenteditable editors use native `insertText` editing so ProseMirror/Quill can observe an editing operation. Prompt content is plain text; no prompt HTML is parsed.

The extension never dispatches Enter, submits a form, clicks Send, or executes the prompt. If native editing is unavailable, the composer changes, active-tab access is denied, or the page is unsupported, the UI copies the prompt and explains why. Clipboard failure leaves a selectable output for manual copying.

Chat vendor DOM structures are not stable public APIs. Adapter fixtures verify native editing and event behavior; signed-in live vendor UI checks are still required before a store release. No live vendor account was probed or signed into during this build.

## Verification and CI

```bash
npm run typecheck
npm run build:extension
npm run test:extension
npm run lint:firefox --workspace @promptengine/extension
npx playwright install --with-deps chromium
npm run test:browser --workspace @promptengine/extension
```

Local validation passed: 90 PostgreSQL API tests, 25 extension tests, 12 existing web tests, five native Chromium adapter fixtures, TypeScript checking and all three extension builds. The installed Chrome workflow is included in CI but could not be executed locally because the available headless-shell runtime does not support extensions.

The PostgreSQL API suite now covers browser-token self-revocation. The native browser fixture test uses actual Chromium editing APIs at intercepted service-shaped DOM pages, and never contacts a live assistant. Firefox package lint reports zero errors; its two `UNSAFE_VAR_ASSIGNMENT` warnings are in React's bundled implementation. Prompt content is rendered through controlled textareas/native text operations; first-party insertion code never writes `innerHTML`. These library warnings are documented, not hidden.

Installed-extension test:

```bash
# Use an isolated PostgreSQL database, a .venv, and the browser-test environment
# from docs/phase-4.md. The database name must contain test.
npm run test:installed --workspace @promptengine/extension
```

It starts real Flask and Vite servers, loads an unpacked Chrome extension in full Chromium, pairs through the actual web UI, verifies scoped requests and local/session storage, inserts through `chrome.scripting`, and revokes the token. A temporary test copy pregrants only localhost and intercepted ChatGPT fixture hosts because browser automation cannot accept native optional-host prompts or click a toolbar action. Production manifests are never modified by this test. Installed-extension testing requires full Chromium; a headless-shell binary without extension support cannot run it. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` can select another installed browser.

CI includes the extension unit tests, build, Firefox lint, native Chromium fixtures and installed Chrome workflow. Runtime Firefox installation and live signed-in chat checks remain manual release checks. Phase 6 supplies production Docker/Gunicorn/Nginx packaging.

## Browser references

- [Chrome activeTab permissions](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab)
- [Firefox built-in data consent](https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/)
- [Playwright installed extension testing](https://playwright.dev/docs/chrome-extensions)
