# Spot-Test 1B — Insert Log (Phase B write round, user nipapornt@chememan.com)

Date: 2026-07-23 · API: http://127.0.0.1:8000 (APP_ENV=local, real Fabric SQL) ·
Auth header on every call: `x-ms-client-principal-name: nipapornt@chememan.com`

Year semantics: UI "2026" → API `year=2027` → Pending layer rows written with **fiscal_year=2027**.

Baseline (DB-verified before any write): `budget.pending_budget`, `budget.pending_budget_detail`,
`budget.budget_trip` for her 7 CCs FY2027 = **0 rows each**.
Approval status FY2027: dept "Budgeting & Cost Accounting" = DRAFT, dept "General" = DRAFT (neither locked → writes allowed).

Distinctive small amounts (111–372 range) + remark `spot-test 1B` so every row is unmistakable in DB.

---

## 6.1 — Normal GL fills via `PUT /budget/rows` (fiscal_year=2027)

| # | cost_center | gl_account | gl_name | months (mNN=amount) | total_year |
|---|-------------|------------|---------|---------------------|------------|
| A | 10AC020000 | 6210600010 | ค่าโทรศัพท์ / ค่าโทรศัพท์มือถือ | m01=111, m02=112, m03=113, m04=114, m05=115, m06=116 | 681 |
| B | 10AC020000 | 6210900060 | ค่าไปรษณีย์ | m01=121, m02=122, m03=123, m07=127, m08=128 | 621 |
| C | 10GE000000 | 6210500020 | ค่าน้ำประปา | m02=211, m04=212, m06=213, m09=214, m12=215 | 1,065 |
| D | 10GE000000 | 6211400040 | ค่าธรรมเนียมธนาคาร | m03=221, m06=222, m09=223, m12=224 | 890 |

(4 rows / 20 month-cells — results + updated_at tokens appended below as the round progresses.)

### 6.1 results — ALL WRITTEN + DB-VERIFIED 2026-07-23 ~09:47 UTC

| # | HTTP | API total_year | updated_at (lock token) | DB months verified |
|---|------|----------------|--------------------------|--------------------|
| A | 200 | 681.00 | 2026-07-23T09:46:56.002798Z | ✅ m01..m06 = 111/112/113/114/115/116 exact |
| B | 200 | 621.00 | 2026-07-23T09:46:57.182167Z | ✅ m01=121, m02=122, m03=123, m07=127, m08=128 exact |
| C | 200 | 1,065.00 | 2026-07-23T09:46:58.271748Z | ✅ m02=211, m04=212, m06=213, m09=214, m12=215 exact |
| D | 200 | 890.00 | 2026-07-23T09:46:59.364362Z | ✅ m03=221, m06=222, m09=223, m12=224 exact |

DB check: `budget.pending_budget` FY2027 for 10AC020000+10GE000000 = exactly these 4 rows,
all `_user=nipapornt@chememan.com`, remark `spot-test 1B`. **20/20 month cells match.**
(Dims snapshot stored on rows: 10AC020000 → dept "Budgeting & Cost Accounting"; 10GE000000 → dept "General".)

---

## 6.2 — Special GLs (one item per group visible to her) + 2 trips

All 6 special groups appear in her `GET /budget/gl-accounts` (134 GLs, 43 special — all `edit_by=user`).

### Detail lines via `PUT /budget/detail` (fiscal_year=2027)

| # | cost_center | gl_account | group | months | total | meta_json |
|---|-------------|------------|-------|--------|-------|-----------|
| E | 10AC020000 | 6210700030 | Professional & Legal Fee | m02=331, m06=332, m10=333 | 996 | — (free-form group) |
| F | 10GE000000 | 6211900030 | Entertainment (external 030) | m04=341, m08=342 | 683 | {"ประเภทการรับรอง":"Customer"} |
| G | 10GE000000 | 6211200060 | Lease & Rental (vehicle 060) | m05=351, m11=352 | 703 | {"สถานที่ใช้งาน":"BK","กิจกรรม":"spot-test 1B","ประเภทรถ":"Van","ทะเบียนรถ":"1กข-9999"} |
| H | 10GE000000 | 6211700030 | Public Relation & Donation | m09=361 | 361 | — (free-form group) |
| I | 10AC020000 | 6210100150 | Training & Seminar | m01=371, m12=372 | 743 | — (free-form group) |

