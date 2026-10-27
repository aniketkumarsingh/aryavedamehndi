import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";

const KIND_LABELS = { credit: "Credit", spend: "Used on order", restore: "Returned (order cancelled)", expire: "Expired", void: "Removed" };

/** Refer a friend + wallet balance and history. */
export default function Wallet() {
  const { user, ready } = useAuth();
  const [referral, setReferral] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  function load() {
    api.get("/users/me/referral").then(setReferral).catch((e) => setError(e.message));
    api.get("/users/me/wallet").then(setWallet).catch(() => {});
  }
  useEffect(() => {
    if (user?.role === "consumer") load();
  }, [user?.role]);

  if (ready && !user) {
    return (
      <div className="card p-6 max-w-md mx-auto text-center">
        <p className="mb-3">Log in to see your wallet and referral code.</p>
        <Link href="/login" className="btn-primary">Log in</Link>
      </div>
    );
  }

  const shareText = referral
    ? `Get ₹${referral.friend_discount} off your first AryaVeda Mehndi order with my code ${referral.code}: ${referral.link}`
    : "";

  async function share() {
    try {
      if (navigator.share) await navigator.share({ text: shareText });
      else {
        await navigator.clipboard.writeText(shareText);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }
    } catch {
      /* share sheet dismissed */
    }
  }

  async function apply(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      const res = await api.post("/users/me/referral/apply", { code: code.trim() });
      setMessage(`Code applied — ₹${res.friend_discount} comes off your first order.`);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="max-w-xl mx-auto flex flex-col gap-5">
      <Head>
        <title>Wallet &amp; Referrals — AryaVeda Mehndi</title>
      </Head>
      <h1 className="text-2xl">Wallet &amp; referrals</h1>

      {referral && (
        <div className="card p-5 flex flex-col gap-3">
          <h2 className="font-semibold">Refer a friend</h2>
          <p className="text-sm text-ink-soft">
            Your friend gets ₹{referral.friend_discount} off their first shop order. You get ₹{referral.reward} in your wallet once it&apos;s delivered
            and the return window has passed.
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="chip text-base font-semibold tracking-wider">{referral.code}</span>
            <button className="btn-primary text-sm" onClick={share}>{copied ? "Copied ✓" : "Share"}</button>
            <a className="btn-secondary text-sm" href={`https://wa.me/?text=${encodeURIComponent(shareText)}`} target="_blank" rel="noopener noreferrer">
              WhatsApp
            </a>
          </div>
          <p className="text-xs text-ink-soft">
            {referral.invited} joined · {referral.rewarded} rewarded · ₹{referral.earned} earned
          </p>
          {!referral.referred_by_code && (
            <form onSubmit={apply} className="flex gap-2 pt-2 border-t border-line">
              <input className="input text-sm uppercase" placeholder="Have a friend's code?" value={code} onChange={(e) => setCode(e.target.value)} />
              <button className="btn-secondary text-sm" disabled={code.trim().length < 4}>Apply</button>
            </form>
          )}
          {referral.referred_by_code && <p className="text-xs text-ink-soft">You joined with code {referral.referred_by_code}.</p>}
          {message && <p className="text-sm text-green-800">{message}</p>}
          {error && <p className="text-sm text-red-700">{error}</p>}
        </div>
      )}

      {wallet && (
        <div className="card p-5 flex flex-col gap-3">
          <div className="flex justify-between items-baseline">
            <h2 className="font-semibold">Wallet</h2>
            <span className="text-2xl font-semibold text-maroon-soft">₹{wallet.balance}</span>
          </div>
          <p className="text-xs text-ink-soft">Use it at checkout on shop orders. Credit expires — the soonest-expiring is used first.</p>
          <div className="flex flex-col gap-1 text-sm">
            {wallet.entries.map((e, i) => (
              <div key={i} className="flex justify-between gap-2 border-b border-line pb-1">
                <span>
                  {KIND_LABELS[e.kind] || e.kind}
                  {e.note && <span className="text-ink-soft"> · {e.note}</span>}
                  {e.kind === "credit" && e.expires_at && e.remaining > 0 && (
                    <span className="text-xs text-ink-soft"> · ₹{e.remaining} left, expires {new Date(e.expires_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</span>
                  )}
                </span>
                <span className={e.amount < 0 ? "text-red-700" : "text-green-800"}>{e.amount < 0 ? "−" : "+"}₹{Math.abs(e.amount)}</span>
              </div>
            ))}
            {wallet.entries.length === 0 && <p className="text-ink-soft">No wallet activity yet.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
