/* ═══════════════════════════════════════════════════════════
   gl-group.js — GL Group Master controller
   Wired to gl-group.html (new UI design).
   Element IDs used: glCodeInput, glGroupInput, glCodeDropdown,
   glGroupDropdown, glCodeList, glGroupList, tableBody, modeBadge,
   saveBtnLabel, countPill, tableSearch, confirmModal, confirmBtn,
   confirmSummary, noticeModal, noticeMsg, noticeSummary,
   stat-gl, stat-group, stat-unmapped, stat-sap.
   API layer: shared/api-client-gl-group.js (glApiClient)
   ═══════════════════════════════════════════════════════════ */

/* ── THEME ── */
function toggleTheme() {
  const next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('cm.theme', next); } catch (_) {}
}
window.toggleTheme = toggleTheme;

function applyThemeFromStorage() {
  const PRESETS = {
    chememan: { forest: '#00522C', mint: '#1FA378', gold: '#C9963D' },
    ocean:    { forest: '#0E4D6E', mint: '#37B5C7', gold: '#F2C661' },
    sunset:   { forest: '#7B2D26', mint: '#E07B4C', gold: '#F2B752' },
    midnight: { forest: '#1B244B', mint: '#5B73D9', gold: '#A88AE6' },
    nature:   { forest: '#2D5016', mint: '#7BA428', gold: '#B8A04A' },
    royal:    { forest: '#3D1F6E', mint: '#9B6DD9', gold: '#D6B16A' },
  };
  let theme = 'light', preset = 'ocean', intensity = 60;
  try {
    theme     = localStorage.getItem('cm.theme')       || 'light';
    preset    = localStorage.getItem('cm.preset')      || 'ocean';
    intensity = +(localStorage.getItem('cm.intensity') || 60);
  } catch (_) {}
  document.documentElement.setAttribute('data-theme', theme);

  const p = PRESETS[preset] || PRESETS.ocean;
  const adjust = (hex, factor) => {
    const h = hex.replace('#', '');
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    const mix   = c => factor >= 1 ? Math.round(c * (2 - factor)) : Math.round(c + (255 - c) * (1 - factor));
    const toHex = n => Math.max(0, Math.min(255, n)).toString(16).padStart(2, '0');
    return '#' + toHex(mix(r)) + toHex(mix(g)) + toHex(mix(b));
  };
  const f = intensity / 100;
  document.documentElement.style.setProperty('--accent',   adjust(p.forest, f));
  document.documentElement.style.setProperty('--accent-2', adjust(p.mint,   f));
  document.documentElement.style.setProperty('--accent-3', adjust(p.gold,   f));
}

/* ═══════════════════════════════════════════════════════════
   STATE
   ═══════════════════════════════════════════════════════════ */
let sapGlCodes  = [];   /* [{ code, name }]            — /reference/gl-codes */
let glGroupDims = [];   /* [{ group_id, group_name }]  — /reference/gl-groups */
let masterData  = [];   /* [{ gl_code, group_id, group_name }] — /list */

let editModeGlCode = null;   /* gl_code being edited, or null for new */
let pendingDelete  = null;   /* gl_code awaiting confirm modal */
let newRowKey      = null;   /* gl_code to highlight after save */
let sortCol        = null;   /* 'glCode' | 'glGroup' | null */
let sortDir        = 'asc';

/* ─── HTML escaping (XSS prevention) ─── */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

/* ═══════════════════════════════════════════════════════════
   INIT
   ═══════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
  applyThemeFromStorage();

  const ok = await checkAdminAccess();
  if (!ok) return;

  showTableLoading(true);
  try {
    const [glCodes, glGroups, mappings] = await Promise.all([
      glApiClient.refGlCodes(),
      glApiClient.refGlGroups(),
      glApiClient.list(),
    ]);
    sapGlCodes  = glCodes;
    glGroupDims = glGroups;
    masterData  = mappings;
  } catch (err) {
    showError(err);
  } finally {
    showTableLoading(false);
  }

  initGlCodeDropdown();
  initGlGroupDropdown();
  renderTable();

  /* Confirm-delete button */
  document.getElementById('confirmBtn').addEventListener('click', () => executeConfirmedDelete());

  /* Table body — event delegation for edit/delete buttons */
  document.getElementById('tableBody')?.addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    switch (btn.dataset.action) {
      case 'edit':   editRecord(btn.dataset.glCode);  break;
      case 'delete': askDelete(btn.dataset.glCode);   break;
    }
  });

  /* Close dropdowns when clicking outside */
  document.addEventListener('click', e => {
    const codeWrap  = document.getElementById('glCodeDropdown');
    const groupWrap = document.getElementById('glGroupDropdown');
    if (codeWrap  && !codeWrap.contains(e.target))  codeWrap.classList.remove('open');
    if (groupWrap && !groupWrap.contains(e.target)) groupWrap.classList.remove('open');
  });
});

