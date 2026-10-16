const TOKEN_KEY = "aryamehndi_token";
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

export function storeSession({ access_token, user_id, role }) {
  try {
    localStorage.setItem(TOKEN_KEY, access_token);
    localStorage.setItem(USER_KEY, JSON.stringify({ id: user_id, role }));
  } catch {
    /* private-browsing storage can throw - session just won't persist */
  }
  notifyAuthChanged();
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
  notifyAuthChanged();
}

async function request(path, { method = "GET", body, isForm = false, auth = true, query } = {}) {
  const headers = {};
  if (!isForm) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const qs = query ? `?${new URLSearchParams(query).toString()}` : "";

  const res = await fetch(`/api${path}${qs}`, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401 && auth && getToken()) {
      // Token expired/invalid server-side - drop the stale local session so
      // the UI reflects "logged out" instead of silently failing forever.
      clearSession();
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
};