### Trips via `POST /budget/trip` (Travelling Expense, per-diem auto-derived)

Pre-write expected THB (computed from `/reference` masters + DB rates BEFORE writing):

| # | cost_center | traveler | position → rate | country (group) | days × rate × FX | expected THB | travel_months → split |
|---|-------------|----------|-----------------|-----------------|------------------|--------------|------------------------|
| J domestic | 10AC020000 | 101032 นิภาพร ทองกิ่ง | Senior Supervisor 1 → domestic 250 | Thailand (1, ในประเทศ) | 3 × 250 × 1 | **750.00** | m03=375.00, m05=375.00 |
| K intl asian | 10GE000000 | 100427 วราพร ติรสิทธิ์ | Asst. Dept Head (MGR) → asian 80 | Malaysia (2, asian ต่างประเทศ) | 2 × 80 × 33.0 | **5,280.00** | m07=2,640.00, m08=2,640.00 |

FX source: `dbo.master_currency_rate` fiscal_year=2027 → usd_thb **33.0000**. Both trips side=SGA → per-diem GL 6210400010.

### 6.2 results — ALL WRITTEN + DB-VERIFIED 2026-07-23 ~09:51 UTC

Detail lines (`budget.pending_budget_detail`, FY2027):

| # | HTTP | detail_id | DB months verified | DB total_year | meta persisted |
|---|------|-----------|--------------------|---------------|----------------|
| E | 200 | 50 | ✅ m02=331, m06=332, m10=333 | 996.00 | — (NULL) |
| F | 200 | 51 | ✅ m04=341, m08=342 | 683.00 | ✅ {"ประเภทการรับรอง": "Customer"} |
| G | 200 | 52 | ✅ m05=351, m11=352 | 703.00 | ✅ all 4 keys (BK / Van / 1กข-9999 / กิจกรรม) |
| H | 200 | 53 | ✅ m09=361 | 361.00 | — (NULL) |
| I | 200 | 54 | ✅ m01=371, m12=372 | 743.00 | — (NULL) |

Trips (`budget.budget_trip`, FY2027):

| # | HTTP | trip_id | DB row verified | per-diem detail line | expected THB | DB total_year | match |
|---|------|---------|-----------------|----------------------|--------------|---------------|-------|
| J | 200 | 7 | ✅ Thailand, group 1, days 3, months '03,05', SGA | detail_id 55 (auto_calc=1), m03=375.00, m05=375.00 | 3×250 = 750.00 | **750.00** | ✅ EXACT |
| K | 200 | 8 | ✅ Malaysia, group 2, days 2, months '07,08', SGA | detail_id 56 (auto_calc=1), m07=2,640.00, m08=2,640.00 | 2×80×33.0 = 5,280.00 | **5,280.00** | ✅ EXACT (per-diem + FX correct) |

Parent cells (`budget.pending_budget`) recomputed for all 7 special-GL cells — parent == SUM(detail) verified
(e.g. 10AC020000/6210400010 total 750.00; 10GE000000/6210400010 total 5,280.00). Thai `line_label`s persisted intact (no mojibake).

---

## 12.x — Error-path tests (write round)

### 12.1 — stale `expected_updated_at` → 409 ✅
- Row A updated once with valid token T1 (`09:46:56.002798Z`) → HTTP 200, new token T2 (`09:54:10.277950Z`).
- Second PUT reusing stale T1 → **HTTP 409**, detail `"10AC020000/6210600010/2027 was changed by someone else — reload and retry"`.
- Frontend `apiFetch` maps any 409 → Thai **"ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น กรุณาโหลดข้อมูลใหม่แล้วลองอีกครั้ง"** (`client.ts:82`, status-only mapping — verified in Phase A unit tests; backend detail stays English by design).
- DB check after: row A unchanged (m01=111, m06=116, total 681.00, token=T2) — the 409 wrote nothing.

### 12.2 — out-of-scope cost_center 10IT012000 → 403 ✅
- `PUT /budget/rows` cc=10IT012000 (not in her Fill scope) → **HTTP 403**, detail `"10IT012000 is not in your Fill scope"`
  → frontend maps to Thai **"ไม่มีสิทธิ์เข้าถึงข้อมูลนี้"** (`client.ts:80`).
