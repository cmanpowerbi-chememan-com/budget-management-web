/* ═══════════════════════════════════════════════════════════
   api-client.js — GL Group Master
   Fetch wrapper with Azure AD auth + token refresh retry
   ═══════════════════════════════════════════════════════════ */

const API_BASE = '/api/master/gl-group';

class ApiError extends Error {
  constructor(status, body) {
    super(body.message_th || body.message_en || body.error || 'Request failed');
    this.status = status;
    this.body = body;
  }
}

const apiClient = {
  async _fetch(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const opts = {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      credentials: 'include',
    };

    let res = await fetch(url, opts);

    // Token expired? Refresh once and retry.
    if (res.status === 401) {
      await fetch('/.auth/refresh', { credentials: 'include' });
      res = await fetch(url, opts);
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({ error: 'Unknown error' }));
      throw new ApiError(res.status, body);
    }
    return res.json();
  },

  list()           { return this._fetch('/list',                    { method: 'GET'    }); },
  save(p, edit)    { return this._fetch('/save',                    { method: 'POST',   body: JSON.stringify({...p, is_edit_mode: edit}) }); },
  remove(p)        { return this._fetch('/delete',                  { method: 'DELETE', body: JSON.stringify(p) }); },
  refGlCodes()     { return this._fetch('/reference/gl-codes',      { method: 'GET'    }); },
  refGlGroups()    { return this._fetch('/reference/gl-groups',     { method: 'GET'    }); },
};

/* ─── Admin access check ─── */
async function checkAdminAccess() {
  const res = await fetch('/.auth/me', { credentials: 'include' });
  const { clientPrincipal } = await res.json();

  if (!clientPrincipal) {
    const back = encodeURIComponent(window.location.pathname);
    window.location.href = `/.auth/login/aad?post_login_redirect_uri=${back}`;
    return false;
  }

  const isAdmin = (clientPrincipal.userRoles || []).includes('master_table_admins');
  if (!isAdmin) {
    window.location.href = '/access-denied.html';
    return false;
  }
  return true;
}

window.apiClient = apiClient;
window.checkAdminAccess = checkAdminAccess;
window.ApiError = ApiError;
