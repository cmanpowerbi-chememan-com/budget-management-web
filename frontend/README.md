# Frontend (React + Next.js, static export) — A7 scaffold

This is the **app shell only** (BUILD_PLAN.md A7): Entra Easy Auth wiring, RLS scope
fetch, and the ADR-0016 email deep-link parser, rendered as a placeholder shell. No
grid, subforms, or approve UI yet — those are A8-A10.

## Local dev (2 terminals)

```bash
# Terminal 1 — backend (see backend/README.md)
cd backend
uvicorn app.main:app --reload

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:3000`. The Next dev server proxies `/health`, `/me`, `/scope`,
`/budget`, `/approval` to `http://127.0.0.1:8000` (see `next.config.ts`'s `rewrites()`)
— no CORS setup needed locally. In production, set `NEXT_PUBLIC_API_BASE` if the API is
served from a different origin than the SPA; it defaults to same-origin (empty string).

To exercise the deep-link (ADR-0016), open e.g.:
`http://127.0.0.1:3000/?dept=ฝ่ายบัญชี&year=2026`

## Why no `/api` prefix in the proxy

`backend/app/main.py` mounts routers directly (`/health`, `/me`, `/scope`, `/budget`,
`/approval/*`) with no shared prefix, so the dev proxy forwards each known route
namespace as-is. Adding an `/api/*` prefix would need path-rewriting for no benefit.

## Why no router / state library

Phase-1 is a single page (ADR-0016: approval happens inline on the main page, no
separate inbox screen) — `react-router` would add a dependency with nothing to route
between, and the App Router's own file-based routing stays at one route
(`app/page.tsx`) for the same reason. Deep-link params are read once on load via
`platform/location.ts`'s guarded `currentSearch()`. No Redux/Zustand/react-query
either — two hooks (`useAuth`, `useScope`) covering two GET calls don't need a state
library; revisit only if A8+ needs shared mutable state across many components.

## Structure

```
src/
├── app/
│   ├── layout.tsx      root layout — global CSS imports, fonts, pre-paint theme script
│   └── page.tsx        the one client-only boundary (dynamic(..., { ssr: false }))
├── api/
│   ├── client.ts      typed fetch wrapper — 401 → Easy Auth login redirect,
│   │                  403/5xx/network → mapped ApiError
│   └── types.ts       response shapes for /me, /scope
├── auth/
│   ├── useAuth.ts      GET /me → { email, loading, error }
│   └── useScope.ts     GET /scope → RLS Fill/See scope + role (ADR-0019)
├── filters/
│   └── deepLink.ts     parses ?dept=&year= (ADR-0016), convenience-only
├── platform/
│   ├── env.ts               the one build-env read (NEXT_PUBLIC_API_BASE)
│   ├── location.ts          guarded window.location reads/navigation
│   └── usePersistedToggle.ts shared persisted-state hook (theme + admin-view toggles)
├── styles/
│   ├── tokens.css       design tokens ported from the canonical mockup
│   │                    (design/mockups/0002claude design/0002.3budget-export.html)
│   └── global.css       base reset + shell chrome (nav/user-bar/filter-chip)
├── test/setup.ts        jest-dom matchers + RTL cleanup wiring
└── App.tsx              the shell: nav, user bar, deep-link chip, grid placeholder
```

## Tests

```bash
npm test
```

Vitest + React Testing Library, jsdom environment. Covers: the deep-link parser
(valid/invalid/missing/URL-encoded Thai), `useAuth`'s 401→redirect behavior, the API
client's error mapping (401/403/5xx/network), and the shell rendering with/without a
deep-link filter.

## Build

```bash
npm run build
```

`next build` (typecheck is built in) with `output: 'export'` → static site in `out/`.
