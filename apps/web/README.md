# PromptEngine web application

React + TypeScript + Vite, Tailwind CSS v4, and locally owned shadcn/ui-style primitives backed by Radix Slot and CVA. See [Phase 4 setup](../../docs/phase-4.md).

From the repository root:

```bash
npm ci
npm run dev
npm run build
npm run typecheck
npm run test:web
```

The development server proxies `/api` to Flask at `http://127.0.0.1:5000`. Set `API_PROXY_TARGET` for another local backend. Configure Flask `WEB_ORIGIN=http://localhost:5173` and `API_ORIGIN=http://localhost:5000`. There are no client-side secrets or authentication tokens in browser storage.

Production output: `apps/web/dist`. Serve the SPA and `/api` on the same HTTPS origin, with a fallback to `index.html` for frontend routes. Production Docker/Nginx packaging is Phase 6.
