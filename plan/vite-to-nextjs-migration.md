# Migration Guide — Frontend: Vite → Next.js (Static Export)

**Status:** plan written, **NOT yet executed** — awaiting go-ahead.
**Driver:** org standard on Next.js (confirmed 2026-07-23).
**Scope:** framework/tooling swap only — behavior, tests, deploy model unchanged.
Perf layer (TanStack Query, code splitting) is a **separate follow-up task** — it works
identically on Vite and Next and is deliberately NOT bundled into this migration.

> **Architecture review blended in (2026-07-23).** A read-only deletion-test review of all
> ~66 source files ran alongside this plan (6 dimensions, each finding adversarially
> re-verified against the code). **Headline: keep this migration a pure framework swap.**
> 21 real "deepening" opportunities were found, but the verify pass confirmed **almost all
> touch files the migration never opens** — folding them in would break the tiny-commit
> discipline of §5 and inflate migration risk for no reason. Only **3 genuinely intersect**
> the migration (they touch `App.tsx`/the shell, which are rewritten anyway) — those are
> folded in below and tagged `[ARCH]`. Everything else is a **separate post-migration PR**,
> ranked in the new **§8 Architecture backlog**. The review also **sharpened gotcha G1**
> (see §4) and surfaced **two real bugs** unrelated to Next (§8.C).

---

## 1. Decision summary

| Question | Decision |
|---|---|
| Migrate? | Yes — org standard. App is still small (66 files, no router) → cheapest moment to move. |
| Next.js flavor | **`output: 'export'`** (static export) — no Node server, no SSR/RSC. |
| Why not SSR/Node | Internal app behind Entra Easy Auth; every byte of data needs the user session; backend is FastAPI. SSR buys nothing, adds a Node container + auth-header forwarding. |
| Router structure | Keep single-screen SPA (`app/page.tsx` only). No fake multi-route until a second screen exists. |
| Rendering | Whole app client-only via one `dynamic(..., { ssr: false })` wrapper — see §4 gotcha G1. |
| Test/lint stack | Unchanged: vitest + jsdom, oxlint, Playwright. They are framework-agnostic. |
| Deploy | Unchanged shape: static files built in Docker stage 1 → FastAPI `StaticFiles` (`STATIC_DIR`) in the same Container App. Only the build output dir changes: `dist/` → `out/`. |

## 2. Current state (verified by reading the code, 2026-07-23)

- `frontend/` = React 19.2 + Vite 8 + TS ~6.0, 66 source files in feature folders
  (`grid/ approval/ attachments/ auth/ api/ picker/ subform/ userbar/ admin/ filters/ styles/`),
  co-located `*.test.ts(x)`, `e2e/` (4 Playwright specs — backend fully mocked via `page.route()`).
- Single-screen SPA, **no client router**. `src/App.tsx` reads `window.location.search`
  (deep-link, ADR-0016) and `localStorage` (theme) inside render-time `useState` initializers.
  `src/grid/GridTable.tsx` + `src/grid/model.ts` also read/write `localStorage`.
- `vite.config.ts`:
  - dev proxy: `/health /me /scope /budget /approval /attachments /reference` → `http://127.0.0.1:8000`
    (backend has **no** `/api` prefix — routers are mounted bare, see `backend/app/main.py`).
  - binds `127.0.0.1` explicitly (Windows resolves `localhost` → IPv6 `::1`; IPv4 URL was refused).
  - holds the vitest config block (`jsdom`, `setupFiles: ./src/test/setup.ts`, `exclude: e2e/**`).
- `src/api/client.ts:13` — `const API_BASE: string = import.meta.env.VITE_API_BASE ?? ''`
  (same-origin default; 401 → redirect `/.auth/login/aad`, ADR-0004 Easy Auth).
  Grep confirms this is the **only** `import.meta.env` usage in `src/`.
- `index.html` — `<html lang="th" data-theme="light">`, Google Fonts links
  (Newsreader / Archivo / IBM Plex Sans Thai / IBM Plex Mono), favicon `/favicon.svg`.
- `tsconfig.app.json` — strict TS, `types: ["vite/client"]`, excludes all test/e2e files
  from the production typecheck (vitest discovers tests via its own globs).
