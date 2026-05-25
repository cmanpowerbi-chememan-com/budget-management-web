# HTML Modification Guide — 0007 Orgcode-CostCenter Master

Surgical changes to the original `0007orgcode-costcenter.html` (1,539 lines).
**DO NOT REWRITE THE HTML.**

---

## Change 1: Replace the entire inline `<script>` block

Replace with two `<script>` tags:

```html
<script src="api-client.js"></script>
<script src="0007-orgcode-costcenter.js"></script>
```

---

## Change 2: Verify required IDs on existing markup

| Element | Required ID |
|---------|-------------|
| Cost Center input | `costCenterInput` |
| Orgcode dropdown input | `orgcodeInput` |
| Table | `dataTable` |
| Search input | `tableSearch` |
| Delete confirm modal | `deleteModal` |
| Error modal | `errorModal` |
| Success toast | `successToast` |
| Cost Center count chip | `countCC` |
| Orgcode count chip | `countOrg` |

If the original HTML uses different IDs (e.g. `glCodeInput` carried over from a copy of 0003), update either the HTML or the JS to match.

---

## Change 3: Wire the regex validation on Cost Center input

Original HTML already has the regex behavior inline. Ensure the input has:

```html
<input type="text" id="costCenterInput"
       oninput="validateCostCenterInput(this)"
       maxlength="20" />
```

The function `validateCostCenterInput` is defined in `0007-orgcode-costcenter.js` and matches the original regex `/[^0-9A-Za-z]/g` + auto-uppercase + 600ms red flash on invalid chars.

---

## Change 4: Remove "Edit" button from table row template

Junction table has **no non-PK columns** — there is nothing to edit. The original HTML may show an Edit button per row; remove it from the template. Only Delete remains.

The new JS already does this — the table renderer outputs only the Delete button.

---

## Change 5: (Optional) Add `.input-warning` CSS

Same as 0003 — add to shared stylesheet if not present:

```css
.input-warning {
  border-color: #C9351F !important;
  box-shadow: 0 0 0 3px rgba(201, 53, 31, 0.15);
}
```

---

## Change 6: Verify `/access-denied.html` exists

Same as 0003 — shared across all master pages. If already added during 0003 setup, no action needed.

---

## What was NOT changed

- All CSS (theme system, glassmorphism, animations)
- HTML markup for form, table, modal containers
- Color palette (`--gl-code`, `--gl-group` variables)
- Sort behavior (already client-side, JS preserves it)
- Modal show/hide animations

If anything visually differs from the original after applying these changes, it's a bug.
