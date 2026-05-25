# HTML Modification Guide — 0003 GL Group Master

The original `0003budget-gl-master.html` is 1,162 lines. **DO NOT REWRITE IT.**
Apply these surgical changes only:

---

## Change 1: Replace the entire inline `<script>` block

**Location:** Original lines `~739–1155` (everything between `<script>` and `</script>` near the bottom)

**Action:** Delete that block. Replace with two `<script>` tags:

```html
<script src="api-client.js"></script>
<script src="0003-gl-group.js"></script>
```

Both files are in the same `frontend/` folder.

---

## Change 2: Add `id` to existing modal containers (if not already present)

The new JS expects these IDs on existing modal markup:

| Element | Required ID |
|---------|-------------|
| Delete confirmation modal container | `deleteModal` |
| Error modal container | `errorModal` |
| Success toast container | `successToast` |
| Error modal `.modal-title` child | — (selector used) |
| Error modal `.modal-body` child | — (selector used) |
| Error modal `.modal-details` child | — (selector used) |

If the original HTML's success modal only has the text "บันทึกสำเร็จ" hardcoded, change it to an empty `<div>` so JS can set the text:

```html
<!-- Before -->
<div id="successToast" class="toast">บันทึกสำเร็จ</div>
<!-- After -->
<div id="successToast" class="toast"></div>
```

---

## Change 3: Verify form input IDs match

The new JS expects:

```html
<input type="text" id="glCodeInput"  ... />
<input type="text" id="glGroupInput" ... />
<input type="text" id="tableSearch"  ... />
```

These are the IDs already used in the original HTML. No change needed unless something was renamed.

---

## Change 4: Verify the data table selector

The new JS uses `#dataTable tbody`. If the original HTML has a different ID (e.g. `mappingTable`), either:
- Update the HTML `<table id="dataTable">`, OR
- Replace `#dataTable` in `0003-gl-group.js` with the original selector

Quick check: open the original HTML and search for `<table` near the bottom of `<body>`.

---

## Change 5: Verify summary chip IDs

The new JS sets text content on:

```html
<span id="countActive">…</span>
<span id="countGroups">…</span>
```

If the original HTML uses different IDs for these summary chips, update either the HTML or the JS to match.

---

## Change 6: (Optional) Add a `.input-warning` CSS rule

The `showWarning()` function adds a temporary class to flash the input red. If the original CSS doesn't have this class, add:

```css
.input-warning {
  border-color: #C9351F !important;
  box-shadow: 0 0 0 3px rgba(201, 53, 31, 0.15);
  animation: shake 0.3s;
}
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-4px); }
  75% { transform: translateX(4px); }
}
```

---

## Change 7: Add `access-denied.html` (one-time, shared across all master pages)

The new JS redirects non-admin users to `/access-denied.html`. Create this file in the parent web shell:

```html
<!doctype html>
<html lang="th">
<head>
  <meta charset="UTF-8" />
  <title>ไม่มีสิทธิ์เข้าถึง · Access Denied</title>
  <link rel="stylesheet" href="/shared/style.css" />
</head>
<body>
  <div class="access-denied">
    <h1>403</h1>
    <h2>ไม่มีสิทธิ์เข้าถึงหน้านี้</h2>
    <p>หน้านี้สำหรับผู้ดูแลระบบ Master Table เท่านั้น</p>
    <p>หากต้องการสิทธิ์การเข้าถึง กรุณาติดต่อทีม Data Engineering</p>
    <a href="/" class="btn">กลับหน้าหลัก</a>
  </div>
</body>
</html>
```

---

## What was NOT changed

The new JS preserves every original behavior:

- Theme system (`PRESETS`, `toggleTheme`, `applyThemeFromStorage`)
- Dropdown fuzzy search (`renderGlCodeList`, `renderGlGroupList`)
- Sort header click handlers (`toggleSort`)
- Modal animations (`show` class)
- Glassmorphism CSS, gradients, fonts
- Color palette (`--gl-code`, `--gl-group`, etc.)
- Form layout, table layout, summary chips

If something visually differs from the original after applying these changes, it's a bug. Compare HTML diff carefully.
