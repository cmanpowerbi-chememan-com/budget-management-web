# D5 — The 1-hour session: what is it for, and what does the dialog say?

Type: `wayfinder:grilling` · Status: **CLOSED 2026-09-06 — APPLIED TO PRODUCTION, REVERT OUTSTANDING** · Blocked by: ~~D1~~ **closed 2026-09-06 — but D1 chose PRODUCTION, which changes this ticket's premise entirely. Read the amendment at the bottom before answering.**

## Question

The ask is "แก้ไข stg web เหมือนตอนทดสอบ SIT ex. time web expiried every 1 hr". What is the
1-hour session actually for — exercising the expiry dialog once, or running the whole round on a
short session? And what happens to the dialog's copy, which currently states a different number?

## Ground truth

- **Staging has no `cookieExpiration` block at all right now** — it runs the Container Apps
  platform default, `FixedTime` / `08:00:00` (≈8 h). Production is explicitly `14:00:00`.
- Neither app has a `login.tokenStore`, so **expiry is fixed from login, never sliding**. A
  1-hour setting forces every attendee to re-login two or three times in a working session,
  losing any figure typed but not yet blurred.
- SIT's 20-minute setting **was applied and was reverted.** Tracker `sit-session-expiry-5min`
  records the exact command:
  `az containerapp auth update -n cman-budget-web-stg -g CMAN-BUDGET-MNGT-WEB-RG --set login.cookieExpiration.convention=FixedTime --set login.cookieExpiration.timeToExpiration=00:20:00`
  and `stg-revert-session-and-sit-impersonate` records the revert and its consequence.
- `authConfigs/current` is a **per-app ARM child resource**, so a staging change physically
  cannot touch production.

## The thing nobody has logged

`frontend/src/api/sessionExpiry.ts:16` hardcodes the dialog body:

> `หมดเวลาการเข้าใช้งาน (ระบบให้ล็อกอินได้ครั้งละ 14 ชั่วโมง) กรุณา login ใหม่อีกครั้ง`

On a 1-hour staging that sentence is **false to every tester**, and a tester who reads a wrong
number in an error dialog files it as a defect. Making it env-driven is cheaper than the earlier
estimate suggested: the literal appears in exactly **two** files across `frontend/src` — the
source line and `grid/BudgetGrid.test.tsx:162`. One source line, one test.

## Options