/* ═══════════════════════════════════════════════════════════
   GL CODE DROPDOWN
   ═══════════════════════════════════════════════════════════ */
function initGlCodeDropdown() {
  const wrap  = document.getElementById('glCodeDropdown');
  const input = document.getElementById('glCodeInput');
  if (!wrap || !input) return;

  input.addEventListener('focus', () => { wrap.classList.add('open'); renderGlCodeList(''); });
  input.addEventListener('input', () => { wrap.classList.add('open'); renderGlCodeList(input.value); });
  input.addEventListener('blur',  () => setTimeout(() => wrap.classList.remove('open'), 150));

  /* Event delegation — mousedown so blur fires before click is lost */
  document.addEventListener('mousedown', e => {
    const item = e.target.closest('#glCodeList .dropdown-item[data-action="select-gl-code"]');
    if (!item) return;
    e.preventDefault();
    selectGlCode(item.dataset.code, item.dataset.name);
  });
}

function renderGlCodeList(filter) {
  const list = document.getElementById('glCodeList');
  if (!list) return;
  const q = (filter || '').toLowerCase();
  const filtered = sapGlCodes.filter(it =>
    it.code.toLowerCase().includes(q) || (it.name || '').toLowerCase().includes(q)
  );
  if (!filtered.length) {
    list.innerHTML = '<div class="dropdown-empty">ไม่พบ GL Code · No matches</div>';
    return;
  }
  list.innerHTML = filtered.map(it => `
    <div class="dropdown-item"
         data-action="select-gl-code"
         data-code="${escapeHtml(it.code)}"
         data-name="${escapeHtml(it.name || '')}">
      <span class="code">${escapeHtml(it.code)}</span>
      <span class="name">${escapeHtml(it.name || '')}</span>
    </div>
  `).join('');
}

function selectGlCode(code, name) {
  const input = document.getElementById('glCodeInput');
  if (input) input.value = code;
  document.getElementById('glCodeDropdown')?.classList.remove('open');

  /* Auto-fill GL Group if a mapping already exists for this code */
  const existing = masterData.find(d => d.gl_code === code);
  if (existing) {
    const groupInput = document.getElementById('glGroupInput');
    if (groupInput) {
      groupInput.value                    = existing.group_name || '';
      groupInput.dataset.selectedGroupId  = existing.group_id   || '';
    }
    setEditMode(code);
  } else {
    setEditMode(null);
  }
}
window.selectGlCode = selectGlCode;

/* ═══════════════════════════════════════════════════════════
   GL GROUP DROPDOWN
   ═══════════════════════════════════════════════════════════ */
function initGlGroupDropdown() {
  const wrap  = document.getElementById('glGroupDropdown');
  const input = document.getElementById('glGroupInput');
  if (!wrap || !input) return;

  input.addEventListener('focus', () => { wrap.classList.add('open'); renderGlGroupList(''); });
  input.addEventListener('input', () => { wrap.classList.add('open'); renderGlGroupList(input.value); });
  input.addEventListener('blur',  () => setTimeout(() => wrap.classList.remove('open'), 150));

  /* Event delegation */
  document.addEventListener('mousedown', e => {
    const item = e.target.closest('#glGroupList .dropdown-item[data-action]');
    if (!item) return;
    e.preventDefault();
    if (item.dataset.action === 'select-gl-group') {
      selectGlGroup(item.dataset.groupId, item.dataset.groupName);
    } else if (item.dataset.action === 'create-gl-group') {
      createNewGroup(item.dataset.name);
    }
  });
}

