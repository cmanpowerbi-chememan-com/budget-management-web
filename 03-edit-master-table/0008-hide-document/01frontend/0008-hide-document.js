/* ═══════════════════════════════════════════════════════════
   0008-hide-document.js — Hide Document Number Master logic
   
   Composite PK 3 cols: (doc_num, fiscal_year, fiscal_month).
   Frontend joins year+month into "YYYY-MM" for display, but
   sends as 3 separate fields to the backend.
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
   DATA
   ═══════════════════════════════════════════════════════════ */
let sapDocNumbers = [];   // [{code, name}, ...]
let masterData    = [];   // [{doc_num, fiscal_year, fiscal_month, period, doc_name}, ...]

let pendingDelete = null;
let newRowKey     = null;

/* ═══════════════════════════════════════════════════════════
   PERIOD FORMATTER — frontend "YYYY-MM" string from separate
   year/month integers. Used for display only.
   ═══════════════════════════════════════════════════════════ */
function fmtPeriod(y, m) {
  return `${y}-${String(m).padStart(2, '0')}`;
}

/* ═══════════════════════════════════════════════════════════
   INIT
   ═══════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
  applyThemeFromStorage();
  const ok = await checkAdminAccess();
  if (!ok) return;

  try {
    const [docs, mappings] = await Promise.all([
      apiClient.refDocNumbers(),
      apiClient.list(),
    ]);
    sapDocNumbers = docs;
    masterData    = mappings;
    populateMonthDropdown();
    renderTable();
    renderLegend();
  } catch (err) {
    showErrorModal(err);
  }
});

/* ═══════════════════════════════════════════════════════════
   MONTH DROPDOWN — fixed 1..12
   ═══════════════════════════════════════════════════════════ */
function populateMonthDropdown() {
  const sel = document.getElementById('monthSelect');
  if (!sel) return;
  const names = [
    'มกราคม', 'กุมภาพันธ์', 'มีนาคม',  'เมษายน',
    'พฤษภาคม', 'มิถุนายน',   'กรกฎาคม', 'สิงหาคม',
    'กันยายน', 'ตุลาคม',     'พฤศจิกายน', 'ธันวาคม',
  ];
  sel.innerHTML = names.map((n, i) =>
    `<option value="${i + 1}">${String(i + 1).padStart(2, '0')} — ${n}</option>`
  ).join('');
}

/* ═══════════════════════════════════════════════════════════
   SAVE — 3-column composite PK
   ═══════════════════════════════════════════════════════════ */
async function saveRecord() {
  const docInput   = document.getElementById('docNumInput');
  const yearInput  = document.getElementById('yearInput');
  const monthSel   = document.getElementById('monthSelect');

  const doc_num      = docInput.value.trim();
  const fiscal_year  = parseInt(yearInput.value, 10);
  const fiscal_month = parseInt(monthSel.value, 10);

  // ── Local validation: empty + range ──
  if (!doc_num || !fiscal_year || !fiscal_month) {
    showWarning('กรุณากรอกข้อมูลให้ครบทุกช่อง');
    return;
  }
  if (fiscal_year < 2020 || fiscal_year > 2099) {
    showWarning('Fiscal Year ต้องอยู่ระหว่าง 2020-2099');
    return;
  }
  if (fiscal_month < 1 || fiscal_month > 12) {
    showWarning('Fiscal Month ต้องอยู่ระหว่าง 1-12');
    return;
  }

  // ── Frontend Fail Fast: check all 3 PK columns ──
  const dup = masterData.some(r =>
    r.doc_num === doc_num &&
    r.fiscal_year === fiscal_year &&
    r.fiscal_month === fiscal_month
  );
  if (dup) {
    showErrorModal({
      status: 409,
      body: {
        code: 'DUPLICATE_KEY',
        message_th: `Document ${doc_num} ถูก hide ในงวด ${fmtPeriod(fiscal_year, fiscal_month)} อยู่แล้ว`,
      },
    });
    return;
  }

  try {
    await apiClient.save({ doc_num, fiscal_year, fiscal_month }, false);
    newRowKey = `${doc_num}::${fiscal_year}::${fiscal_month}`;
    await refreshAll();
    resetForm();
    showSuccessToast(`เพิ่ม rule สำเร็จ (${fmtPeriod(fiscal_year, fiscal_month)})`);
  } catch (err) {
    showErrorModal(err);
  }
}

