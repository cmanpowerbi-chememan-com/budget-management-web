/* ═══════════════════════════════════════════════════════════
   0007-orgcode-costcenter.js
   Junction table (cost_center, orgcode) — composite PK.
   No edit mode: a pair either exists or doesn't.
   ═══════════════════════════════════════════════════════════ */

/* ── THEME ── */
function toggleTheme() {
  const next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('cm.theme', next); } catch (_) {}
}
function applyThemeFromStorage() {
  try {
    const theme = localStorage.getItem('cm.theme') || 'light';
    document.documentElement.setAttribute('data-theme', theme);
  } catch (_) {}
}

/* ═══════════════════════════════════════════════════════════
   STATE
   ═══════════════════════════════════════════════════════════ */
let sapOrgcodes    = [];   // [{ code, name }] — from /reference/orgcodes
let sapCostCenters = [];   // [{ code, name }] — from /reference/cost-centers
let masterData     = [];   // [{ id, cost_center, orgcode, orgcode_name }]

/* Form state */
let selectedCCs    = [];   // [{ code, name }] — multi-selected cost centers
let selectedOrgcode = null; // { code, name } | null — single orgcode

/* UI state */
let pendingDelete = null;  // { cost_center, orgcode } | { kind, key } | { kind, cc, org }
let newRowKey     = null;  // "cost_center::orgcode" for highlight
let viewMode      = 'cc';  // 'cc' | 'org'

/* ═══════════════════════════════════════════════════════════
   INIT
   ═══════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
  applyThemeFromStorage();

  const ok = await checkAdminAccess();
  if (!ok) return;

  showLoading(true);
  try {
    const [orgcodes, costCenters, mappings] = await Promise.all([
      occApiClient.refOrgcodes(),
      occApiClient.refCostCenters(),
      occApiClient.list(),
    ]);
    sapOrgcodes    = orgcodes;
    sapCostCenters = costCenters;
    masterData     = mappings;
  } catch (err) {
    showError(err);
  } finally {
    showLoading(false);
  }

  initCostCenterDropdown();
  initOrgcodeDropdown();
  renderTable();

  /* Wire up confirm-delete button */
  document.getElementById('confirmBtn').onclick = () => executeConfirmedDelete();

  /* Close dropdowns on outside click */
  document.addEventListener('click', (e) => {
    const ccWrap  = document.getElementById('ccDropdown');
    const orgWrap = document.getElementById('glGroupDropdown');
    if (ccWrap  && !ccWrap.contains(e.target))  ccWrap.classList.remove('open');
    if (orgWrap && !orgWrap.contains(e.target)) orgWrap.classList.remove('open');
  });
});

function showLoading(on) {
  const grid = document.getElementById('chipGrid');
  if (!grid) return;
  if (on) {
    grid.innerHTML = `<div class="chip-empty"><div class="empty-title">Loading…</div></div>`;
  }
}

/* ═══════════════════════════════════════════════════════════
   COST CENTER MULTI-SELECT DROPDOWN
   ═══════════════════════════════════════════════════════════ */
function initCostCenterDropdown() {
  const wrap  = document.getElementById('ccDropdown');
  const input = document.getElementById('ccSearchInput');
  if (!wrap || !input) return;

  input.addEventListener('focus', () => { wrap.classList.add('open'); renderCCList(''); });
  input.addEventListener('input', () => { wrap.classList.add('open'); renderCCList(input.value); });
  input.addEventListener('blur',  () => setTimeout(() => wrap.classList.remove('open'), 160));
}

function renderCCList(filter) {
  const list = document.getElementById('ccDropdownList');
  if (!list) return;
  const q = filter.toLowerCase();
  const already = new Set(selectedCCs.map(s => s.code));
  const filtered = sapCostCenters.filter(it =>
    !already.has(it.code) &&
    (it.code.toLowerCase().includes(q) || (it.name || '').toLowerCase().includes(q))
  );
  if (!filtered.length) {
    list.innerHTML = '<div class="dropdown-empty">ไม่พบ Cost Center</div>';
    return;
  }
  list.innerHTML = filtered.map(it => `
    <div class="dropdown-item"
         data-action="select-cc"
         data-code="${escapeHtml(it.code)}"
         data-name="${escapeHtml(it.name || '')}">
      <span class="code">${escapeHtml(it.code)}</span>
      <span class="name">${escapeHtml(it.name || '')}</span>
    </div>
  `).join('');
}

