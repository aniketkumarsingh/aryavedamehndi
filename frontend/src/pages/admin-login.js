import { useState } from "react";
import Head from "next/head";
import { useRouter } from "next/router";
import { api, storeSession } from "@/lib/api";

export default function AdminLogin() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post("/auth/admin-login", { username, password }, null);
      storeSession(res);
      router.push("/admin");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="invitation-frame max-w-sm mx-auto p-6 mt-4">
      <Head>
        <title>Admin Login — AryaVeda Mehndi</title>
      </Head>
      <span className="corner-tl" aria-hidden="true" />
      <span className="corner-tr" aria-hidden="true" />
      <span className="corner-bl" aria-hidden="true" />
      <span className="corner-br" aria-hidden="true" />
      <img src="/logo/mark.svg" alt="AryaVeda Mehndi" className="h-16 w-16 mx-auto mb-3" />
      <h1 className="text-xl text-center">Admin Login</h1>
      <p className="text-sm text-ink-soft text-center mb-5">For the AryaVeda Mehndi team only.</p>

      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="text-sm font-semibold">Username</label>
        <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />

        <label className="text-sm font-semibold">Password</label>
        <input
          className="input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />

        {error && <p className="text-red-700 text-sm">{error}</p>}

        <button className="btn-primary mt-1" disabled={loading}>
          {loading ? "Signing in…" : "Log In"}
        </button>
      </form>
    </div>
  );
}