- CI `.github/workflows/ci-tests.yml` — `cd frontend && npm ci && npm test && npm run build`.
  These commands survive the migration unchanged.
- `backend/Dockerfile` (build context = **repo root**): stage 1 `node:24-alpine` runs
  `npm run build:ci` → `COPY --from=frontend-build /fe/dist ./static`.
  Known incident: unicode "✓" in build logs crashed the **local Windows** az CLI
  (colorama/cp1252) mid `az acr build` — hence the quiet `build:ci` script.
  **Next.js prints "✓ Compiled successfully" too** — same risk class, mitigated in step 9.
- **Backend↔frontend coupling points** (verified 2026-07-23 by reading `backend/app/`):
  the API contract (routes, auth, error shapes) is fully decoupled — zero Python API
  changes needed. But the *static-serving* layer hardcodes Vite's output shape:
  - `backend/app/config.py:104` — default `static_dir_path` falls back to
    `<repo>/frontend/dist` (local preview of a production build). Must become
    `frontend/out` (step 9b) or local `uvicorn` silently runs API-only after migration.
  - `backend/app/static.py:79-81` — mounts `/assets` (Vite's hashed-asset dir) with a
    1-year immutable cache. Next.js export emits hashed assets under `out/_next/static/`
    and has NO `assets/` dir. Without an added mount, `/_next/static/*` files are still
    served correctly by the SPA fallback — but lose the long-cache headers (step 9b).

## 3. File map (before → after)

| Before (Vite) | After (Next) | Action |
|---|---|---|
| `frontend/vite.config.ts` | `frontend/next.config.ts` + `frontend/vitest.config.ts` | split: proxy/export config → next.config; test block → vitest.config |
| `frontend/index.html` | `frontend/src/app/layout.tsx` | port head/fonts/lang/title |
| `frontend/src/main.tsx` | `frontend/src/app/page.tsx` | replace entry with client-only dynamic wrapper |
| `frontend/src/App.tsx` | `frontend/src/App.tsx` (same path) | only change: remove `import './styles/global.css'` |
| `frontend/src/<feature>/*` | unchanged | no moves, no renames |
| `frontend/tsconfig.json` + `tsconfig.app.json` + `tsconfig.node.json` | single `frontend/tsconfig.json` (Next style) | replace; keep strict flags + test excludes |
| `frontend/next-env.d.ts` | new, auto-generated by `next build`/`next dev` | commit it (create-next-app convention) |
| build output `frontend/dist/` | `frontend/out/` | update Dockerfile + `.gitignore` |
| `VITE_API_BASE` | `NEXT_PUBLIC_API_BASE` | one line in `client.ts` (+ test stub check) |
| `backend/app/config.py` default static_dir (`frontend/dist`) | `frontend/out` | one-line edit + comment (step 9b) |
| `backend/app/static.py` `/assets` long-cache mount | add `/_next/static` long-cache mount | keep `/assets` for rollback compat (step 9b) |

## 4. Gotchas (each maps to a step below)

- **G1 — prerender crash on `window`/`localStorage`.** With `output: 'export'` Next still
  *prerenders pages at build time*. Fix once, at the entry: `app/page.tsx` is a **client
  component** using `dynamic(..., { ssr: false })` — App never runs at build time, so
  **this one move neutralizes every render-time browser touch at once**. Zero edits needed
  inside the 60+ feature components, and **no `platform/` I/O seam is required to ship**
  (see §8.A — that seam is an optional deepening, not a migration blocker).
  *Verified severity (arch review, so the plan doesn't over-claim):* of the render-time
  browser reads, most are **already `try/catch`-guarded and would survive a prerender by
  returning their fallback** — `grid/model.ts` localStorage helpers (`loadStoredColumnWidths`
  et al.) and `admin/useAdminViewToggle` (sessionStorage). The **only two genuinely
  unguarded** render-time reads are both in `App.tsx`: `readStoredTheme()` at ~L19
  (throws `window is not defined`) and `useState(() => parseDeepLink(window.location.search))`
  at ~L44. The `ssr:false` wrapper covers all of them regardless. (Honest choice: everything
  is behind Easy Auth anyway — a prerendered HTML shell has no value.)
- **G2 — global CSS location.** App Router allows global `.css` imports **only** in
  `app/layout.tsx`. So `tokens.css` + `global.css` move there; the import in `App.tsx`
  must be deleted or the build fails.
- **G3 — dev proxy.** `rewrites()` in `next.config.ts` works under `next dev` only; the
  exported static site has no server. Fine — production is same-origin via FastAPI
  `StaticFiles`, exactly like today's `dist/`.
- **G4 — `next/font` avoided.** `next/font/google` downloads fonts at build time —
  fragile in the restricted ACR/Cloud-Shell path. Keep the plain `<link>` tags from the
  canonical mockup (`design/mockups/0002claude design/0002.3budget-export.html`).
- **G5 — unicode build-log crash (repeat of the Vite incident).** Add `ENV CI=true` in
  Dockerfile stage 1 → Next emits plain non-interactive logs. (Build itself runs in ACR
  on Linux; the crash was the *local* az CLI rendering streamed logs.)
- **G6 — IPv6 localhost trap (Windows).** Keep binding to `127.0.0.1`:
  `next dev -H 127.0.0.1`, and Playwright `baseURL`/`webServer.url` use `127.0.0.1:3000`.
- **G7 — `ssr: false` is only legal inside a Client Component.** `app/page.tsx` must
  start with `'use client'` (Next 15 rejects `ssr:false` in a Server Component).
- **G8 — no ESLint config.** Next warns "No ESLint configuration detected" during build
  and skips — expected; lint stays with oxlint (`npm run lint`).
- **G9 — backend static-serving couples to the bundler's output shape.** `static.py`'s
  long-cache mount and `config.py`'s default path name `dist/`/`assets/` explicitly.
  Miss these and nothing crashes — the app just loses local preview + asset caching.
  Covered by step 9b + the backend test row in §6.

## 5. Step-by-step execution

> One branch/commit set. Each step lists exact files + content.
> Verification commands are in §6 — run them at the flagged checkpoints.

### Step 0 — baseline (prove green BEFORE touching)

```bash
cd frontend
npm test            # all vitest suites green
npm run build       # vite build succeeds (proves starting point)
cd ../backend && pytest tests -m "not integration" -q   # backend baseline too (step 9b touches static.py)
```
If anything is red here, stop — fix on main first, do not migrate on a red baseline.

### Step 1 — dependencies

```bash
cd frontend
npm install next@latest          # React 19 is supported by Next ≥15.3; pin whatever lands
npm uninstall vite               # @vitejs/plugin-react STAYS (vitest uses it for JSX)
```
Expected `package.json` deps after: `next`, `react`, `react-dom`.
devDeps keep: `@vitejs/plugin-react`, `vitest`, `jsdom`, `oxlint`, `typescript`,
`@types/react`, `@types/react-dom`, `@types/node`, playwright + testing-library packages.

### Step 2 — `frontend/next.config.ts` (new)

```ts
import type { NextConfig } from 'next'

// Dev-only proxy parity with the old vite.config.ts. The A7 backend has NO
// `/api` prefix (routers mounted bare in backend/app/main.py), so each known
// route namespace is forwarded as-is. Rewrites exist only under `next dev`;
// the exported static site is served same-origin by FastAPI in production.
const BACKEND_DEV_SERVER = 'http://127.0.0.1:8000'

const nextConfig: NextConfig = {
  output: 'export',
  // No next/image use today; block the optimized-loader foot-gun for later.
  images: { unoptimized: true },
  async rewrites() {
    const namespaces = ['health', 'me', 'scope', 'budget', 'approval', 'attachments', 'reference']
    return namespaces.map((ns) => ({
      source: `/${ns}/:path*`,
      destination: `${BACKEND_DEV_SERVER}/${ns}/:path*`,
    }))
  },
}

export default nextConfig
```

### Step 3 — app shell

**`frontend/src/app/layout.tsx`** (new — ports `index.html`; charset/viewport are
Next defaults, `lang`/`data-theme`/fonts carried over verbatim):

```tsx
import type { Metadata, Viewport } from 'next'
import '../styles/tokens.css'
import '../styles/global.css'

export const metadata: Metadata = {
  title: 'Budget Management — Chememan',
  icons: { icon: '/favicon.svg' },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1.0,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="th" data-theme="light">
      <head>
        {/* Fonts match the canonical mockup (design/mockups/0002claude design/0002.3budget-export.html).
            Plain <link>, NOT next/font — see gotcha G4. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400;1,6..72,500&family=Archivo:wght@400;500;600;700&family=IBM+Plex+Sans+Thai:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  )
}
```

**`frontend/src/app/page.tsx`** (new — the ONE client-only boundary, gotchas G1+G7):

```tsx
'use client'

import dynamic from 'next/dynamic'

// The whole app is client-only: App.tsx and the grid read window/localStorage
// in render-time initializers, and every screen sits behind Easy Auth, so a
// build-time prerender would crash (G1) while buying nothing (no SEO/public).
const App = dynamic(() => import('../App'), { ssr: false })

export default function Page() {
  return <App />
}
```

**`frontend/src/App.tsx`** — one-line edit: delete `import './styles/global.css'`
(G2; both stylesheets are now loaded by `layout.tsx`). Nothing else changes.

**Delete:** `frontend/src/main.tsx`, `frontend/index.html`.

#### Step 3 `[ARCH]` — shell hygiene folded in (files are open anyway)

The arch review flagged three cleanups whose files this step already rewrites; do them
here so they never need a second PR touching the same shell. Full rationale → §8.A.

- **`[ARCH-a]` Pre-paint theme script — DO (real, not cosmetic).** `layout.tsx` hardcodes
  `data-theme="light"`; today's `ThemeToggle` only re-applies the stored theme in a
  `useEffect`. Under `dynamic(ssr:false)` the whole App (and thus that effect) runs *later*
  than it does on Vite → opted-in **dark** users get a longer flash-of-light. Fix at the
  shell, before first paint, inside the `<head>` of `layout.tsx`:
  ```tsx
  <script dangerouslySetInnerHTML={{ __html:
    `try{var t=localStorage.getItem('budget-theme');if(t==='dark')document.documentElement.dataset.theme='dark'}catch(e){}` }} />
  ```
  `ThemeToggle` then only toggles thereafter. (Static-export-safe: inline script ships in
  the exported HTML; no server needed.)
- **`[ARCH-b]` `usePersistedToggle` (OPTIONAL).** `App.tsx`'s theme read/write and
  `admin/useAdminViewToggle` are the *same* "persisted boolean + storage guard" shape with
  **inconsistent guards** (theme unguarded, admin `try/catch`-guarded). If `App.tsx` is
  already being edited, optionally extract one `usePersistedToggle(key, storage)` so the
  guard is uniform. Small win; skip if it widens the diff — it is not required to ship.
- **`[ARCH-c]` `platform/location.ts` (OPTIONAL).** `App.tsx:~44` reads
  `window.location.search` at render. The `ssr:false` wrapper already makes this safe, so
  this is *not* required — but a one-function `currentSearch()` (guarded `typeof window`)
  is the natural companion to the Step-4 env reader if you choose to create `platform/`.

### Step 4 — `src/api/client.ts` env swap

```ts
// before
const API_BASE: string = import.meta.env.VITE_API_BASE ?? ''
// after
const API_BASE: string = process.env.NEXT_PUBLIC_API_BASE ?? ''
```
Update the doc comment line that mentions `VITE_API_BASE`. Check
`src/api/client.test.ts` / `src/auth/useAuth.test.tsx` for `import.meta.env` stubs
and switch them to `process.env.NEXT_PUBLIC_API_BASE` if present (grep first).
No `.env` file exists for the frontend today — the `''` same-origin default is what
runs everywhere; keep it.

> `[ARCH-c]` note: this is the **only** `import.meta.env` read in `src/` (grep-verified),
> and it is a **hard build break** under Next (not just a prerender issue — `import.meta.env`
> is a Vite-only global). One line, one file. The arch review's optional `platform/env.ts`
> (a single `apiBase()` function) buys nothing over this one-line edit *unless* you also
> create `platform/location.ts` above and want the whole browser-I/O contract in one folder.
> Default: **just do the one-liner**; skip the folder.

### Step 5 — TypeScript config

Replace the project-references trio with **one** `frontend/tsconfig.json`
(delete `tsconfig.app.json` + `tsconfig.node.json`):

```json
{
  "compilerOptions": {
    "target": "ES2023",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "esnext",
    "moduleResolution": "bundler",
    "jsx": "preserve",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "noEmit": true,
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "src"],
  "exclude": [
    "node_modules",
    "src/**/*.test.ts",
    "src/**/*.test.tsx",
    "src/**/*.spec.ts",
    "src/**/*.spec.tsx",
    "src/test/**",
    "e2e/**"
  ]
}
```
Notes: `types: ["vite/client"]` drops out (replaced by auto-generated
`next-env.d.ts` — created on first `next build`/`next dev`, commit it).
Test files stay excluded from the build typecheck — identical semantics to the old
`tsc -b` setup; vitest type-transpiles tests itself and never uses this file.

### Step 6 — vitest config

**`frontend/vitest.config.ts`** (new — the test block moved verbatim):

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Playwright's permanent E2E suite lives in ./e2e and must never be picked
    // up by Vitest's default *.spec.ts include glob.
    exclude: ['e2e/**', 'node_modules/**'],
  },
})
```

**Delete:** `frontend/vite.config.ts`.

### Step 7 — `package.json` scripts

| Script | Before | After |
|---|---|---|
| `dev` | `vite` | `next dev -H 127.0.0.1` (G6) |
| `build` | `tsc -b && vite build` | `next build` (type-check is built in) |
| `build:ci` | `tsc -b && vite build --logLevel warn` | `next build` (plain logs via `CI=true` in Docker instead — G5) |
| `preview` | `vite preview` | **removed** (static `out/` can be served by any static server if ever needed) |
| `test` / `lint` / `test:e2e` | unchanged | unchanged |

### Step 8 — Playwright (`frontend/playwright.config.ts`)

- `baseURL`: `http://localhost:5173` → `http://127.0.0.1:3000` (G6 — not `localhost`).
- `webServer`: `{ command: 'npm run dev', url: 'http://127.0.0.1:3000', reuseExistingServer: !process.env.CI, timeout: 60_000 }`
  (timeout raised 30s → 60s: Next cold-compiles the route on first hit).