- DB check after: 0 rows for 10IT012000 in `pending_budget` / `pending_budget_detail` / `budget_trip` — **nothing written**.

### 12.3 — invalid value → 422 naming the field ✅ (with one deviation noted)
- `m01 = 10000000000000000` (violates Pydantic `lt=1e16`) → **HTTP 422**, detail `[{"type":"less_than","loc":["body","m01"],"msg":"Input should be less than 10000000000000000","ctx":{"lt":1e+16}}]`
  — `loc` names the offending field `m01` in exactly the shape the frontend's `summarizeValidationDetail` consumes
  (→ Thai "ข้อมูลไม่ถูกต้อง: m01 — ค่าเกินกำหนด (ต้องน้อยกว่า …)").
- **Deviation:** a *negative* month amount (`m01=-50`) does NOT 422 — it passes Pydantic and is rejected by the
  business guard `NegativeMonthError` → **HTTP 400**, detail `"month amounts must be >= 0"` (frontend shows
  "คำขอไม่ถูกต้อง" + the detail). This matches the documented design in `write_model.py` ("422 vs 400 … is
  intentional"): 422 = malformed request shape, 400 = well-formed but violates a budget rule.
- DB check after both: 0 rows for 10GE000000/6210600010 FY2027 — nothing written.

---

## 14 — FX + admin-locked GLs ✅
- FX correctness verified inside 6.2 trip K: 2 days × 80 USD (asian rate, ADH(MGR)) × 33.0 (FY2027 `master_currency_rate.usd_thb`) = 5,280.00 THB stored exactly.
- Admin-locked GLs: `dbo.gl_group` master = **146** rows; her `GET /budget/gl-accounts` returns **134** → **12 hidden** (matches Phase A's 12). Every returned GL has `edit_by=user`.

---

## 16 — Post-write grid totals == DB ✅
- `GET /budget?year=2027&cost_center=…` re-queried for both CCs AFTER all writes; pending layer compared cell-by-cell
  against `budget.pending_budget` DB rows: **143 cells compared, 0 mismatches** (11 rows: 4 normal + 7 special parents).
- Grand totals: 10AC020000 pending = **3,791.00** (681+621+996+743+750), 10GE000000 = **8,982.00** (1,065+890+683+703+361+5,280).
- GL key-set with non-zero pending in grid == DB row set exactly. API numbers are served from DB, not cached/echoed.

---

## 17 — CLEANUP (executed 2026-07-23 ~10:00 UTC, AFTER all tests above)

Every inserted object deleted via the app's own API (no direct DB DELETE was needed):

| object | endpoint | result |
|--------|----------|--------|
| trip 7 (domestic) | `DELETE /budget/trip?trip_id=7&expected_updated_at=…09:51:05.396926Z` | 200 ok (cascaded per-diem line 55, removed orphan parent) |
| trip 8 (intl asian) | `DELETE /budget/trip?trip_id=8&expected_updated_at=…09:51:06.852978Z` | 200 ok (cascaded per-diem line 56, removed orphan parent) |
| detail 50–54 | `DELETE /budget/detail?detail_id=…&expected_updated_at=…` | 200 ok ×5 (each recomputed its parent; orphan parents auto-removed) |
| rows A–D | `DELETE /budget/rows?cost_center=…&gl_account=…&fiscal_year=2027&expected_updated_at=…` | 200 ok ×4 (row A used post-12.1 token T2) |

### Final DB verification (post-cleanup SELECTs)

| check | count |
|-------|-------|
| `budget.pending_budget` FY2027, her 7 CCs | **0** |
| `budget.pending_budget_detail` FY2027, her 7 CCs | **0** |
| `budget.budget_trip` FY2027, her 7 CCs | **0** |
| orphan detail_ids 50–56 | **0** |
| orphan trip_ids 7–8 | **0** |
| `pending_budget.remark LIKE 'spot-test 1B%'` | **0** |

**Cleanup complete — DB restored to the pre-test baseline (0 rows in all 3 tables).** No approval
state was touched at any point (`/approval/submit|approve|reject` never called; both depts remained DRAFT).
