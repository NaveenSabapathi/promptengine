# PromptEngine WebExtension

TypeScript + React + Tailwind, packaged with Vite for Chrome MV3, Firefox MV3, and Firefox MV2. See [Phase 5 guide](../../docs/phase-5.md) for installation, pairing, permissions, tests, and release limitations.

From the repository root:

```bash
npm ci
npm run build:extension
npm run test:extension
npm run lint:firefox --workspace @promptengine/extension
```

Unpacked directories: `apps/extension/dist/chrome`, `dist/firefox`, `dist/firefox-mv2`. Configure your HTTPS PromptEngine API and web origins in the extension; localhost HTTP is allowed for development. No deployment origin or provider key is embedded in the package.

The popup uses a scoped, revocable browser token instead of web cookies. Insertion uses the active tab only on explicit action, detects supported hosts again inside the tab, protects existing drafts, and never clicks Send. If a composer cannot safely accept native plain text, copy fallback remains available.