function selectCC(code, name) {
  if (selectedCCs.some(s => s.code === code)) return;
  selectedCCs.push({ code, name });
  renderCCChips();
  const input = document.getElementById('ccSearchInput');
  if (input) { input.value = ''; }
  renderCCList('');
}
window.selectCC = selectCC;

function removeCC(code) {
  selectedCCs = selectedCCs.filter(s => s.code !== code);
  renderCCChips();
  renderCCList(document.getElementById('ccSearchInput')?.value || '');
}
window.removeCC = removeCC;

function renderCCChips() {
  const container = document.getElementById('ccChips');
  if (!container) return;
  if (!selectedCCs.length) {
    container.innerHTML = '';
    return;
  }
  container.innerHTML = selectedCCs.map(s => `
    <span class="chip-tag cc" style="cursor:default">
      <span>${escapeHtml(s.code)}</span>
      <svg class="x-icon" style="opacity:1;cursor:pointer"
           data-action="remove-cc" data-code="${escapeHtml(s.code)}"
           viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <line x1="18" x2="6" y1="6" y2="18"/><line x1="6" x2="18" y1="6" y2="18"/>
      </svg>
    </span>
  `).join('');
}

/* ═══════════════════════════════════════════════════════════
   ORGCODE SINGLE-SELECT DROPDOWN
   ═══════════════════════════════════════════════════════════ */
function initOrgcodeDropdown() {
  const wrap  = document.getElementById('glGroupDropdown');
  const input = document.getElementById('glGroupInput');
  if (!wrap || !input) return;

  input.addEventListener('focus', () => { wrap.classList.add('open'); renderOrgcodeList(''); });
  input.addEventListener('input', () => { wrap.classList.add('open'); renderOrgcodeList(input.value); });
  input.addEventListener('blur',  () => setTimeout(() => wrap.classList.remove('open'), 160));
}

function renderOrgcodeList(filter) {
  const list = document.getElementById('glGroupList');
  if (!list) return;
  const q = filter.toLowerCase();
  const filtered = sapOrgcodes.filter(it =>
    it.code.toLowerCase().includes(q) || (it.name || '').toLowerCase().includes(q)
  );
  if (!filtered.length) {
    list.innerHTML = '<div class="dropdown-empty">ไม่พบ Orgcode</div>';
    return;
  }
  list.innerHTML = filtered.map(it => `
    <div class="dropdown-item"
         data-action="select-org"
         data-code="${escapeHtml(it.code)}"
         data-name="${escapeHtml(it.name || '')}">
      <span class="code">${escapeHtml(it.code)}</span>
      <span class="name">${escapeHtml(it.name || '')}</span>
    </div>
  `).join('');
}

function selectOrgcode(code, name) {
  selectedOrgcode = { code, name };
  const input = document.getElementById('glGroupInput');
  if (input) input.value = code;
  document.getElementById('glGroupDropdown')?.classList.remove('open');
}
window.selectOrgcode = selectOrgcode;

/* ═══════════════════════════════════════════════════════════
   SAVE — POST one request per selected CC
   ═══════════════════════════════════════════════════════════ */
