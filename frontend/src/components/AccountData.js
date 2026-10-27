import { useEffect, useState } from "react";
import { api, clearSession } from "@/lib/api";
import { downloadFile } from "@/lib/download";

/** "Your data": download a copy, or delete the account (DPDP Act). */
export default function AccountData() {
  const [check, setCheck] = useState(null);
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) api.get("/users/me/deletion-check").then(setCheck).catch((e) => setError(e.message));
  }, [open]);

  async function remove() {
    setBusy(true);
    setError("");
    try {
      await api.post("/users/me/delete", { confirm });
      clearSession();
      window.location.href = "/";
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <div className="card p-6 flex flex-col gap-3">
      <h2 className="font-semibold">Your data</h2>
      <p className="text-sm text-ink-soft">Download everything we hold about you, or delete your account.</p>
      <div className="flex gap-2 flex-wrap">
        <button className="btn-secondary text-sm" onClick={() => downloadFile("/users/me/export", "aryaveda-my-data.json").catch((e) => setError(e.message))}>
          Download my data
        </button>
        <button className="text-sm text-red-700 underline" onClick={() => setOpen(!open)}>Delete my account…</button>
      </div>
      {open && (
        <div className="border border-red-200 rounded-xl p-4 flex flex-col gap-2 text-sm">
          <p>
            Your name, phone number, photos, addresses and saved details are removed and you&apos;re signed out everywhere. Orders that had a
            GST invoice keep their billing details for the period the law requires. This can&apos;t be undone.
          </p>
          {check && !check.can_delete && (
            <p className="text-red-700">You can delete your account once you have no {check.blocking.join(" or ")}.</p>
          )}
          {check?.can_delete && (
            <>
              <label className="text-xs">
                Type <b>DELETE</b> to confirm
                <input className="input mt-1" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
              </label>
              <button className="btn-primary self-start !bg-red-700 !border-red-700" disabled={busy || confirm.trim().toUpperCase() !== "DELETE"} onClick={remove}>
                {busy ? "Deleting…" : "Delete my account"}
              </button>
            </>
          )}
        </div>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}