- Keep `workers: 3` and the existing comment block; update the comment where it says
  "Vite dev server" → "Next dev server" (cold-compile caveat still applies).
- Update the header docstring ("started automatically (`npm run dev`, Vite)" → Next).

### Step 9 — Dockerfile (`backend/Dockerfile`)

Stage 1 edits only:
```dockerfile
# after COPY frontend/ ./  — plain, non-interactive build logs so streamed
# output can never re-trigger the Windows az CLI colorama/cp1252 crash (G5).
ENV CI=true
RUN npm run build:ci
```
and in stage 2:
```dockerfile
COPY --from=frontend-build /fe/out ./static   # was /fe/dist
```
Update header comments that say "React+Vite SPA" → "Next.js static export".
**Cannot be verified locally** (no Docker on this machine — CLAUDE.md hard rule).
It will be exercised on the next `az acr build` per `docs/deploy/A14_RUNBOOK.md`;
state this plainly in the commit message. CI's `npm run build` still covers the
Next build itself.

### Step 9b — backend static-serving adjustments (G9)

Only the two files that hardcode Vite's output shape; **no API router code changes.**

**`backend/app/config.py`** — default local fallback, one line (+ comment block above it):
```python
# backend/app/config.py -> backend/ -> repo root -> frontend/out
return Path(__file__).resolve().parent.parent.parent / "frontend" / "out"   # was "dist"
```
Update the comment at `config.py:92-96` (`frontend/dist` → `frontend/out`).

