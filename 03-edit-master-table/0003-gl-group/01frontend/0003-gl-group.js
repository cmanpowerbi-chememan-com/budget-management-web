/* ═══════════════════════════════════════════════════════════
   0003-gl-group.js — Modified application logic
   Replaces the inline <script> section of the original HTML
   (lines ~739-1155 in 0003budget-gl-master.html).

   Preserves: theme system, dropdown UI, sort logic, modal
              animations, render functions.
   Changes:   data arrays now load from API; save/delete now
              POST/DELETE to backend; admin access enforced.
   ═══════════════════════════════════════════════════════════ */

/* ── THEME (preserved from original) ── */
const PRESETS = {
  chememan: { forest:'#00522C', mint:'#1FA378', gold:'#C9963D' },
  ocean:    { forest:'#0E4D6E', mint:'#37B5C7', gold:'#F2C661' },
  sunset:   { forest:'#7B2D26', mint:'#E07B4C', gold:'#F2B752' },
  midnight: { forest:'#1B244B', mint:'#5B73D9', gold:'#A88AE6' },
  nature:   { forest:'#2D5016', mint:'#7BA428', gold:'#B8A04A' },
  royal:    { forest:'#3D1F6E', mint:'#9B6DD9', gold:'#D6B16A' },
};

function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme');
  document.documentElement.setAttribute('data-theme', cur === 'light' ? 'dark' : 'light');
}

function applyThemeFromStorage() {
  const theme = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', theme);
}

/* ═══════════════════════════════════════════════════════════
   DATA — loaded from API at page init (no hardcoded arrays)
   ═══════════════════════════════════════════════════════════ */
let sapGlCodes  = [];   // populated from /api/master/gl-group/reference/gl-codes
let glGroups    = [];   // populated from /api/master/gl-group/reference/gl-groups
let masterData  = [];   // populated from /api/master/gl-group/list

/* UI state (preserved) */
let editMode      = false;
let editKey       = null;
let newRowKey     = null;
let pendingDelete = null;
let sortCol       = null;
let sortDir       = 'asc';
let selectedGlCode  = null;  // from dropdown
let selectedGroupId = null;  // from dropdown OR null if creating new

/* ═══════════════════════════════════════════════════════════
   INIT — replaces the bottom of the original <script>
   ═══════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
  applyThemeFromStorage();

  /* ── Static button wiring (replaces inline onclick in HTML) ── */
  document.getElementById('themeToggleBtn').addEventListener('click', toggleTheme);
  document.getElementById('saveBtn').addEventListener('click', saveRecord);
  document.getElementById('tableSearch').addEventListener('input', renderTable);
  document.getElementById('exportCsvBtn').addEventListener('click', exportCsv);

  /* Sort headers — event delegation on thead */
  document.querySelector('.data-table thead').addEventListener('click', e => {
    const th = e.target.closest('th[data-col]');
    if (th) toggleSort(th.dataset.col);
  });

  /* Table action buttons — event delegation on table */
  document.getElementById('dataTable').addEventListener('click', e => {
    const btn = e.target.closest('button[data-gl-code]');
    if (!btn) return;
    const code = btn.dataset.glCode;
    if (btn.classList.contains('btn-edit'))   editRecord(code);
    else if (btn.classList.contains('btn-danger')) confirmDelete(code);
  });

  /* Notice modal */
  document.getElementById('noticeModal').addEventListener('click', e => { if (e.target.id === 'noticeModal') closeNotice(); });
  document.getElementById('noticeCloseBtn').addEventListener('click', closeNotice);
  document.getElementById('noticeOkBtn').addEventListener('click', closeNotice);

  /* Delete modal */
  document.getElementById('deleteModal').addEventListener('click', e => { if (e.target.id === 'deleteModal') closeDeleteModal(); });
  document.getElementById('deleteCloseBtn').addEventListener('click', closeDeleteModal);
  document.getElementById('deleteCancelBtn').addEventListener('click', closeDeleteModal);
  document.getElementById('deleteConfirmBtn').addEventListener('click', executeDelete);

  /* Error modal */
  document.getElementById('errorModal').addEventListener('click', e => { if (e.target.id === 'errorModal') closeErrorModal(); });
  document.getElementById('errorCloseBtn').addEventListener('click', closeErrorModal);
  document.getElementById('errorOkBtn').addEventListener('click', closeErrorModal);

  /* Dropdown item clicks — event delegation */
  document.getElementById('glCodeList').addEventListener('click', e => {
    const item = e.target.closest('.dropdown-item[data-code]');
    if (item) selectGlCode(item.dataset.code);
  });
  document.getElementById('glGroupList').addEventListener('click', e => {
    const item = e.target.closest('.dropdown-item');
    if (!item) return;
    if ('createName' in item.dataset) selectGlGroupNew(item.dataset.createName);
    else if (item.dataset.groupId)    selectGlGroup(item.dataset.groupId, item.dataset.groupName);
  });

  // Layer 1 of defense in depth: client-side group check
  const ok = await checkAdminAccess();
  if (!ok) return;

  try {
    const [glCodes, groups, mappings] = await Promise.all([
      apiClient.refGlCodes(),
      apiClient.refGlGroups(),
      apiClient.list(),
    ]);
    sapGlCodes = glCodes;
    glGroups   = groups;       // [{group_id, group_name}, ...]
    masterData = mappings;     // [{gl_code, group_id, group_name}, ...]
    renderTable();
    initDropdowns();
  } catch (err) {
    showErrorModal(err);
  }
});