function renderGlGroupList(filter) {
  const list = document.getElementById('glGroupList');
  if (!list) return;
  const q = (filter || '').toLowerCase();

  /* Combine server dims + any locally known group names (already in masterData) */
  const knownNames = [...new Set([
    ...glGroupDims.map(d => d.group_name),
    ...masterData.map(d => d.group_name).filter(Boolean),
  ])].sort();

  const filtered = knownNames.filter(g => g.toLowerCase().includes(q));
  let html = '';

  if (filtered.length) {
    html += filtered.map(g => {
      const dim = glGroupDims.find(d => d.group_name === g);
      return `<div class="dropdown-item"
               data-action="select-gl-group"
               data-group-id="${escapeHtml(dim ? dim.group_id : '')}"
               data-group-name="${escapeHtml(g)}">
        <span class="code" style="font-family:var(--sans);font-weight:600;color:var(--ink)">${escapeHtml(g)}</span>
      </div>`;
    }).join('');
  } else if (!filter) {
    html = '<div class="dropdown-empty">ไม่มี GL Group · พิมพ์เพื่อสร้างใหม่</div>';
  }

  /* Offer "create new" when typed name does not exist */
  const trimmed = (filter || '').trim();
  if (trimmed && !knownNames.some(g => g.toLowerCase() === trimmed.toLowerCase())) {
    html += `<div class="dropdown-item create-new"
               data-action="create-gl-group"
               data-name="${escapeHtml(trimmed)}">
      <span>สร้างกลุ่มใหม่: <b>${escapeHtml(trimmed)}</b></span>
    </div>`;
  }

  list.innerHTML = html || '<div class="dropdown-empty">No options</div>';
}

function selectGlGroup(groupId, groupName) {
  const input = document.getElementById('glGroupInput');
  if (input) {
    input.value                    = groupName;
    input.dataset.selectedGroupId  = groupId || '';
  }
  document.getElementById('glGroupDropdown')?.classList.remove('open');
}
window.selectGlGroup = selectGlGroup;

function createNewGroup(name) {
  /* group_id intentionally empty — backend creates new dim via create_on_save path */
  selectGlGroup('', name);
}
window.createNewGroup = createNewGroup;

/* ═══════════════════════════════════════════════════════════
   MODE BADGE
   ═══════════════════════════════════════════════════════════ */
function setEditMode(glCode) {
  editModeGlCode = glCode;
  const badge = document.getElementById('modeBadge');
  const label = document.getElementById('saveBtnLabel');
  if (!badge || !label) return;
  if (glCode) {
    badge.textContent       = 'แก้ไข · UPDATE';
    badge.style.color       = 'var(--gl-group)';
    badge.style.borderColor = 'var(--gl-group)';
    label.textContent       = 'อัปเดต';
  } else {
    badge.textContent       = 'เพิ่มใหม่ · NEW';
    badge.style.color       = '';
    badge.style.borderColor = '';
    label.textContent       = 'บันทึก';
  }
}
window.setEditMode = setEditMode;

/* ═══════════════════════════════════════════════════════════
   SAVE (async — calls real API)
   ═══════════════════════════════════════════════════════════ */
async function saveRecord() {
  const glCode    = (document.getElementById('glCodeInput')?.value  || '').trim();
  const glGroup   = (document.getElementById('glGroupInput')?.value || '').trim();
  const groupIdEl = document.getElementById('glGroupInput');
  const groupId   = groupIdEl?.dataset.selectedGroupId || '';

  if (!glCode || !glGroup) {
    showNotice('โปรดกรอกข้อมูล', 'กรุณาเลือกทั้ง GL Code และ GL Group ก่อนบันทึก', null);
    return;
  }

  /* Validate GL Code is from SAP reference */
  const sapItem = sapGlCodes.find(s => s.code === glCode);
  if (!sapItem) {
    showNotice('GL Code ไม่ถูกต้อง', 'กรุณาเลือก GL Code จากรายการของ SAP เท่านั้น', null);
    return;
  }

  const isEdit  = !!editModeGlCode;
  const payload = groupId
    ? { gl_code: glCode, group_id: groupId }
    : { gl_code: glCode, group_name: glGroup };

  const saveBtn = document.querySelector('.btn-save');
  if (saveBtn) saveBtn.disabled = true;

  try {
    await glApiClient.save(payload, isEdit);
    newRowKey = glCode;
    await refreshAll();
    resetForm();
    showNotice(
      isEdit ? 'อัปเดตสำเร็จ' : 'บันทึกสำเร็จ',
      isEdit
        ? 'อัปเดต Mapping เรียบร้อย และย้ายขึ้นบนสุดของตาราง'
        : 'เพิ่ม Mapping ใหม่ที่บนสุดของตาราง',
      { action: isEdit ? 'UPDATE' : 'CREATE', glCode, glGroup, sapName: sapItem.name }
    );
  } catch (err) {
    if (saveBtn) saveBtn.disabled = false;
    if (err.status === 409) {
      showNotice(
        'ข้อมูลซ้ำ',
        err.body?.message_th || 'รหัส GL Code นี้มีอยู่ในระบบแล้ว กรุณา refresh แล้วลองใหม่',
        null
      );
    } else {
      showError(err);
    }
    return;
  }

  if (saveBtn) saveBtn.disabled = false;
}
window.saveRecord = saveRecord;

