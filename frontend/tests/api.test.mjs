import { beforeEach, describe, test } from "node:test";
import assert from "node:assert/strict";

// Minimal browser globals for src/lib/api.js.
globalThis.window = new EventTarget();
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};

const { api, getToken, getStoredUser, storeSession, logoutSession } = await import("../src/lib/api.js");

function json(status, body) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** fetch mock: `routes` maps "METHOD path" -> handler(init) returning a Response. */
function mockFetch(routes) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const key = `${init.method || "GET"} ${url.split("?")[0]}`;
    calls.push({ key, init });
    const handler = routes[key];
    if (!handler) throw new Error(`unexpected fetch ${key}`);
    return handler(init);
  };
  return calls;
}

const session = { access_token: "old-access", refresh_token: "old-refresh", user_id: "u1", role: "consumer" };

beforeEach(() => {
  store.clear();
  storeSession(session);
});

describe("silent token refresh", () => {
  test("an expired access token is refreshed and the request replayed", async () => {
    const calls = mockFetch({
      "GET /api/users/me": (init) =>
        init.headers.Authorization === "Bearer new-access" ? json(200, { id: "u1" }) : json(401, { detail: "Invalid or expired token" }),
      "POST /api/auth/refresh": (init) => {
        assert.deepEqual(JSON.parse(init.body), { refresh_token: "old-refresh" });
        return json(200, { access_token: "new-access", refresh_token: "new-refresh", user_id: "u1", role: "consumer" });
      },
    });

    assert.deepEqual(await api.get("/users/me"), { id: "u1" });
    assert.equal(getToken(), "new-access");
    assert.equal(localStorage.getItem("aryamehndi_refresh"), "new-refresh");
    assert.deepEqual(
      calls.map((c) => c.key),
      ["GET /api/users/me", "POST /api/auth/refresh", "GET /api/users/me"]
    );
  });

  test("concurrent 401s share a single refresh (rotated tokens only work once)", async () => {
    let refreshes = 0;
    mockFetch({
      "GET /api/a": (init) => (init.headers.Authorization === "Bearer new-access" ? json(200, "a") : json(401, {})),
      "GET /api/b": (init) => (init.headers.Authorization === "Bearer new-access" ? json(200, "b") : json(401, {})),
      "POST /api/auth/refresh": async () => {
        refreshes += 1;
        await new Promise((r) => setTimeout(r, 10));
        return json(200, { access_token: "new-access", refresh_token: "new-refresh", user_id: "u1", role: "consumer" });
      },
    });

    assert.deepEqual(await Promise.all([api.get("/a"), api.get("/b")]), ["a", "b"]);
    assert.equal(refreshes, 1);
  });

  test("a failed refresh logs the user out and surfaces the original error", async () => {
    mockFetch({
      "GET /api/users/me": () => json(401, { detail: "Invalid or expired token" }),
      "POST /api/auth/refresh": () => json(401, { detail: "Refresh token was already used" }),
    });

    await assert.rejects(api.get("/users/me"), /Invalid or expired token/);
    assert.equal(getToken(), null);
    assert.equal(getStoredUser(), null);
  });

  test("a request still 401 after refreshing isn't retried forever", async () => {
    const calls = mockFetch({
      "GET /api/admin/overview": () => json(401, { detail: "nope" }),
      "POST /api/auth/refresh": () => json(200, { access_token: "new-access", refresh_token: "new-refresh", user_id: "u1", role: "consumer" }),
    });

    await assert.rejects(api.get("/admin/overview"), /nope/);
    assert.equal(calls.filter((c) => c.key === "GET /api/admin/overview").length, 2);
  });

  test("logged-out requests never try to refresh", async () => {
    store.clear();
    const calls = mockFetch({ "POST /api/auth/admin-login": () => json(401, { detail: "Invalid username or password" }) });
    await assert.rejects(api.post("/auth/admin-login", {}), /Invalid username/);
    assert.equal(calls.length, 1);
  });

  test("logout revokes the refresh token server-side and clears the session", async () => {
    const calls = mockFetch({ "POST /api/auth/logout": () => json(204) });
    await logoutSession();
    assert.equal(getToken(), null);
    assert.deepEqual(JSON.parse(calls[0].init.body), { refresh_token: "old-refresh" });
  });
});
