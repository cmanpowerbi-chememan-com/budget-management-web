# 2. Build the main budget app on React + Vite + FastAPI now

Date: 2026-06-06
Status: Accepted

## Context

The deployed master-tables module (edit GL group / orgcode-CC / hide-document) is
vanilla HTML + JS on Azure Static Web Apps with integrated Azure Functions, and the
main-app mockup (`0002budget-export.html`) is also vanilla. CLAUDE.md names the
"final" stack as React + Vite (frontend) + FastAPI (backend) on Azure Container Apps,
but `project-context.md` framed React/FastAPI as a later production rewrite.

The main budget app is large (RLS table, monthly grids, special-GL subforms,
approval workflow, import/export, dashboard). The question: build it vanilla now to
match master-tables, or go straight to the production stack.

## Decision

Build the main budget app on **React + Vite + FastAPI now** — skip the vanilla
interim. The mockup is ported into React components; budget logic lives in the
FastAPI backend.

## Consequences

- No throwaway vanilla rewrite later; component model fits the complex grids/subforms.
- **Two stacks coexist**: main app (React/FastAPI on Container Apps) vs master-tables
  (vanilla/Functions on SWA). Open follow-up: migrate master-tables onto the same
  stack, or leave it. Not decided here.
- Adds a build step, Container Apps deploy, and Node tooling — heavier than the SWA
  flow, accepted for the main app's scale.
- No-install constraint still holds: deploy via Azure Cloud Shell; local dev =
  `npm run dev` + `uvicorn`.