async function saveRecord() {
  if (!selectedCCs.length) {
    flashWarning('กรุณาเลือก Cost Center อย่างน้อย 1 รายการ');
    return;
  }
  if (!selectedOrgcode) {
    flashWarning('กรุณาเลือก Orgcode');
    return;
  }

  /* Frontend duplicate check */
  const dupes = selectedCCs.filter(cc =>
    masterData.some(r => r.cost_center === cc.code && r.orgcode === selectedOrgcode.code)
  );
  if (dupes.length) {
    showError({
      status: 409,
      body: {
        code: 'DUPLICATE_KEY',
        message_th: `คู่ (${dupes.map(d => d.code).join(', ')}, ${selectedOrgcode.code}) มีอยู่แล้ว`,
      },
    });
    return;
  }

  const btn = document.querySelector('.btn-save');
  if (btn) btn.disabled = true;

  const results = await Promise.allSettled(
    selectedCCs.map(cc => occApiClient.save({ cost_center: cc.code, orgcode: selectedOrgcode.code }))
  );

  if (btn) btn.disabled = false;

  const saved   = results.filter(r => r.status === 'fulfilled');
  const failed  = results.filter(r => r.status === 'rejected');

  const savedOrgCode = selectedOrgcode.code;

  if (saved.length > 0) {
    /* Find the last fulfilled result by scanning allSettled results in reverse.
       Using saved.length-1 as a positional index into selectedCCs is wrong
       when earlier requests fail and shift the fulfilled subset's position. */
    const lastFulfilledIdx = results.findLastIndex(r => r.status === 'fulfilled');
    const lastCC = selectedCCs[lastFulfilledIdx];
    if (lastCC) newRowKey = `${lastCC.code}::${selectedOrgcode.code}`;
    await refreshAll();
    resetForm();
  }

  if (failed.length === 0) {
    showSuccessNotice(saved.length, savedOrgCode);
  } else {
    const errMsgs = failed.map(r => r.reason?.message || 'ไม่ทราบสาเหตุ').join('\n');
    showError({ status: 500, body: { message_th: `บันทึกไม่ครบ: ${saved.length}/${results.length} สำเร็จ\n${errMsgs}` } });
  }
}
window.saveRecord = saveRecord;

/* ═══════════════════════════════════════════════════════════
   DELETE — single edge, whole CC, whole Orgcode
   ═══════════════════════════════════════════════════════════ */
function removeEdge(cc, org) {
  pendingDelete = { kind: 'pair', cc, org };
  const sap = sapOrgcodes.find(s => s.code === org);
  document.getElementById('confirmSummary').innerHTML = `
    <div class="row"><span class="lbl">Cost Center</span><span class="gl-code-pill">${escapeHtml(cc)}</span></div>
    <div class="row"><span class="lbl">Orgcode</span><span class="gl-group-pill">${escapeHtml(org)}</span></div>
    <div class="row"><span class="lbl">หน่วยงาน</span><span style="color:var(--ink-2);font-size:12.5px">${escapeHtml(sap?.name || '—')}</span></div>
  `;
  document.getElementById('confirmModal').classList.add('open');
}
window.removeEdge = removeEdge;

function deleteCC(cc) {
  const rows = masterData.filter(r => r.cost_center === cc);
  pendingDelete = { kind: 'cc', key: cc, rows };
  document.getElementById('confirmSummary').innerHTML = `
    <div class="row"><span class="lbl">Cost Center</span><span class="gl-code-pill">${escapeHtml(cc)}</span></div>
    <div class="row"><span class="lbl">Mappings ที่จะถูกลบ</span><span style="font-family:var(--mono);font-weight:700;color:#C25A3F">${rows.length} รายการ</span></div>
  `;
  document.getElementById('confirmModal').classList.add('open');
}
window.deleteCC = deleteCC;

function deleteOrg(org) {
  const rows = masterData.filter(r => r.orgcode === org);
  const sap  = sapOrgcodes.find(s => s.code === org);
  pendingDelete = { kind: 'org', key: org, rows };
  document.getElementById('confirmSummary').innerHTML = `
    <div class="row"><span class="lbl">Orgcode</span><span class="gl-group-pill">${escapeHtml(org)}</span></div>
    <div class="row"><span class="lbl">หน่วยงาน</span><span style="color:var(--ink-2);font-size:12.5px">${escapeHtml(sap?.name || '—')}</span></div>
    <div class="row"><span class="lbl">Mappings ที่จะถูกลบ</span><span style="font-family:var(--mono);font-weight:700;color:#C25A3F">${rows.length} รายการ</span></div>
  `;
  document.getElementById('confirmModal').classList.add('open');
}
window.deleteOrg = deleteOrg;