/* ═══════════════════════════════════════════════════════════
   SAVE — async API call (replaces in-memory push/update)
   ═══════════════════════════════════════════════════════════ */
async function saveRecord() {
  const glCode    = document.getElementById('glCodeInput').value.trim();
  const groupText = document.getElementById('glGroupInput').value.trim();

  if (!glCode || !groupText) {
    showWarning('กรุณากรอกข้อมูลให้ครบ');
    return;
  }

  // Build payload — either existing group_id OR new group_name
  const existingGroup = glGroups.find(g => g.group_name === groupText);
  const payload = { gl_code: glCode };
  if (existingGroup) {
    payload.group_id = existingGroup.group_id;
  } else {
    payload.group_name = groupText;   // backend will create_on_save
  }

  // Frontend Fail Fast (UX) — backend re-checks as safety net
  if (!editMode) {
    const dup = masterData.some(r => r.gl_code === glCode);
    if (dup) {
      showErrorModal({
        status: 409,
        body: {
          code: 'DUPLICATE_KEY',
          message_th: 'GL Code นี้มีอยู่ในระบบแล้ว',
        },
      });
      return;
    }
  }

  try {
    const result = await apiClient.save(payload, editMode);
    newRowKey = glCode;
    await refreshAll();
    resetForm();
    showSuccessToast(editMode ? 'อัปเดตสำเร็จ' : 'บันทึกสำเร็จ');
    editMode = false;
    editKey = null;
  } catch (err) {
    showErrorModal(err);
  }
}

/* ═══════════════════════════════════════════════════════════
   DELETE — async API call (replaces in-memory filter)
   Modal pattern preserved from original HTML.
   ═══════════════════════════════════════════════════════════ */
function confirmDelete(glCode) {
  pendingDelete = glCode;
  document.getElementById('deleteModal').classList.add('show');
}

async function executeDelete() {
  if (!pendingDelete) return;
  try {
    await apiClient.remove({ gl_code: pendingDelete });
    await refreshAll();
    closeDeleteModal();
    showSuccessToast('ลบสำเร็จ');
  } catch (err) {
    closeDeleteModal();
    showErrorModal(err);
  }
}

function closeDeleteModal() {
  document.getElementById('deleteModal').classList.remove('show');
  pendingDelete = null;
}

/* ═══════════════════════════════════════════════════════════
   EDIT — populate form, set edit mode (no API call yet)
   ═══════════════════════════════════════════════════════════ */
function editRecord(glCode) {
  const row = masterData.find(r => r.gl_code === glCode);
  if (!row) return;
  document.getElementById('glCodeInput').value  = row.gl_code;
  document.getElementById('glGroupInput').value = row.group_name;
  selectedGlCode  = row.gl_code;
  selectedGroupId = row.group_id;
  editMode = true;
  editKey  = glCode;
}

