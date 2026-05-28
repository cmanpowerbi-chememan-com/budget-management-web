/* ═══════════════════════════════════════════════════════════
   api-client-orgcode-cc.js — Orgcode & Cost Center Mapping
   Fetch wrapper for /api/master/orgcode-costcenter/*
   ═══════════════════════════════════════════════════════════ */

const OCC_API_BASE = '/api/master/orgcode-costcenter';

class OccApiError extends Error {
  constructor(status, body) {
    super(body.message_th || body.message_en || body.error || 'Request failed');
    this.status = status;
    this.body = body;
  }
}

const occApiClient = {
  async _fetch(path, options = {}) {
    const url = `${OCC_API_BASE}${path}`;
    const opts = {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      credentials: 'include',
    };

    let res = await fetch(url, opts);

    if (res.status === 401) {
      await fetch('/.auth/refresh', { credentials: 'include' });
      res = await fetch(url, opts);
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({ error: 'Unknown error' }));
      throw new OccApiError(res.status, body);
    }
    return res.json();
  },

  list()           { return this._fetch('/list',                       { method: 'GET'    }); },
  save(p)          { return this._fetch('/save',                       { method: 'POST',   body: JSON.stringify(p) }); },
  remove(p)        { return this._fetch('/delete',                     { method: 'DELETE', body: JSON.stringify(p) }); },
  refOrgcodes()    { return this._fetch('/reference/orgcodes',         { method: 'GET'    }); },
  refCostCenters() { return this._fetch('/reference/cost-centers',     { method: 'GET'    }); },
};

/* ─── Admin access guard ─── */
async function checkAdminAccess() {
  const res = await fetch('/.auth/me', { credentials: 'include' });
  const { clientPrincipal } = await res.json();
  if (!clientPrincipal) {
    const back = encodeURIComponent(window.location.pathname);
    window.location.href = `/.auth/login/aad?post_login_redirect_uri=${back}`;
    return false;
  }
  return true;
}

window.occApiClient   = occApiClient;
window.OccApiError    = OccApiError;
window.checkAdminAccess = checkAdminAccess;