function editCC(cc) {
  /* Pre-fill the CC into the multi-select */
  const item = sapCostCenters.find(s => s.code === cc);
  selectedCCs = item ? [{ code: item.code, name: item.name || '' }] : [{ code: cc, name: '' }];
  selectedOrgcode = null;
  renderCCChips();
  const orgInput = document.getElementById('glGroupInput');
  if (orgInput) { orgInput.value = ''; orgInput.focus(); }
  document.querySelector('.panel-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
window.editCC = editCC;

function editOrg(org) {
  const item = sapOrgcodes.find(s => s.code === org);
  selectedOrgcode = item ? { code: item.code, name: item.name || '' } : { code: org, name: '' };
  selectedCCs = [];
  renderCCChips();
  const orgInput = document.getElementById('glGroupInput');
  if (orgInput) orgInput.value = org;
  document.getElementById('ccSearchInput')?.focus();
  document.querySelector('.panel-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
window.editOrg = editOrg;

async function executeConfirmedDelete() {
  if (!pendingDelete) return;

  let pairs = [];
  const pd  = pendingDelete;
  if (pd.kind === 'pair') {
    pairs = [{ cost_center: pd.cc, orgcode: pd.org }];
  } else if (pd.kind === 'cc') {
    pairs = pd.rows.map(r => ({ cost_center: r.cost_center, orgcode: r.orgcode }));
  } else if (pd.kind === 'org') {
    pairs = pd.rows.map(r => ({ cost_center: r.cost_center, orgcode: r.orgcode }));
  }

  closeConfirm();
  try {
    await Promise.all(pairs.map(p => occApiClient.remove(p)));
    await refreshAll();
    showSuccessToast(`ลบ ${pairs.length} mapping สำเร็จ`);
  } catch (err) {
    showError(err);
  }
}

function closeConfirm() {
  document.getElementById('confirmModal')?.classList.remove('open');
  pendingDelete = null;
}
window.closeConfirm = closeConfirm;

function resetForm() {
  selectedCCs     = [];
  selectedOrgcode = null;
  renderCCChips();
  const orgInput = document.getElementById('glGroupInput');
  if (orgInput) orgInput.value = '';
  const ccInput = document.getElementById('ccSearchInput');
  if (ccInput) ccInput.value = '';
}

async function refreshAll() {
  masterData = await occApiClient.list();
  renderTable();
}

/* ═══════════════════════════════════════════════════════════
   RENDER
   ═══════════════════════════════════════════════════════════ */
function setViewMode(m) {
  viewMode = m;
  document.querySelectorAll('.view-switch button').forEach(b =>
    b.classList.toggle('active', b.dataset.mode === m)
  );
  renderTable();
}
window.setViewMode   = setViewMode;
window.renderTable   = renderTable;

function renderTable() {
  renderSummary();
  const q = (document.getElementById('tableSearch')?.value || '').toLowerCase();
  const filtered = masterData.filter(r =>
    r.cost_center.toLowerCase().includes(q) ||
    r.orgcode.toLowerCase().includes(q) ||
    (r.orgcode_name || '').toLowerCase().includes(q)
  );

  document.getElementById('countPill').innerHTML = `<b>${filtered.length}</b> / ${masterData.length} mappings`;

  const ccMap  = new Map();
  const orgMap = new Map();
  filtered.forEach(r => {
    if (!ccMap.has(r.cost_center))  ccMap.set(r.cost_center,  []);
    if (!orgMap.has(r.orgcode))     orgMap.set(r.orgcode, []);
    ccMap.get(r.cost_center).push(r.orgcode);
    orgMap.get(r.orgcode).push(r.cost_center);
  });

  document.getElementById('legend-cc').textContent    = ccMap.size;
  document.getElementById('legend-org').textContent   = orgMap.size;
  document.getElementById('legend-edges').textContent = filtered.length;

  const grid = document.getElementById('chipGrid');
  if (!filtered.length) {
    grid.innerHTML = `<div class="chip-empty">
      <div class="empty-title">No mappings.</div>
      <div class="empty-sub">เพิ่ม mapping คู่แรกได้จากฟอร์มด้านบน</div>
    </div>`;
    return;
  }

  let html = '';
  if (viewMode === 'cc') {
    const keys = [...ccMap.keys()].sort();
    html = keys.map(cc => {
      const orgs  = [...new Set(ccMap.get(cc))].sort();
      const multi = orgs.length > 1;
      const isNew = `${cc}::${orgs[0]}` === newRowKey;
      return `<div class="chip-card ${multi ? 'has-multi' : ''} ${isNew ? 'row-new' : ''}" data-key="${cc}" data-kind="cc">
        <div class="chip-card-head">
          <div class="primary">
            <div class="pill-line">
              <span class="gl-code-pill">${escapeHtml(cc)}</span>
              <span class="deg">×${orgs.length}</span>
            </div>
          </div>
          <div class="card-actions">
            <button class="action-btn edit" data-action="edit-cc" data-cc="${escapeHtml(cc)}" title="เพิ่ม mapping ใหม่สำหรับ CC นี้">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button class="action-btn delete" data-action="delete-cc" data-cc="${escapeHtml(cc)}" title="ลบทุก mapping ของ CC นี้">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </div>
        </div>
        <div class="chip-card-arrow">maps to ${orgs.length} orgcode${orgs.length > 1 ? 's' : ''}</div>
        <div class="chip-card-body">
          ${orgs.map(o => {
            const sap = sapOrgcodes.find(s => s.code === o);
            return `<span class="chip-tag org" data-action="remove-edge" data-cc="${escapeHtml(cc)}" data-org="${escapeHtml(o)}" title="คลิกเพื่อลบ mapping นี้" style="cursor:pointer">
              <span>${escapeHtml(o)}</span>
              <span class="org-name">${escapeHtml(sap?.name || '')}</span>
              <svg class="x-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" x2="6" y1="6" y2="18"/><line x1="6" x2="18" y1="6" y2="18"/></svg>
            </span>`;
          }).join('')}
        </div>
      </div>`;
    }).join('');
  } else {
    const keys = [...orgMap.keys()].sort();
    html = keys.map(org => {
      const ccs   = [...new Set(orgMap.get(org))].sort();
      const multi = ccs.length > 1;
      const sap   = sapOrgcodes.find(s => s.code === org);
      return `<div class="chip-card ${multi ? 'has-multi' : ''}" data-key="${org}" data-kind="org">
        <div class="chip-card-head">
          <div class="primary">
            <div class="pill-line">
              <span class="gl-group-pill">${escapeHtml(org)}</span>
              <span class="deg">×${ccs.length}</span>
            </div>
            <span class="name">${escapeHtml(sap?.name || '—')}</span>
          </div>
          <div class="card-actions">
            <button class="action-btn edit" data-action="edit-org" data-org="${escapeHtml(org)}" title="เพิ่ม mapping ใหม่สำหรับ Orgcode นี้">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button class="action-btn delete" data-action="delete-org" data-org="${escapeHtml(org)}" title="ลบทุก mapping ของ Orgcode นี้">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </div>
        </div>
        <div class="chip-card-arrow">contains ${ccs.length} cost center${ccs.length > 1 ? 's' : ''}</div>
        <div class="chip-card-body">
          ${ccs.map(c => `<span class="chip-tag cc" data-action="remove-edge" data-cc="${escapeHtml(c)}" data-org="${escapeHtml(org)}" title="คลิกเพื่อลบ mapping นี้" style="cursor:pointer">
            <span>${escapeHtml(c)}</span>
            <svg class="x-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" x2="6" y1="6" y2="18"/><line x1="6" x2="18" y1="6" y2="18"/></svg>
          </span>`).join('')}
        </div>
      </div>`;
    }).join('');
  }

  grid.innerHTML = html;
  setTimeout(() => { newRowKey = null; }, 2500);
}

function renderSummary() {
  const mappedOrgs = new Set(masterData.map(r => r.orgcode));
  const unmapped   = sapOrgcodes.filter(s => !mappedOrgs.has(s.code)).length;
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set('stat-gl',       new Set(masterData.map(r => r.cost_center)).size);
  set('stat-group',    mappedOrgs.size);
  set('stat-unmapped', unmapped);
  set('stat-sap',      sapOrgcodes.length);
}

/* ═══════════════════════════════════════════════════════════
   UI HELPERS
   ═══════════════════════════════════════════════════════════ */
function showSuccessNotice(count, orgcode) {
  const title  = document.querySelector('#noticeModal .modal-title');
  const msg    = document.getElementById('noticeMsg');
  const sumEl  = document.getElementById('noticeSummary');
  if (title) title.innerHTML = 'บันทึก<em>สำเร็จ</em>';
  if (msg)   msg.textContent = `เพิ่ม ${count} mapping สำเร็จ`;
  if (sumEl) {
    sumEl.style.display = 'flex';
    sumEl.innerHTML = `<div class="row"><span class="lbl">Orgcode</span><span class="gl-group-pill">${escapeHtml(orgcode)}</span></div>
      <div class="row"><span class="lbl">Cost Centers</span><span style="font-family:var(--mono);font-weight:700;color:var(--gl-code)">${count} รายการ</span></div>`;
  }
  document.getElementById('noticeModal')?.classList.add('open');
}

function closeNotice() {
  document.getElementById('noticeModal')?.classList.remove('open');
}
window.closeNotice = closeNotice;

function showSuccessToast(message) {
  /* Fallback: reuse notice modal as toast when no toast element exists */
  const title = document.querySelector('#noticeModal .modal-title');
  const msg   = document.getElementById('noticeMsg');
  const sumEl = document.getElementById('noticeSummary');
  if (title) title.innerHTML = 'สำเร็จ';
  if (msg)   msg.textContent = message;
  if (sumEl) sumEl.style.display = 'none';
  document.getElementById('noticeModal')?.classList.add('open');
}

function showError(err) {
  const body  = err?.body || {};
  const title = body.code === 'DUPLICATE_KEY'  ? 'ข้อมูลซ้ำ'
              : err?.status === 403            ? 'ไม่มีสิทธิ์เข้าถึง'
              : err?.status === 401            ? 'เซสชันหมดอายุ'
              : 'เกิดข้อผิดพลาด';
  const detail = body.message_th || body.message_en || err?.message || 'ไม่ทราบสาเหตุ';

  const modal = document.querySelector('#noticeModal .modal-title');
  const msg   = document.getElementById('noticeMsg');
  const sumEl = document.getElementById('noticeSummary');
  if (modal) modal.innerHTML = `<span style="color:#C25A3F">${escapeHtml(title)}</span>`;
  if (msg)   msg.textContent = detail;
  if (sumEl) sumEl.style.display = 'none';
  document.getElementById('noticeModal')?.classList.add('open');
}

function flashWarning(hint) {
  const wrap = document.getElementById('ccDropdown') || document.getElementById('glGroupDropdown');
  if (!wrap) return;
  const input = wrap.querySelector('input');
  if (!input) return;
  input.style.borderColor  = '#C25A3F';
  input.style.boxShadow    = '0 0 0 3px color-mix(in oklab, #C25A3F 18%, transparent)';
  clearTimeout(input._errTimer);
  input._errTimer = setTimeout(() => { input.style.borderColor = ''; input.style.boxShadow = ''; }, 700);
}

/* ─── HTML escape helpers ─── */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}
/** @deprecated Use data-* attributes + event delegation instead of inline onclick */
function esc(s) {
  return String(s).replace(/['\\]/g, c => '\\' + c);
}

/* ─── Event delegation — single listener handles all dynamic buttons ─── */
document.addEventListener('DOMContentLoaded', () => {
  /* CC dropdown list */
  document.addEventListener('mousedown', e => {
    const item = e.target.closest('#ccDropdownList .dropdown-item[data-action]');
    if (!item) return;
    if (item.dataset.action === 'select-cc') {
      e.preventDefault();
      selectCC(item.dataset.code, item.dataset.name);
    }
  });

  /* Orgcode dropdown list */
  document.addEventListener('mousedown', e => {
    const item = e.target.closest('#glGroupList .dropdown-item[data-action]');
    if (!item) return;
    if (item.dataset.action === 'select-org') {
      e.preventDefault();
      selectOrgcode(item.dataset.code, item.dataset.name);
    }
  });

  /* Selected CC chips (form area) — remove-cc action */
  document.getElementById('ccChips')?.addEventListener('click', e => {
    const btn = e.target.closest('[data-action="remove-cc"]');
    if (btn) removeCC(btn.dataset.code);
  });

  /* Chip grid — card actions + chip tags */
  document.getElementById('chipGrid')?.addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    switch (btn.dataset.action) {
      case 'edit-cc':     editCC(btn.dataset.cc);                       break;
      case 'delete-cc':   deleteCC(btn.dataset.cc);                     break;
      case 'remove-edge': removeEdge(btn.dataset.cc, btn.dataset.org);  break;
      case 'edit-org':    editOrg(btn.dataset.org);                     break;
      case 'delete-org':  deleteOrg(btn.dataset.org);                   break;
    }
  });
});
