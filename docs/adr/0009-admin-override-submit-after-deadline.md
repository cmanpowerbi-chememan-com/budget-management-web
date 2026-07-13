# 9. Admin fill/submit scope and override-submit after the deadline

Date: 2026-06-10
Status: Superseded by ADR-0012 (admin Submit → APPROVED is the override mechanism) and amended by
ADR-0019 (an empty-Filler CC has NO admin fallback — it stays unfilled, removing this ADR's
orphan-ฝ่าย→admin routing). Kept for history.
Builds on: ADR-0006 (approval routing/snapshot/escalation), ADR-0008 (approval unit = ฝ่าย),
project-context "Phase-1 scope & deadline" (the deadline lock)

## Context

Two rules collide at the deadline boundary:

1. **Admin submit scope (normal mode):** an Admin (ADMIN_EMAILS) can SEE all CCs and EDIT any
   CC's Pending (oversight / emergency fix), but may only **submit** CCs bound to their own
   orgcode — admins don't push other departments' budgets through approval during the open
   cycle (keeps them out of others' work unless needed).
2. **Deadline lock:** when a fiscal year's `submission_deadline` passes, every normal user's
   Pending form locks — they cannot edit AND cannot even **submit**. Only Admin can override
   the lock to make a late correction.

The collision: after the deadline a budget-dept Admin overrides the lock and edits one CC in
department Y. To reach the approval chain, *someone* must click Submit. The CC's real owner is
locked out (can't submit); the Admin's normal rule forbids submitting another department's CC.
→ **deadlock**: the corrected budget would sit in DRAFT forever.

Also reaffirmed in grilling (2026-06-10): the **approval unit is the ฝ่าย (department)**, so a
submit/approve always acts on the **whole ฝ่าย as one block** — even when only one CC was
edited, all CCs of that ฝ่าย re-enter approval together as one `approval_status` row.

A tempting "route to the dept's manager" idea was rejected as a general rule: a ฝ่าย does NOT
always have a single manager. Single-head ฝ่าย (most) → all L4 share one L3 managerempcode, so a
"dept manager" exists; but multi-section ฝ่าย (e.g. **Accounting** = 11 fillers under 3 different
section heads สุรีย์/สาลินี/วีนา on one CC) have **no single dept manager**. Deriving one would
need a new ฝ่าย→manager map and contradicts the confirmed "approver1 = direct managerempcode, no
walk-up derive" rule (CLAUDE.md 2026-05-27).

## Decision

- **ฝ่าย-block granularity is firm** (reaffirms ADR-0008): Submit and Approve both operate on the
  whole `(ฝ่าย, fiscal_year)` unit. Editing a single CC of an APPROVED ฝ่าย sends the **entire
  ฝ่าย** back into the chain (re-snapshot), per ADR-0006's edit-APPROVED rule.
- **Admin submit — two modes:**
  - **Normal mode (cycle open):** Admin submits CCs bound to their own orgcode, **plus any
    "orphan ฝ่าย"** — a ฝ่าย that has CCs in file02 but NO submitter in `user_fill_dept`, so
    nobody else can enter its budget (verified 2026-06-10: 8 orphan ฝ่าย / 10 CC — CFO, COO,
    Company Secretary, General, KK/PBB Factory-node, Security KK/TK). Admin fills + submits these
    as the fallback owner; budget dept later assigns a real proxy filler (like CEO→แพรวทิพย์).
  - **Override mode (after deadline):** when Admin overrides the lock to edit a ฝ่าย, Admin may
    also **submit/re-submit that ฝ่าย on behalf** — because the system is closed and Admin is the
    only unlocked operator. Without this, late corrections deadlock.
  - Both the orphan-fill and the override-submit route on the **admin-loop** table below (NOT the
    ฝ่าย's chain), and are logged `ADMIN_OVERRIDE`.
- **Routing for an Admin override-submit = the ADMIN's OWN budget loop** (decided 2026-06-10,
  supersedes the earlier "reuse the ฝ่าย's existing chain" idea). The 4 admins are budget-dept
  authorities, so a correction they make is vouched at THEIR own level in the budget hierarchy,
  starting at the admin's position and running up to the top (Waraporn). Skip-self applies:

  | Admin override-submits | Chain |
  |------------------------|-------|
  | วราพร (100427, Budget Manager — top) | → **APPROVED** (จบ; no one above for budget) |
  | ปิยะดา (101218, AVP Budgeting — above วราพร) | → **APPROVED** (จบ) |
  | นิภาพร (101032, Budget Staff = approver2) | → **วราพร** → APPROVED (skip self) |
  | jakkaritw (Data Analytics — NOT an approver) | → **นิภาพร → วราพร** → APPROVED (full budget review) |

  - This is **admin-override-mode specific**: in NORMAL submit (an admin filling their own dept
    budget), วราพร still routes → ปิยะดา → END per her CLAUDE.md special case. The "วราพร → จบ"
    short-circuit applies ONLY when she is the override-operator fixing another ฝ่าย post-deadline.
  - Routing does NOT use the ฝ่าย's original submitter chain and does NOT use the admin's
    managerempcode — it uses the fixed budget-loop table above.
- **Reject after the deadline** (incl. a ฝ่าย that was auto-submitted at the cutoff per ADR-0006):
  reject sends the ฝ่าย back to DRAFT, but the post-deadline lock disables the user's editing of
  DRAFT too — so the submitter is stuck. **Only an Admin can fix it**: either override-edit and
  re-submit (routed on the admin-loop), or extend the deadline to unlock the original submitter.
  Without this the rejected ฝ่าย would dead-end in a locked DRAFT.
- **Every Admin override action is logged `ADMIN_OVERRIDE`** in `approval_log` (who, when, which
  ฝ่าย/CC, old→new value). `board_budget` import is unaffected by the lock (separate lifecycle).

## Consequences

- No deadlock on post-deadline corrections; the only actor able to operate the closed system can
  also complete the round-trip into approval.
- Routing is a **fixed 4-row admin-loop table**, fully deterministic — no dependence on the ฝ่าย's
  prior snapshot and no need to invent a "dept manager" for multi-section ฝ่าย (Accounting). An
  admin's correction is reviewed only by budget authorities AT or ABOVE the admin's own level,
  which is the correct trust model (a top authority's fix is final; a non-authority's fix gets
  full budget review).
- Admin gains a real cross-department submit power, but only post-deadline, only via an explicit
  override, and fully audited — the normal-cycle "own-orgcode only" guard still holds.
- The shared-ฝ่าย approver1 caveat from ADR-0008 (a NORMAL submitter's last-submitter manager
  isn't guaranteed to be a single dept head) remains OPEN/low-risk and is unrelated to the admin
  path: in practice each ฝ่าย has one representative filler, so the normal snapshot chain is stable
  (user-confirmed 2026-06-10).
