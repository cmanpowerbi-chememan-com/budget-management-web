# HTML Modification Guide — 0008 Hide Document Number Master

Surgical changes to the original `0008edit-document-number.html` (1,554 lines).

---

## Change 1: Replace the inline `<script>` block

```html
<script src="api-client.js"></script>
<script src="0008-hide-document.js"></script>
```

---

## Change 2: Required IDs on existing form elements

| Element | Required ID |
|---------|-------------|
| Document Number dropdown input | `docNumInput` |
| Fiscal Year number input (min=2020 max=2099) | `yearInput` |
| Fiscal Month dropdown | `monthSelect` |
| Table | `dataTable` |
| Table search input | `tableSearch` |
| Delete confirm modal | `deleteModal` |
| Error modal | `errorModal` |
| Success toast | `successToast` |
| Doc count chip | `countDocs` |
| Period count chip | `countPeriods` |

---

## Change 3: Year input attributes

The original HTML already has range attributes. Verify:

```html
<input type="number" id="yearInput"
       min="2020" max="2099"
       step="1" required />
```

These mirror the backend Pydantic + SQL CHECK constraints.

---

## Change 4: Month dropdown — populated dynamically by JS

The original HTML may have hardcoded `<option>` tags 1-12.  
The new JS calls `populateMonthDropdown()` to fill in Thai month names + number.

If original HTML hardcodes English options, keep them — `populateMonthDropdown()` will overwrite.

---

## Change 5: Period column shows "YYYY-MM"

Frontend computes display via SQL `CONCAT(year, '-', LPAD(month, 2, '0'))` in `list_handler.py`. Result is `period` field in JSON response.

Make sure the table column shows `period` (not `fiscal_year` alone).

---

## What was NOT changed

- All CSS, theme system, fonts, color palette
- Modal markup, animations, transitions
- Dropdown fuzzy search behavior for Document Number

If anything visually differs from the original after applying these changes, it's a bug.