- **(a) Do not change it.** Run on the ≈8 h staging default (or production's 14 h), and script
  the expiry check as a deliberate short window at the end of day 1 by applying 1 h, testing, and
  reverting the same day.
- **(b) Apply 1 h for the whole round** and make the dialog copy env-driven first.
- **(c) Apply 1 h and leave the copy wrong**, briefing testers verbally not to report it.

## Recommendation

**(a)**, unless the point is specifically to prove the round survives repeated re-logins. One
scripted expiry test proves the dialog; a whole round on a 1-hour fixed cookie mostly proves that
people dislike logging in. If **(b)** is chosen, the copy fix ships first — it is a one-line
change plus one test.

---

## AMENDMENT 2026-09-06 — D1 chose production, so this is no longer a staging question

Everything above was written assuming the 1-hour cookie would land on staging, where nothing is
at stake. **It would now land on `cman-budget-web-prd`**, and that is a different act:

- Production's cookie is currently `14:00:00`. Six departments already hold real FY2027 budget
  rows (17 rows / 147,140.00 THB company-wide), and the real submission deadline is 2026-10-07.
- Lowering it affects **every** user of the production app for as long as it stands, not just
  the five attendees. Anyone outside UAT who is mid-entry gets logged out an hour after login.
- Because there is no `tokenStore` on either app, expiry is **fixed from login, never sliding**.
  It does not matter how actively someone is typing.
- The change only takes effect for logins made **after** it lands, so testers must re-login once
  for it to apply at all, and again every hour after that.
- Reverting is one `az containerapp auth update` back to `14:00:00`, and the ARM resource is
  per-app, so the change cannot leak anywhere else.

The dialog-copy problem is unchanged and now worse: on a 1-hour production the sentence
"ระบบให้ล็อกอินได้ครั้งละ 14 ชั่วโมง" would be wrong for **real users**, not just testers.

**Revised recommendation: option (a), scoped as a booked slot.** Apply `01:00:00` at an agreed
time, run the expiry case, revert to `14:00:00` the same day, and record both commands in the run
log. That proves the dialog without leaving production on a short session or shipping a copy fix
first. If the round is instead meant to run the whole way on 1 hour, the copy fix ships before
the change — one source line (`frontend/src/api/sessionExpiry.ts:16`) and one test
(`frontend/src/grid/BudgetGrid.test.tsx:162`).

---

## RESOLUTION — CLOSED 2026-09-06 · APPLIED · **REVERT STILL OWED**

**jakkaritw chose option (b), not (a):** run the whole round on a 1-hour session rather than
booking a short slot. His words: *"ไม่ดีกว่าเปลี่ยนเปน ทุกๆ 1 hr ไปเลย แต่โนตไว้ว่าต้องแก้กลับหลัง uat done"*
(he first proposed 3 hours, then changed to 1 hour before anything was applied).

**This is already live on production.** Applied 2026-09-06:

```bash
az containerapp auth update -n cman-budget-web-prd -g CMAN-BUDGET-MNGT-WEB-RG   --set login.cookieExpiration.convention=FixedTime   --set login.cookieExpiration.timeToExpiration=01:00:00
```

Verified immediately after: `timeToExpiration` `14:00:00` → `01:00:00`, and **ten other auth
fields byte-identical** (`platform.enabled`, `unauthenticatedClientAction=RedirectToLoginPage`,
`redirectToProvider`, AAD `clientId 61d5d556-…`, `clientSecretSettingName`, `openIdIssuer`,
`allowedAudiences`, `allowedApplications`, `isAutoProvisioned`, `excludedPaths`); `login` key set
unchanged; anonymous `curl /health` still **401**, so Easy Auth is still enforcing; **staging
untouched** (still no `cookieExpiration` block).

Pre-change ARM backup: `../prd_auth_backup_before_3h_20260906.json`. The filename says `3h`
because 3 hours was the first proposal; the file content is the true `14:00:00` baseline, and
nothing was ever applied at 3 hours.

### The revert — tracked as `prd-session-1h-revert-after-uat`

**One command, and easier than the staging precedent**, because production already *has* a
`cookieExpiration` block. The 2026-08-18 staging change had to be undone by GET → strip the node
in Python → PUT the whole object (because `--set` cannot delete a node and `az rest --method
patch` returns 405 on authConfigs). None of that applies here:

```bash
az containerapp auth update -n cman-budget-web-prd -g CMAN-BUDGET-MNGT-WEB-RG   --set login.cookieExpiration.convention=FixedTime   --set login.cookieExpiration.timeToExpiration=14:00:00
```

### Three consequences that belong in the pack and the run plan

1. **It applies only to logins made after the change.** Anyone already signed in keeps their old
   14-hour cookie until they log out. Testers must log in fresh for 1 hour to take effect.
2. **It is fixed from login and does not slide with activity** — neither app has a `tokenStore`.
   Typing continuously does not extend it. Expect a re-login roughly every hour, and warn testers
   that a figure typed but not yet blurred is lost (ADR-0028, accepted by design).
3. **It affects every production user, not only the five testers.** That is why the revert is a
   dated, tracked obligation rather than a note.

### The dialog copy — ACCEPTED AS-IS by jakkaritw, 2026-09-06

The session-expired dialog hardcodes `ระบบให้ล็อกอินได้ครั้งละ 14 ชั่วโมง` at
`frontend/src/api/sessionExpiry.ts:16`. While the cookie is 1 hour that sentence is false, and it
is false for **real production users**, not only the five testers.

**jakkaritw's verdict: "acceptable" — do not fix.** No code change, no production deploy for this
string. This is a deliberate choice ("ตั้งใจไม่ทำ"), not an outstanding task, so it must not be
re-proposed by a later session as a bug to close.

Two consequences that follow from accepting it:

1. **It must appear in the known-issues table** of both the UAT pack (T5) and the run plan (T6),
   so a tester who reads "14 ชั่วโมง" and gets logged out after 1 hour reports nothing. Without
   that line, accepting the drift just converts it into a defect report.
2. **It self-heals on revert.** The moment `prd-session-1h-revert-after-uat` puts the cookie back
   to `14:00:00`, the sentence becomes true again with no code change. That is the main reason
   accepting it is cheap: the wrong text lives exactly as long as the wrong cookie.

For the record, had it been fixed the cost was one source line plus one test
(`frontend/src/grid/BudgetGrid.test.tsx:162`) and one production deploy.
