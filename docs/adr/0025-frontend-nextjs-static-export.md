# 25. Frontend: Vite → Next.js (static export, App Router)

Date: 2026-07-23
Status: Accepted
Supersedes: the Vite/React tooling implied by ADR-0002 (main app = React + FastAPI) — ADR-0002's
app-architecture decision (React SPA + FastAPI backend, Entra Easy Auth) is unchanged, only the
build tool/framework under React changes.

## Context

Org standard moved to Next.js (confirmed 2026-07-23). The app was still small (66 source files,
single-screen SPA, no client router) — the cheapest moment to move, before more screens/routes
accumulate. The full execution plan lives in `plan/vite-to-nextjs-migration.md` (decision table,
gotchas G1–G9, step-by-step file map, architecture backlog); this ADR records the decision and
consequences, not the mechanics.

The app is entirely behind Entra ID Easy Auth (ADR-0004) — every byte of real data needs the
user's session, and the backend is FastAPI, not Node. An SSR/RSC Next.js deployment would need a
Node server plus auth-header forwarding for zero benefit (no public/SEO content, nothing can be
usefully rendered before the user is authenticated).

## Decision

- **`output: 'export'`** — static export, no Node server, no SSR/RSC/server actions/middleware.
  Deploy shape is unchanged from the Vite era: static files built in a Docker stage → served
  same-origin by FastAPI's `StaticFiles` mount in the same Container App.
- **Whole app is client-only**, via one `dynamic(() => import('../App'), { ssr: false })` boundary
  in `app/page.tsx` (must live inside a `'use client'` component — Next 15+ rejects `ssr:false` in
  a Server Component). This neutralizes every render-time `window`/`localStorage` read at once
  (App.tsx's deep-link parse and theme read) without touching any of the 60+ feature components.
- **Single route** (`app/page.tsx` only) — Phase-1 is one screen (ADR-0016: approval happens
  inline on the main page, no separate inbox), so the App Router's file-based routing stays at one
  route for the same reason `react-router` was never added.
- **`app/layout.tsx`** owns the global CSS imports (`tokens.css`, `global.css` — App Router only
  allows global CSS imports in the root layout), the font `<link>` tags (plain tags, not
  `next/font/google`, which downloads fonts at build time — fragile on the restricted ACR/Cloud
  Shell build path), and a pre-paint inline `<script>` that applies a stored dark theme before
  first paint (mitigates a longer flash-of-light under `ssr:false`, since `ThemeToggle`'s own
  effect now mounts later than it did under Vite).
- **`frontend/src/platform/`** — a small browser-I/O seam (`env.ts` for the one build-env read,
  `location.ts` for guarded `window.location` reads/navigation, `usePersistedToggle.ts` for one
  shared persisted-state hook consumed by both the theme toggle and the admin-view toggle). Folded
  into this migration because the files it touches (`App.tsx`, `client.ts`,
  `admin/useAdminViewToggle.ts`) were being rewritten anyway for the env/`window` swap; kept
  deliberately small — no dialogs/storage-key abstraction beyond what these two call sites need.
- **`NEXT_PUBLIC_API_BASE`** replaces `VITE_API_BASE` (the only `import.meta.env` read in `src/`,
  a hard build break under Next since `import.meta.env` is Vite-only). Same-origin `''` default,
  unchanged.
- Test/lint stack unchanged: vitest + jsdom + Testing Library (config split out of the old
  `vite.config.ts` into a standalone `vitest.config.ts`), oxlint, Playwright.

## Consequences

- **Backend static-serving touchpoints are DEFERRED, NOT part of this branch.** Plan steps 9/9b
  (`backend/Dockerfile` stage-1 `ENV CI=true` + `npm run build:ci` → `/fe/out`; `backend/app/config.py`'s
  default `static_dir_path` fallback `frontend/dist` → `frontend/out`; `backend/app/static.py`'s
  additional `/_next/static` long-cache mount) are intentionally out of scope of this frontend-only
  milestone. **No backend file was touched.** Until those land, `frontend/out` is not yet wired
  into the Docker image or a local `uvicorn` preview — `next build` and the frontend test suites
  are fully verified, but an end-to-end container build/preview is not. Tracked as the next piece
  of work before deploy.
- `frontend/dist/` → `frontend/out/` as the build output directory; `frontend/.gitignore` and the
  root `.dockerignore` updated accordingly. `next-env.d.ts` is new, auto-generated, and committed
  (create-next-app convention).
- Dev server: `next dev -H 127.0.0.1` (Windows IPv6-localhost trap, same reasoning as the old Vite
  config), port 3000. The dev-only backend proxy (`rewrites()` in `next.config.ts`) only works
  under `next dev` — production stays same-origin via FastAPI, exactly as before.
- **Next's Turbopack dev server compiles the client bundle lazily on first real browser
  navigation** (not at `next dev` startup, since `output: 'export'` + the `ssr:false` shell means
  almost nothing is server-rendered). Measured on this machine: ~27–39s for the first Playwright
  spec to compile+hydrate, low-single-digit seconds once warm. `playwright.config.ts`'s per-test
  `timeout` was raised to 60s (was Playwright's 30s default) to give the first spec headroom
  without masking a genuine hang; `webServer.timeout` was already raised to 60s in the plan for
  the same class of reason.
- **One Next-introduced test-selector collision, fixed:** the App Router always injects its own
  empty `#__next-route-announcer__` (`role="alert"`, an accessibility live-region for route
  announcements). `frontend/e2e/edge-states.spec.ts`'s `page.getByRole('alert')` became ambiguous
  (2 matches) post-migration; rescoped to `.grid-error` (the app's own error-banner class). Same
  assertion intent, unambiguous locator — not a masked regression, the banner text was correct
  throughout.
- **E2E suite is at migration-parity, not 100% green — by design, pre-existing.** 20/23 Playwright
  specs pass, identical to the pre-migration Vite baseline recorded in
  `docs/test/ui-test-results-2026-07-22.md` (one day before this migration). The 3 known failures
  (`approver-journey` 2.1, `edge-states` 4.1, `filler-journey` 1.1) are pre-existing, documented,
  unrelated to Next.js — two are stale e2e selectors after separate app redesigns (YearPicker
  aria-label rename; the ฝ่าย-picker's 2026-07-21 "always auto-select, never land unselected"
  change), the third is the known `role='none'` extra `/scope/departments` fetch (§8.C of the
  migration plan; empty response, no data leak). None were touched by this migration.
- Flipping to a Node server later (SSR/RSC) remains cheap if ever needed — only `next.config.ts`'s
  `output: 'export'` and the `ssr:false` boundary would need to change; the route/component tree
  underneath is unaffected either way.