/* ═══════════════════════════════════════════════════════════
   EDIT — pre-fill form from table row click
   ═══════════════════════════════════════════════════════════ */
function editRecord(glCode) {
  const rec = masterData.find(d => d.gl_code === glCode);
  if (!rec) return;

  const codeInput  = document.getElementById('glCodeInput');
  const groupInput = document.getElementById('glGroupInput');
  if (codeInput)  codeInput.value = rec.gl_code;
  if (groupInput) {
    groupInput.value                   = rec.group_name || '';
    groupInput.dataset.selectedGroupId = rec.group_id   || '';
  }
  setEditMode(rec.gl_code);
  document.querySelector('.panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
window.editRecord = editRecord;

/* ═══════════════════════════════════════════════════════════
   DELETE
   ═══════════════════════════════════════════════════════════ */
function askDelete(glCode) {
  pendingDelete = glCode;
  const rec    = masterData.find(d => d.gl_code === glCode);
  const sap    = sapGlCodes.find(s => s.code === glCode);
  const sumEl  = document.getElementById('confirmSummary');
  if (sumEl) {
    sumEl.innerHTML = `
      <div class="row"><span class="lbl">GL Code</span><span class="gl-code-pill">${escapeHtml(glCode)}</span></div>
      <div class="row"><span class="lbl">SAP name</span><span style="color:var(--ink-2);font-size:12.5px">${escapeHtml(sap ? sap.name : '—')}</span></div>
      <div class="row"><span class="lbl">GL Group</span><span class="gl-group-pill">${escapeHtml(rec ? rec.group_name : '—')}</span></div>
    `;
  }
  document.getElementById('confirmModal')?.classList.add('open');
}
window.askDelete = askDelete;

async function executeConfirmedDelete() {
  if (!pendingDelete) return;
  const glCode = pendingDelete;
  closeConfirm();
  try {
    await glApiClient.remove({ gl_code: glCode });
    await refreshAll();
    showSuccessToast(`ลบ GL Code ${escapeHtml(glCode)} สำเร็จ`);
  } catch (err) {
    showError(err);
  }
}

function closeConfirm() {
  document.getElementById('confirmModal')?.classList.remove('open');
  pendingDelete = null;
}
window.closeConfirm = closeConfirm;

/* ═══════════════════════════════════════════════════════════
   SORT
   ═══════════════════════════════════════════════════════════ */
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
window.toggleSort = toggleSort;

/* ═══════════════════════════════════════════════════════════
   REFRESH + RESET
   ═══════════════════════════════════════════════════════════ */
async function refreshAll() {
  const [glGroups, mappings] = await Promise.all([
    glApiClient.refGlGroups(),
    glApiClient.list(),
  ]);
  glGroupDims = glGroups;
  masterData  = mappings;
  renderTable();
}

function resetForm() {
  const codeInput  = document.getElementById('glCodeInput');
  const groupInput = document.getElementById('glGroupInput');
  if (codeInput)  codeInput.value = '';
  if (groupInput) { groupInput.value = ''; groupInput.dataset.selectedGroupId = ''; }
  setEditMode(null);
}

/* ═══════════════════════════════════════════════════════════
   RENDER TABLE
   ═══════════════════════════════════════════════════════════ */
function renderSummary() {
  const totalGl      = masterData.length;
  const uniqueGroups = new Set(masterData.map(d => d.group_name)).size;
  const mappedCodes  = new Set(masterData.map(d => d.gl_code));
  const unmapped     = sapGlCodes.filter(s => !mappedCodes.has(s.code)).length;
  const sapTotal     = sapGlCodes.length;

  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set('stat-gl',       totalGl);
  set('stat-group',    uniqueGroups);
  set('stat-unmapped', unmapped);
  set('stat-sap',      sapTotal);
}

function renderTable() {
  renderSummary();

  const tbody = document.getElementById('tableBody');
  if (!tbody) return;

  const q = (document.getElementById('tableSearch')?.value || '').toLowerCase();
  let filtered = masterData.filter(d =>
    d.gl_code.toLowerCase().includes(q) ||
    (d.group_name || '').toLowerCase().includes(q)
  );

  if (sortCol) {
    const key = sortCol === 'glCode' ? 'gl_code' : 'group_name';
    const dir = sortDir === 'asc' ? 1 : -1;
    filtered = [...filtered].sort((a, b) => {
      const va = (a[key] || '').toLowerCase();
      const vb = (b[key] || '').toLowerCase();
      if (va < vb) return -1 * dir;
      if (va > vb) return  1 * dir;
      return 0;
    });
  }

  const countPill = document.getElementById('countPill');
  if (countPill) countPill.innerHTML = `<b>${filtered.length}</b> / ${masterData.length} records`;

  if (!filtered.length) {
    tbody.innerHTML = `<tr class="empty"><td colspan="3">
      <div class="empty-title">No matches.</div>
      <div class="empty-sub">Try clearing the search or add a new mapping above.</div>
    </td></tr>`;
    return;
  }

  /* Compute merge runs (consecutive identical group_name) */
  const rowToRun = new Array(filtered.length);
  let i = 0;
  while (i < filtered.length) {
    const g = filtered[i].group_name;
    let len = 1;
    while (i + len < filtered.length && filtered[i + len].group_name === g) len++;
    const run = { length: len, group: g };
    for (let k = 0; k < len; k++) rowToRun[i + k] = { run, posInRun: k };
    i += len;
  }

  tbody.innerHTML = filtered.map((d, rowIdx) => {
    const sap          = sapGlCodes.find(s => s.code === d.gl_code);
    const displayIdx   = String(rowIdx + 1).padStart(2, '0');
    const isNew        = d.gl_code === newRowKey;
    const info         = rowToRun[rowIdx];
    const isFirstOfRun = info.posInRun === 0;
    const isMerged     = info.run.length > 1;

    const codeCell = `<td>
      <div class="gl-code-cell">
        <span class="row-idx">${escapeHtml(displayIdx)}</span>
        <div class="code-block">
          <span class="gl-code-pill">${escapeHtml(d.gl_code)}</span>
          <span class="sap-name">${escapeHtml(sap ? sap.name : '—')}</span>
        </div>
      </div>
    </td>`;

    let groupCell = '';
    if (isFirstOfRun) {
      const safeName = escapeHtml(d.group_name || '—');
      if (isMerged) {
        groupCell = `<td rowspan="${info.run.length}" class="group-merged-cell">
          <div class="map-block" style="position:relative">
            <span class="map-arrow" aria-hidden="true">
              <svg viewBox="0 0 24 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 7h17" stroke-dasharray="2 3"/>
                <path d="M16 2l5 5-5 5"/>
              </svg>
            </span>
            <span class="merged-wrap">
              <span class="gl-group-pill merged">
                <span class="count-tag">${info.run.length}× MERGED</span>
                <span class="group-name">${safeName}</span>
              </span>
              <span class="drop drop-1"></span>
              <span class="drop drop-2"></span>
              <span class="drop drop-3"></span>
              <span class="merged-shadow"></span>
            </span>
          </div>
        </td>`;
      } else {
        groupCell = `<td>
          <div class="map-block">
            <span class="map-arrow" aria-hidden="true">
              <svg viewBox="0 0 24 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 7h17" stroke-dasharray="2 3"/>
                <path d="M16 2l5 5-5 5"/>
              </svg>
            </span>
            <div class="group-block">
              <span class="gl-group-pill">${safeName}</span>
            </div>
          </div>
        </td>`;
      }
    }

    /* data-* attributes only — no inline onclick */
    const actionsCell = `<td>
      <div class="action-row">
        <button class="action-btn edit"
                data-action="edit"
                data-gl-code="${escapeHtml(d.gl_code)}"
                title="แก้ไข">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
        </button>
        <button class="action-btn delete"
                data-action="delete"
                data-gl-code="${escapeHtml(d.gl_code)}"
                title="ลบ">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </div>
    </td>`;

    return `<tr class="${isNew ? 'row-new' : ''}">${codeCell}${groupCell}${actionsCell}</tr>`;
  }).join('');

  setTimeout(() => { newRowKey = null; }, 2500);
}
window.renderTable = renderTable;

/* ═══════════════════════════════════════════════════════════
   EXPORT CSV — filtered rows, UTF-8 BOM, Thai-safe
   ═══════════════════════════════════════════════════════════ */
function exportCsv() {
  const q = (document.getElementById('tableSearch')?.value || '').toLowerCase();
  const rows = masterData.filter(d =>
    d.gl_code.toLowerCase().includes(q) ||
    (d.group_name || '').toLowerCase().includes(q)
  );

  const header = ['GL Code', 'SAP Name', 'GL Group'];
  const lines  = [header.join(',')];

  rows.forEach(d => {
    const sap  = sapGlCodes.find(s => s.code === d.gl_code);
    const cell = v => `"${String(v).replace(/"/g, '""')}"`;
    lines.push([cell(d.gl_code), cell(sap ? sap.name : ''), cell(d.group_name || '')].join(','));
  });

  /* UTF-8 BOM ensures Excel opens Thai text correctly */
  const bom  = '﻿';
  const blob = new Blob([bom + lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `gl-group-mapping-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
window.exportCsv = exportCsv;

/* ═══════════════════════════════════════════════════════════
   NOTICE / ERROR UI HELPERS
   ═══════════════════════════════════════════════════════════ */
function showNotice(title, body, summary) {
  const titleEl = document.querySelector('#noticeModal .modal-title');
  if (titleEl) {
    const safeTitle = escapeHtml(title);
    titleEl.innerHTML = title.includes('สำเร็จ')
      ? safeTitle.replace('สำเร็จ', '<em>สำเร็จ</em>')
      : safeTitle;
  }
  const msgEl = document.getElementById('noticeMsg');
  if (msgEl) msgEl.textContent = body;

  const sumEl = document.getElementById('noticeSummary');
  if (sumEl) {
    if (summary) {
      sumEl.style.display = 'flex';
      sumEl.innerHTML = `
        <div class="row"><span class="lbl">Action</span><span style="font-family:var(--mono);font-weight:600;color:var(--accent)">${escapeHtml(summary.action)}</span></div>
        <div class="row"><span class="lbl">GL Code</span><span class="gl-code-pill">${escapeHtml(summary.glCode)}</span></div>
        <div class="row"><span class="lbl">SAP name</span><span style="color:var(--ink-2);font-size:12.5px">${escapeHtml(summary.sapName || '—')}</span></div>
        <div class="row"><span class="lbl">GL Group</span><span class="gl-group-pill">${escapeHtml(summary.glGroup)}</span></div>
      `;
    } else {
      sumEl.style.display = 'none';
    }
  }
  document.getElementById('noticeModal')?.classList.add('open');
}
window.showNotice = showNotice;

function closeNotice() {
  document.getElementById('noticeModal')?.classList.remove('open');
}
window.closeNotice = closeNotice;

function showSuccessToast(message) {
  const titleEl = document.querySelector('#noticeModal .modal-title');
  const msgEl   = document.getElementById('noticeMsg');
  const sumEl   = document.getElementById('noticeSummary');
  if (titleEl) titleEl.innerHTML = 'สำเร็จ';
  if (msgEl)   msgEl.textContent = message;
  if (sumEl)   sumEl.style.display = 'none';
  document.getElementById('noticeModal')?.classList.add('open');
}

function showError(err) {
  const body   = err?.body || {};
  const title  = body.code === 'DUPLICATE_KEY' ? 'ข้อมูลซ้ำ'
               : err?.status === 403            ? 'ไม่มีสิทธิ์เข้าถึง'
               : err?.status === 401            ? 'เซสชันหมดอายุ'
               : 'เกิดข้อผิดพลาด';
  const detail = body.message_th || body.message_en || err?.message || 'ไม่ทราบสาเหตุ';

  const titleEl = document.querySelector('#noticeModal .modal-title');
  const msgEl   = document.getElementById('noticeMsg');
  const sumEl   = document.getElementById('noticeSummary');
  if (titleEl) titleEl.innerHTML = `<span style="color:#C25A3F">${escapeHtml(title)}</span>`;
  if (msgEl)   msgEl.textContent = detail;
  if (sumEl)   sumEl.style.display = 'none';
  document.getElementById('noticeModal')?.classList.add('open');
}

/* ═══════════════════════════════════════════════════════════
   LOADING STATE
   ═══════════════════════════════════════════════════════════ */
function showTableLoading(on) {
  const tbody = document.getElementById('tableBody');
  if (!tbody) return;
  if (on) {
    tbody.innerHTML = `<tr class="empty"><td colspan="3">
      <div class="empty-title">Loading…</div>
    </td></tr>`;
  }
}
