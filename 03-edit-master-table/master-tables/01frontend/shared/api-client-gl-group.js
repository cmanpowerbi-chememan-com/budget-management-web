/* ═══════════════════════════════════════════════════════════
   api-client-gl-group.js — GL Group Master
   Fetch wrapper for /api/master/gl-group/*
   ═══════════════════════════════════════════════════════════ */

const GL_API_BASE = '/api/master/gl-group';

class GlApiError extends Error {
  constructor(status, body) {
    super(body.message_th || body.message_en || body.error || 'Request failed');
    this.status = status;
    this.body = body;
  }
}

const glApiClient = {
  async _fetch(path, options = {}) {
    const url = `${GL_API_BASE}${path}`;
    const opts = {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      credentials: 'include',
    };

    let res = await fetch(url, opts);

    /* Token expired — refresh once and retry */
    if (res.status === 401) {
      await fetch('/.auth/refresh', { credentials: 'include' });
      res = await fetch(url, opts);
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({ error: 'Unknown error' }));
      throw new GlApiError(res.status, body);
    }
    return res.json();
  },

  list()        { return this._fetch('/list',                 { method: 'GET'    }); },
  save(p, edit) { return this._fetch('/save',                 { method: 'POST',   body: JSON.stringify({ ...p, is_edit_mode: edit }) }); },
  remove(p)     { return this._fetch('/delete',               { method: 'DELETE', body: JSON.stringify(p) }); },
  refGlCodes()  { return this._fetch('/reference/gl-codes',  { method: 'GET'    }); },
  refGlGroups() { return this._fetch('/reference/gl-groups', { method: 'GET'    }); },
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

window.glApiClient      = glApiClient;
window.GlApiError       = GlApiError;
window.checkAdminAccess = checkAdminAccess;