**`backend/app/static.py`** — add the Next hashed-asset mount right after the
existing `/assets` block (keep `/assets`: zero-cost rollback compat while the repo
transitions, and it simply doesn't mount when no `assets/` dir exists):
```python
    next_static_dir = static_dir / "_next" / "static"
    if next_static_dir.is_dir():
        # Next.js export layout: hashed assets live under /_next/static (no assets/ dir).
        app.mount("/_next/static", _LongCacheStaticFiles(directory=next_static_dir), name="spa-next-static")
```
Also update the module docstring (line 1: "`frontend/dist`" → "the frontend build
output — `frontend/out` (Next.js export), previously `frontend/dist` (Vite)").
The `_RESERVED_API_PREFIXES` set needs NO change: `_next` paths either hit real files
(served) or carry a suffix (404) — correct behavior already.

**`backend/tests/test_static.py`** — add one test mirroring
`test_static_dir_present_serves_asset_with_long_cache`, building a tmp static dir with
`_next/static/app-<hash>.js` and asserting it serves 200 + the immutable Cache-Control
header. (Behavior-verification style, same as the existing tests.)

### Step 10 — `.gitignore` / stale-reference sweep

- `frontend/.gitignore`: `dist` → `out` (add `out`; drop `dist` only if nothing else emits it).
- Grep the repo for newly-stale mentions and fix: `vite`, `VITE_`, `dist/`
  under `frontend/`, `.dockerignore`, `docs/`, `CLAUDE.md`.

### Step 11 — housekeeping (same commit, per CLAUDE.md protocol)

- `CLAUDE.md`: tech-stack line → `Next.js (static export, App Router) · FastAPI · ...`;
  refresh the "React + FastAPI main app" note and any Vite mention.
- New ADR `docs/adr/0018-frontend-nextjs-static-export.md` (match existing ADR format):
  context = org standard; decision = Next.js App Router with `output: 'export'`,
  whole app client-only (`ssr:false` wrapper); consequences = no SSR/RSC/server
  actions/middleware, dev proxy via `rewrites()`, `out/` replaces `dist/`
  (+ the two backend static-serving touchpoints from step 9b),
  flipping to Node server later remains cheap.
- `tracker/pending.json`: add the task entry (tracker is the ONLY hand-over channel).
- `.claude/plan.md`: tick/update per the mandatory plan-sync rule.

## 6. Verification matrix

| Checkpoint | Command | Expected |
|---|---|---|
| After step 6 | `cd frontend && npm test` | all existing vitest suites green (zero rewrites intended) |
| After step 7 | `npm run build` | succeeds; emits `frontend/out/index.html` (+ `404.html`, `favicon.svg`, `_next/static/*`) |
| After step 8 | `npm run dev` + browser `http://127.0.0.1:3000` | app renders; with backend up, `/me` resolves through the rewrite proxy |
| After step 8 | `npx playwright test` | 4 e2e specs green (backend mocked — no FastAPI needed) |
| After step 9b | `cd backend && pytest tests/test_static.py -q` | existing tests + new `/_next/static` long-cache test green |
| Final | `npm run lint` (frontend) + `pytest tests -m "not integration" -q` (backend) | oxlint clean; full mocked backend suite green |
| CI | push branch | `ci-tests.yml` frontend + backend jobs green (commands unchanged) |
| Deploy | next manual `az acr build` (A14 runbook) | image builds; FastAPI serves the app from `STATIC_DIR`; `/_next/static/*` carries immutable cache headers |

Rollback: the migration is one commit set — `git revert` restores Vite exactly;
no backend API/schema changes are involved (the `/assets` mount stays, so even a
mixed state — old `dist/` image served by new backend code — keeps working).

## 7. Explicitly out of scope

- TanStack Query / optimistic updates / route-level code splitting — follow-up task.
- Multi-route App Router restructure — only when a second screen actually exists.
- `budget-app-deploy.yml.DISABLED` — untouched (nothing Vite-specific inside).
- Any change to backend API routes, DB, ADRs 0002/0004/0012/0016 semantics.
  (Backend edits are limited to the three build/static-serving touchpoints in steps 9 + 9b.)
- **All architecture deepenings in §8** except the three `[ARCH-a/b/c]` shell items folded
  into steps 3–4 above. They touch files this migration never opens; bundling them would
  break the "one clean revertible commit set" property.

## 8. Architecture backlog (from the 2026-07-23 deletion-test review)

Read-only review of all ~66 `src/` files, 6 dimensions, every finding adversarially
re-verified against the code (21 survived of 22 raw). **The migration deliberately carries
NONE of these except `[ARCH-a/b/c]` (steps 3–4).** Each item below names its own file set —
none overlaps the migration touch-set (`App/main/index/vite.config/tsconfig/client.ts` +
the two backend static files), so each is a **separate PR** you can grab in any order after
Next is in. Ranked by the deletion test: *does extracting it concentrate complexity, or just
move it?*

### 8.A — `[ARCH]` folded into the migration (steps 3–4), rationale here

The `platform/` I/O seam (`storage.ts` + `env.ts` + `location.ts`) is a **legit but modest**
dedup — `Worth exploring`, not `Strong`. The verify pass **downgraded** the initial
"everything crashes SSR" framing: 6 of 8 web-storage touches are already `try/catch`-guarded
(§4 G1). So the seam's real value is (a) making theme/width/admin-toggle logic unit-testable
with an injectable `memoryStorage()` fake instead of `vi.spyOn(window.localStorage…)`
(`grid/model.test.ts` does this today), and (b) one audit folder for browser I/O. **It is
NOT a migration blocker** — `ssr:false` already is. Ship the migration first; if you later
want the testability win, `platform/storage.ts` is a clean standalone PR that also lets
`grid/model.ts` reclaim its "no browser" header (see §8.B `columnWidthStorage`).

### 8.B — Independent post-migration PRs, ranked

**Strong (do these first — clear depth win, well-scoped):**

1. **`describeApiError(err, fallback)` in `client.ts`** — files: `api/client.ts` + 5 component
   files. The exact string `` `${err.message}${err.detail ? ` (${err.detail})` : ''}` `` is
   **copy-pasted at 10 sites** (BudgetGrid ×3, DetailSubform ×2, TripManager ×3,
   ApprovalActionBar, AttachmentsModal) inside 4 differently-named private `describeError`
   helpers. `apiFetch` is otherwise a deep module; this is its one shallow leaked edge. One
   exported function; components collapse to `describeApiError(err, 'บันทึกไม่สำเร็จ')`. The
   409/500 *recovery* branches stay put (they reload different things).
2. **`useResizableColumns` hook out of `GridTable.tsx`** — files: `grid/GridTable.tsx`,
   `grid/useResizableColumns.ts` (new). A whole resize+measure+persist state machine
   (colWidths lazy-init, `hasOverrideRef`, `measureContainerRef`, the auto-fit
   `useLayoutEffect`, `draggingKey`, `dragStateRef`/`dragListenersRef`, `detachDragListeners`,
   the unmount cleanup, the full mouse/touch drag handlers, `measureColumnWidths`) lives
   *inline in a 995-line render function* — untestable except through the whole table.
   Returns `{ colWidths, freezeStyle, draggingKey, getResizeHandleProps, resetColumns,
   measureContainerRef }`; `ColumnWidthMeasurer` stays a presentational child.
   **Scope guard:** extract ONLY the resize machinery — leave `colFilters` and
   `columnsCollapsed` inline (they are one `useState` + pure helpers; hook-ifying them is a
   pass-through).

**Worth exploring (real, smaller or needs a sign-off):**

3. **`columnWidthStorage.ts`** — move the 4 localStorage helpers out of `grid/model.ts` so
   its "Pure grid logic — no DOM, no fetch" header (line 1) becomes true again; delete the
   `__proto__` spy from `model.test.ts`. Pairs naturally with #2 and §8.A.
4. **`useAsyncResource<T>(fetcher, {fallbackError, enabled?})`** — files: `auth/useAuth.ts`,
   `auth/useScope.ts`. These two are the **same** fetch-on-mount + `cancelled`-guard +
   error→Thai-string machine, differing only in endpoint + mapping. Collapse both to one
   fetch + one map. Mirror TanStack's `{data,loading,error,reload}` shape so the later Query
   swap is mechanical. (Do NOT force the *component* loaders through it — see §8.D.)
5. **Subform `saveAll` drift fix** *(behavior change → needs jakkaritw sign-off)* — files:
   `subform/DetailSubform.tsx`. The two `saveAll` twins **silently diverged** on the exact
   points the 2026-07-19 races lived: `DetailSubform`'s 409 branch **auto-discards** every
   unprocessed row (`fetchDetailLines→setRows→return`) and it has **no `<fieldset disabled>`
   in-flight freeze**, while `TripManager` annotates-and-continues + freezes. Make
   `DetailSubform` match `TripManager`. Do NOT extract a shared engine (§8.D).
6. **`isConflict(err)` predicate in `client.ts`** — replaces 8 duplicated
   `err instanceof ApiError && err.status === 409` checks; also fixes `BudgetGrid.tsx:206`
   re-hardcoding the 409 Thai string instead of reusing `err.message`.
7. **`planningYear(now)` / `standingYear(py)=py-1` in `grid/model.ts`** — `new Date().getFullYear()`
   year logic is duplicated **4×** (`YearPicker`, `defaultPlanningYear` verbatim in both
   `BudgetGrid` and `UserBar`, `deepLink` clamp) and none takes an injectable clock —
   untestable without mocking global `Date`. The injectable-clock pattern **already exists
   next door** (`nowMonthKey(date = new Date())`) and wasn't applied. Keep the picker
   (−1..+2) and deep-link (±5) windows as two separate clock-injectable functions.

### 8.C — Two real bugs the review surfaced (not Next-related)

- **Last-response-wins race** — `BudgetGrid.loadGrid` (effect keyed on
  `[year, department, adminViewEnabled, deptResolved]`) and `ApprovalActionBar.load` have
  **no `cancelled` guard** (the two auth hooks do). Fast ฝ่าย/ปี toggling lets an older
  response land after a newer one and overwrite it. Fix: 3-line `cancelled` + cleanup in
  those **two** effects only (the other 3 loaders are React-19-benign unmount-only).
- **Double `/scope/departments` fetch + `role='none'` leak** — `useOwnDepartments` (UserBar)
  and `BudgetGrid` both fire `GET /scope/departments?admin_view_enabled=false` on every
  normal-filler load; UserBar also fires it for `role='none'` (matches e2e finding 4.1 —
  benign empty response, no data leak). Real dedup, but its right home is the **TanStack
  Query follow-up** (a single `admin_view_enabled`-keyed owner), not a hand-rolled hook now.

### 8.D — Rejected seams (deletion test FAILED — recorded so future reviews don't re-suggest)

- **A generic `(items, saveOne, onConflict) → results` batch engine** — shallow pass-through.
  Every bug-bearing decision lives in the per-form loop *body* (`DetailSubform` = 1 line/item;
  `TripManager`'s item is a nested mini-batch: trip write + 3 manual lines + stale-closure
  guard). Extracting the ~12-line mechanical skeleton **moves** complexity, doesn't
  concentrate it. Fix the drift as a consistency patch (§8.B #5) instead.
- **A shared "conflict-owning" resource hook** (read + 409-refetch in one abstraction) — a
  **false seam**. When the TanStack follow-up lands, migrate only the **read** half to
  `useQuery` and keep each 409 handler in its component (they reload different things). Do
  not build a bespoke conflict hook.
- **`platform/dialogs.ts`** (wrapping `window.confirm`/`window.open`) — the `typeof window`
  guard is dead code in event handlers and the one-line `vi.spyOn` is already clean. Passthrough.
- **Hook-ifying `colFilters` / `columnsCollapsed`** — one `useState` + pure helpers each;
  a wrapper adds nothing. (Scope guard for §8.B #2.)
- **Collapsing the per-endpoint `api/*.ts` wrappers** — they **earn their keep** as a typed,
  mockable seam (the e2e suite mocks at exactly this layer). Keep them.

### 8.E — Suggested sequencing

Migration (steps 0–11, this doc) → **then** the deferred **TanStack Query follow-up**
(reads → `useQuery`; absorbs §8.B #4, §8.C dedup, and the `useFillGlCount` heavy-fetch smell
— the header pill currently fetches the *entire* `/budget` payload for one scalar) →
**then** the standalone depth PRs §8.B #1, #2, #3 in any order. The two bugs (§8.C) are
independent and can be grabbed immediately after the migration if they bite before the
Query work.