function resetForm() {
  document.getElementById('glCodeInput').value  = '';
  document.getElementById('glGroupInput').value = '';
  selectedGlCode  = null;
  selectedGroupId = null;
  editMode = false;
  editKey  = null;
}

/* ═══════════════════════════════════════════════════════════
   REFRESH — re-pull all data after a write
   ═══════════════════════════════════════════════════════════ */
async function refreshAll() {
  const [groups, mappings] = await Promise.all([
    apiClient.refGlGroups(),
    apiClient.list(),
  ]);
  glGroups   = groups;
  masterData = mappings;
  renderTable();
}

/* ═══════════════════════════════════════════════════════════
   RENDER — preserved from original, only field names adjusted
   (glCode → gl_code, glGroup → group_name)
   ═══════════════════════════════════════════════════════════ */
function renderTable() {
  const tbody = document.querySelector('#dataTable tbody');
  const search = document.getElementById('tableSearch').value.trim().toLowerCase();

  let rows = masterData.filter(r =>
    !search ||
    r.gl_code.toLowerCase().includes(search) ||
    (r.group_name || '').toLowerCase().includes(search)
  );

  if (sortCol) {
    rows.sort((a, b) => {
      const av = (a[sortCol] || '').toString();
      const bv = (b[sortCol] || '').toString();
      const cmp = av.localeCompare(bv);
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }

  tbody.innerHTML = rows.length === 0
    ? `<tr class="empty"><td colspan="3">
         <div class="empty-title">No mappings</div>
         <div class="empty-sub">เพิ่ม mapping แรกได้จากฟอร์มด้านบน</div>
       </td></tr>`
    : rows.map(r => `
        <tr ${r.gl_code === newRowKey ? 'class="row-new"' : ''}>
          <td><span class="badge-code">${escapeHtml(r.gl_code)}</span></td>
          <td><span class="badge-group">${escapeHtml(r.group_name || '—')}</span></td>
          <td class="action-col">
            <button class="btn-sm btn-edit" data-gl-code="${escapeAttr(r.gl_code)}">Edit</button>
            <button class="btn-sm btn-danger" data-gl-code="${escapeAttr(r.gl_code)}">Delete</button>
          </td>
        </tr>
      `).join('');

  document.getElementById('countActive').textContent  = masterData.length;
  document.getElementById('countGroups').textContent  = new Set(masterData.map(r => r.group_id)).size;

  setTimeout(() => { newRowKey = null; }, 2400);
}

function toggleSort(col) {
  if (sortCol !== col) { sortCol = col; sortDir = 'asc'; }
  else if (sortDir === 'asc') sortDir = 'desc';
  else { sortCol = null; sortDir = 'asc'; }
  document.querySelectorAll('.data-table thead th[data-col]').forEach(th => {
    th.removeAttribute('data-sort');
    if (th.dataset.col === sortCol) th.setAttribute('data-sort', sortDir);
  });
  renderTable();
}

/* ═══════════════════════════════════════════════════════════
   ERROR & SUCCESS UI — reuses modal markup from original HTML
   ═══════════════════════════════════════════════════════════ */
function showErrorModal(err) {
  const modal = document.getElementById('errorModal');
  if (!modal) { alert(err.message || String(err)); return; }

  const body = err.body || {};
  const title = body.code === 'DUPLICATE_KEY' ? 'ข้อมูลซ้ำ'
              : err.status === 403 ? 'ไม่มีสิทธิ์เข้าถึง'
              : err.status === 401 ? 'เซสชันหมดอายุ'
              : 'เกิดข้อผิดพลาด';

  modal.querySelector('.modal-title').textContent = title;
  modal.querySelector('.modal-body').textContent  =
    body.message_th || body.message_en || err.message || 'ไม่ทราบสาเหตุ';
  modal.querySelector('.modal-details').textContent = JSON.stringify(body, null, 2);
  modal.classList.add('show');
}

/* ═══════════════════════════════════════════════════════════
   EXPORT CSV — downloads all masterData as gl_group_mapping.csv
   ═══════════════════════════════════════════════════════════ */
function exportCsv() {
  if (!masterData.length) return;

  const rows = [
    ['GL Code', 'GL Group'],
    ...masterData.map(r => [r.gl_code, r.group_name || '']),
  ];

  const csv = rows.map(cols =>
    cols.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')
  ).join('\r\n');

  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `gl_group_mapping_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function closeNotice() {
  document.getElementById('noticeModal').classList.remove('show');
}

function closeErrorModal() {
  document.getElementById('errorModal').classList.remove('show');
}

function showSuccessToast(message) {
  const toast = document.getElementById('successToast');
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2000);
}

function showWarning(msg) {
  const input = document.getElementById('glCodeInput');
  input.classList.add('input-warning');
  setTimeout(() => input.classList.remove('input-warning'), 600);
}

/* ─── HTML-escape helpers (XSS prevention) ─── */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
  ));
}
function escapeAttr(s) {
  return String(s).replace(/['"\\]/g, c => '\\' + c);
}

/* ═══════════════════════════════════════════════════════════
   DROPDOWNS — filter + render lists for GL Code and GL Group
   ═══════════════════════════════════════════════════════════ */

function renderGlCodeList(query) {
  const list = document.getElementById('glCodeList');
  const drop = document.getElementById('glCodeDropdown');
  const q = query.toLowerCase();
  const hits = q ? sapGlCodes.filter(c => c.code.toLowerCase().includes(q)) : sapGlCodes;

  list.innerHTML = hits.length === 0
    ? `<div class="dropdown-empty">ไม่พบ GL Code ที่ตรงกัน</div>`
    : hits.map(c =>
        `<div class="dropdown-item" data-code="${escapeAttr(c.code)}">
           <span class="code">${escapeHtml(c.code)}</span>
         </div>`
      ).join('');
  drop.classList.add('open');
}

function selectGlCode(code) {
  document.getElementById('glCodeInput').value = code;
  selectedGlCode = code;
  document.getElementById('glCodeDropdown').classList.remove('open');
}

function renderGlGroupList(query) {
  const list = document.getElementById('glGroupList');
  const drop = document.getElementById('glGroupDropdown');
  const q = query.toLowerCase();
  const hits = q ? glGroups.filter(g => g.group_name.toLowerCase().includes(q)) : glGroups;

  const exactMatch = glGroups.some(g => g.group_name.toLowerCase() === q);
  const createNew = query && !exactMatch
    ? `<div class="dropdown-item create-new" data-create-name="${escapeAttr(query)}">
         สร้างกลุ่มใหม่: "${escapeHtml(query)}"
       </div>`
    : '';

  list.innerHTML = hits.map(g =>
    `<div class="dropdown-item" data-group-id="${escapeAttr(g.group_id)}" data-group-name="${escapeAttr(g.group_name)}">
       <span class="code">${escapeHtml(g.group_name)}</span>
     </div>`
  ).join('') + createNew || `<div class="dropdown-empty">ไม่มีกลุ่ม</div>`;
  drop.classList.add('open');
}

function selectGlGroup(groupId, groupName) {
  document.getElementById('glGroupInput').value = groupName;
  selectedGroupId = groupId;
  document.getElementById('glGroupDropdown').classList.remove('open');
}

function selectGlGroupNew(name) {
  document.getElementById('glGroupInput').value = name;
  selectedGroupId = null;
  document.getElementById('glGroupDropdown').classList.remove('open');
}

function initDropdowns() {
  const codeInput  = document.getElementById('glCodeInput');
  const groupInput = document.getElementById('glGroupInput');

  codeInput.addEventListener('input', () => renderGlCodeList(codeInput.value));
  codeInput.addEventListener('focus', () => renderGlCodeList(codeInput.value));

  groupInput.addEventListener('input', () => renderGlGroupList(groupInput.value));
  groupInput.addEventListener('focus', () => renderGlGroupList(groupInput.value));

  document.addEventListener('click', e => {
    if (!e.target.closest('#glCodeDropdown'))
      document.getElementById('glCodeDropdown').classList.remove('open');
    if (!e.target.closest('#glGroupDropdown'))
      document.getElementById('glGroupDropdown').classList.remove('open');
  });
}
