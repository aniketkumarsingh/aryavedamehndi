import { clearPrivateCaches } from "./pwa.js";

const TOKEN_KEY = "aryamehndi_token";
const REFRESH_KEY = "aryamehndi_refresh";
const USER_KEY = "aryamehndi_user";
export const AUTH_CHANGED_EVENT = "aryamehndi-auth-changed";

function notifyAuthChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
  }
}

export function getToken() {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getStoredUser() {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function getRefreshToken() {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

export function storeSession({ access_token, refresh_token, user_id, role }) {
  try {
    localStorage.setItem(TOKEN_KEY, access_token);
    if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
    localStorage.setItem(USER_KEY, JSON.stringify({ id: user_id, role }));
  } catch {
    /* private-browsing storage can throw - session just won't persist */
  }
  notifyAuthChanged();
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
  // Any session end (logout, or a refresh that failed) wipes cached
  // private API responses from older service workers.
  clearPrivateCaches();
  notifyAuthChanged();
}

/** Best-effort server-side revoke of the refresh token, then local logout. */
export async function logoutSession() {
  const refresh_token = getRefreshToken();
  clearSession();
  if (!refresh_token) return;
  try {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    });
  } catch {
    /* offline - the token still expires on its own */
  }
}

let refreshInFlight = null;

/** Swaps the refresh token for a new pair after an access token expired.
 * Refresh tokens rotate (each works once), so concurrent refreshes must
 * not both spend the same one - that looks like token theft and the server
 * revokes the whole session. Requests in this tab share one in-flight
 * refresh, and a Web Lock serialises it across tabs; a tab that gets the
 * lock after another tab already refreshed just picks up the new token. */
function refreshSession(failedToken) {
  if (refreshInFlight) return refreshInFlight;

  async function doRefresh() {
    if (getToken() !== failedToken) return !!getToken();
    const refresh_token = getRefreshToken();
    if (!refresh_token) return false;
    try {
      const res = await fetch("/api/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token }),
      });
      if (!res.ok) return false;
      storeSession(await res.json());
      return true;
    } catch {
      return false;
    }
  }

  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  refreshInFlight = (locks ? locks.request("aryamehndi-token-refresh", doRefresh) : doRefresh()).finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

async function request(path, { method = "GET", body, isForm = false, auth = true, query } = {}, isRetry = false) {
  const headers = {};
  if (!isForm) headers["Content-Type"] = "application/json";
  const token = auth ? getToken() : null;
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const qs = query ? `?${new URLSearchParams(query).toString()}` : "";

  const res = await fetch(`/api${path}${qs}`, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && token && !isRetry) {
    // Access tokens are short-lived - refresh once and replay the request.
    if (await refreshSession(token)) {
      return request(path, { method, body, isForm, auth, query }, true);
    }
    // Refresh failed too - drop the stale local session so the UI reflects
    // "logged out" instead of silently failing forever.
    clearSession();
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get: (path, query) => request(path, { query }),
  post: (path, body, query) => request(path, { method: "POST", body, query }),
  put: (path, body) => request(path, { method: "PUT", body }),
  del: (path) => request(path, { method: "DELETE" }),
  upload: (path, file) => {
    const form = new FormData();
    form.append("file", file);
    return request(path, { method: "POST", body: form, isForm: true });
  },
  // Multipart with extra fields alongside the file.
  uploadForm: (path, form, method = "POST") => request(path, { method, body: form, isForm: true }),
};
