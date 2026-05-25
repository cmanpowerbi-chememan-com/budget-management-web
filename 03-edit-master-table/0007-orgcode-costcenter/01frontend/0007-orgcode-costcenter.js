/* ═══════════════════════════════════════════════════════════
   0007-orgcode-costcenter.js — Modified application logic
   Replaces the inline <script> section of the original HTML.

   Junction table — composite PK on (cost_center, orgcode).
   No "edit" mode: pair either exists or doesn't.
   ═══════════════════════════════════════════════════════════ */

/* ── THEME (preserved from original) ── */
function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme');
  document.documentElement.setAttribute('data-theme', cur === 'light' ? 'dark' : 'light');
}
function applyThemeFromStorage() {
  const theme = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', theme);
}

/* ═══════════════════════════════════════════════════════════
   DATA — loaded from API at page init
   ═══════════════════════════════════════════════════════════ */
let sapOrgcodes = [];   // [{code, name}, ...]
let masterData  = [];   // [{cost_center, orgcode, orgcode_name}, ...]

/* UI state */
let pendingDelete = null;     // { cost_center, orgcode }
let newRowKey     = null;     // composite key for highlight: "cost_center::orgcode"

/* ═══════════════════════════════════════════════════════════
   INIT
   ═══════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
  applyThemeFromStorage();
  const ok = await checkAdminAccess();
  if (!ok) return;

  try {
    const [orgcodes, mappings] = await Promise.all([
      apiClient.refOrgcodes(),
      apiClient.list(),
    ]);
    sapOrgcodes = orgcodes;
    masterData  = mappings;
    renderTable();
    renderLegend();
  } catch (err) {
    showErrorModal(err);
  }
});

/* ═══════════════════════════════════════════════════════════
   INPUT VALIDATION — matches HTML regex /[^0-9A-Za-z]/g + upper
   ═══════════════════════════════════════════════════════════ */
function validateCostCenterInput(inputEl) {
  const raw = inputEl.value;
  const cleaned = raw.replace(/[^0-9A-Za-z]/g, '').toUpperCase();
  if (cleaned !== raw) {
    inputEl.value = cleaned;
    // Flash red border per original HTML behavior (600ms)
    inputEl.classList.add('input-warning');
    setTimeout(() => inputEl.classList.remove('input-warning'), 600);
  }
}

/* ═══════════════════════════════════════════════════════════
   SAVE — composite PK pair
   ═══════════════════════════════════════════════════════════ */
async function saveRecord() {
  const ccInput  = document.getElementById('costCenterInput');
  const orgInput = document.getElementById('orgcodeInput');

  const cost_center = ccInput.value.trim().toUpperCase();
  const orgcode     = orgInput.value.trim();

  if (!cost_center || !orgcode) {
    showWarning('กรุณากรอกทั้ง Cost Center และ Orgcode');
    return;
  }

  // Frontend Fail Fast (UX layer): check both PK columns
  const dup = masterData.some(r =>
    r.cost_center === cost_center && r.orgcode === orgcode
  );
  if (dup) {
    showErrorModal({
      status: 409,
      body: {
        code: 'DUPLICATE_KEY',
        message_th: 'Cost Center และ Orgcode คู่นี้มีอยู่แล้ว',
      },
    });
    return;
  }

  try {
    await apiClient.save({ cost_center, orgcode }, false);
    newRowKey = `${cost_center}::${orgcode}`;
    await refreshAll();
    resetForm();
    showSuccessToast('เพิ่ม mapping สำเร็จ');
  } catch (err) {
    showErrorModal(err);
  }
}

/* ═══════════════════════════════════════════════════════════
   DELETE — both PK columns required
   ═══════════════════════════════════════════════════════════ */
function confirmDelete(cost_center, orgcode) {
  pendingDelete = { cost_center, orgcode };
  document.getElementById('deleteModal').classList.add('show');
}

async function executeDelete() {
  if (!pendingDelete) return;
  try {
    await apiClient.remove(pendingDelete);
    await refreshAll();
    closeDeleteModal();
    showSuccessToast('ลบ mapping สำเร็จ');
  } catch (err) {
    closeDeleteModal();
    showErrorModal(err);
  }
}

function closeDeleteModal() {
  document.getElementById('deleteModal').classList.remove('show');
  pendingDelete = null;
}

function resetForm() {
  document.getElementById('costCenterInput').value = '';
  document.getElementById('orgcodeInput').value    = '';
}

async function refreshAll() {
  masterData = await apiClient.list();
  renderTable();
  renderLegend();
}

/* ═══════════════════════════════════════════════════════════
   RENDER — group by Cost Center for the mapping matrix view
   ═══════════════════════════════════════════════════════════ */
function renderTable() {
  const tbody  = document.querySelector('#dataTable tbody');
  const search = document.getElementById('tableSearch').value.trim().toLowerCase();

  const rows = masterData.filter(r =>
    !search ||
    r.cost_center.toLowerCase().includes(search) ||
    r.orgcode.toLowerCase().includes(search) ||
    (r.orgcode_name || '').toLowerCase().includes(search)
  );

  tbody.innerHTML = rows.length === 0
    ? `<tr class="empty"><td colspan="3">
         <div class="empty-title">No mappings</div>
         <div class="empty-sub">เพิ่ม mapping คู่แรกได้จากฟอร์มด้านบน</div>
       </td></tr>`
    : rows.map(r => {
        const key = `${r.cost_center}::${r.orgcode}`;
        const isNew = key === newRowKey ? 'class="row-new"' : '';
        return `
          <tr ${isNew}>
            <td><span class="badge-code">${escapeHtml(r.cost_center)}</span></td>
            <td>
              <span class="badge-group">${escapeHtml(r.orgcode)}</span>
              ${r.orgcode_name ? `<span class="muted"> · ${escapeHtml(r.orgcode_name)}</span>` : ''}
            </td>
            <td class="action-col">
              <button class="btn-sm btn-danger" 
                      onclick="confirmDelete('${escapeAttr(r.cost_center)}', '${escapeAttr(r.orgcode)}')">
                Delete
              </button>
            </td>
          </tr>`;
      }).join('');

  setTimeout(() => { newRowKey = null; }, 2400);
}

function renderLegend() {
  // Count unique Cost Centers and Orgcodes
  const uniqCC  = new Set(masterData.map(r => r.cost_center)).size;
  const uniqOrg = new Set(masterData.map(r => r.orgcode)).size;
  const countCC  = document.getElementById('countCC');
  const countOrg = document.getElementById('countOrg');
  if (countCC)  countCC.textContent  = uniqCC;
  if (countOrg) countOrg.textContent = uniqOrg;
}

/* ═══════════════════════════════════════════════════════════
   ERROR & SUCCESS UI
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

function showSuccessToast(message) {
  const toast = document.getElementById('successToast');
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2000);
}

function showWarning(msg) {
  const input = document.getElementById('costCenterInput');
  input.classList.add('input-warning');
  setTimeout(() => input.classList.remove('input-warning'), 600);
}

/* ─── HTML-escape helpers ─── */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
  ));
}
function escapeAttr(s) {
  return String(s).replace(/['"\\]/g, c => '\\' + c);
}