/* ═══════════════════════════════════════════════════════════
   DELETE — all 3 PK columns required
   ═══════════════════════════════════════════════════════════ */
function confirmDelete(doc_num, fiscal_year, fiscal_month) {
  pendingDelete = {
    doc_num,
    fiscal_year: parseInt(fiscal_year, 10),
    fiscal_month: parseInt(fiscal_month, 10),
  };
  document.getElementById('deleteModal').classList.add('show');
}

async function executeDelete() {
  if (!pendingDelete) return;
  try {
    await apiClient.remove(pendingDelete);
    await refreshAll();
    closeDeleteModal();
    showSuccessToast('ลบ rule สำเร็จ');
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
  document.getElementById('docNumInput').value = '';
  document.getElementById('yearInput').value   = new Date().getFullYear() + 543 - 543; // current year
  document.getElementById('monthSelect').value = '1';
}

async function refreshAll() {
  masterData = await apiClient.list();
  renderTable();
  renderLegend();
}

/* ═══════════════════════════════════════════════════════════
   RENDER
   ═══════════════════════════════════════════════════════════ */
function renderTable() {
  const tbody  = document.querySelector('#dataTable tbody');
  const search = document.getElementById('tableSearch').value.trim().toLowerCase();

  const rows = masterData.filter(r =>
    !search ||
    r.doc_num.toLowerCase().includes(search) ||
    (r.period || '').toLowerCase().includes(search) ||
    (r.doc_name || '').toLowerCase().includes(search)
  );

  tbody.innerHTML = rows.length === 0
    ? `<tr class="empty"><td colspan="3">
         <div class="empty-title">No exclusion rules</div>
         <div class="empty-sub">เพิ่ม rule แรกจากฟอร์มด้านบน</div>
       </td></tr>`
    : rows.map(r => {
        const key = `${r.doc_num}::${r.fiscal_year}::${r.fiscal_month}`;
        const isNew = key === newRowKey ? 'class="row-new"' : '';
        return `
          <tr ${isNew}>
            <td>
              <span class="badge-code">${escapeHtml(r.doc_num)}</span>
              ${r.doc_name ? `<span class="muted"> · ${escapeHtml(r.doc_name)}</span>` : ''}
            </td>
            <td><span class="badge-group">${escapeHtml(r.period)}</span></td>
            <td class="action-col">
              <button class="btn-sm btn-danger" 
                      onclick="confirmDelete('${escapeAttr(r.doc_num)}', ${r.fiscal_year}, ${r.fiscal_month})">
                Delete
              </button>
            </td>
          </tr>`;
      }).join('');

  setTimeout(() => { newRowKey = null; }, 2400);
}

function renderLegend() {
  const uniqDocs    = new Set(masterData.map(r => r.doc_num)).size;
  const uniqPeriods = new Set(masterData.map(r => r.period)).size;
  const elDocs    = document.getElementById('countDocs');
  const elPeriods = document.getElementById('countPeriods');
  if (elDocs)    elDocs.textContent    = uniqDocs;
  if (elPeriods) elPeriods.textContent = uniqPeriods;
}

/* ═══════════════════════════════════════════════════════════
   ERROR & SUCCESS UI
   ═══════════════════════════════════════════════════════════ */
function showErrorModal(err) {
  const modal = document.getElementById('errorModal');
  if (!modal) { alert(err.message || String(err)); return; }

  const body = err.body || {};
  const title = body.code === 'DUPLICATE_KEY' ? 'Rule ซ้ำ'
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
  const input = document.getElementById('docNumInput');
  if (input) {
    input.classList.add('input-warning');
    setTimeout(() => input.classList.remove('input-warning'), 600);
  }
  console.warn(msg);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
  ));
}
function escapeAttr(s) {
  return String(s).replace(/['"\\]/g, c => '\\' + c);
}
