# 16. Approval happens inline on the main budget page — the separate approver inbox is dropped

Date: 2026-06-14
Status: Accepted
Supersedes the **separate approver-inbox screen** (`design/mockups/0013-approver-inbox-demo.html`)
referenced by ADR-0008. The approval-unit, routing, and notification decisions of ADR-0006 / ADR-0008
still stand — only the *surface* approvers act on changes.
Builds on ADR-0008 (approval unit = ฝ่าย), ADR-0014 (admin mode is an opt-in toggle, not always-on).

## Context

Earlier ADRs assumed approvers work from a dedicated inbox page (one row per `(ฝ่าย, year)`, bulk-select,
drill-down) — prototyped as `0013-approver-inbox-demo.html`. The decision to instead approve **inline on
the main budget page** existed only in spec v0.3 (doc 10, Web Access) and as comments in the mockup
`0002.1budget-export.html`, with **no numbered ADR**. Worse, ADR-0008's closing line still cites
`0013-approver-inbox-demo.html` as the inbox source, so a developer reading the ADRs could build the now-dead
inbox screen.

The project philosophy is lean — fewer screens, fewer clicks, one place to work. An approver already opens
the main budget page to *see* a ฝ่าย's numbers; sending them to a separate inbox to act on them is an extra
screen and a context switch for no gain. The same page already carries the ฝ่าย-picker and the row/CC
visibility logic, so approval can live there directly.

## Decision

- **There is NO separate approver inbox screen.** `0013-approver-inbox-demo.html` is a **dead mockup** —
  do not build it.
- **Approval happens inline on the main budget page** — canonical mockup
  `design/mockups/0002claude design/0002.1budget-export.html`:
  - The **ฝ่าย-picker** (already on the page) lets the approver select a department they are an approver for.
  - A **`รออนุมัติ` (pending-approval) badge** marks ฝ่าย that are waiting on **this user's** approval step,
    so the approver sees their queue without leaving the page.
  - **Approve / Reject buttons appear inline**, gated by **whether this user is the current approver step**
    for the selected `(ฝ่าย, fiscal_year)` unit (approver1 = last submitter's managerempcode → นิภาพร →
    วราพร, per ADR-0006 / ADR-0008). If the user is not the current step, the buttons are hidden.
- **Approve / Reject still act on the whole `(ฝ่าย, fiscal_year)` block** (reaffirms ADR-0008) — the inline
  buttons operate on the same approval unit the inbox would have.
- This is purely a **UI surface** change. The approval unit, routing chain, escalation, reject-bounces-the-
  whole-ฝ่าย, and notify-the-last-submitter rules from ADR-0006 / ADR-0008 are **unchanged**.
- Consistent with ADR-0014: when an overlay admin is in **base (approver) mode**, the ฝ่าย-picker shows their
  own ฝ่าย + the `รออนุมัติ` queue with Approve/Reject; in **admin mode** Approve/Reject is hidden
  (administering ≠ approving).

## Consequences

- One fewer screen to build and maintain — approvers work entirely on the page they already use. Matches the
  lean philosophy (fewer screens, fewer clicks).
- The `รออนุมัติ` badge + step-gated buttons replace the inbox's "list of pending units" function; the
  ฝ่าย-picker replaces inbox drill-down.
- ADR-0008's reference to `0013-approver-inbox-demo.html` is superseded (see the patched note there). Future
  devs read the canonical surface as `0002.1budget-export.html`.
- Wired in mockup `design/mockups/0002claude design/0002.1budget-export.html`: ฝ่าย-picker, `รออนุมัติ` badge,
  step-gated inline Approve/Reject.
