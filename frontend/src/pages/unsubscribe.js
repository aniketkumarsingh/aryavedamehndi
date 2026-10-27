import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { api } from "@/lib/api";

/** One-click unsubscribe from promotional messages (link in each one). */
export default function Unsubscribe() {
  const router = useRouter();
  const { u, t } = router.query;
  const [state, setState] = useState("working");

  useEffect(() => {
    if (!router.isReady) return;
    if (!u || !t) return setState("invalid");
    api.post("/marketing/unsubscribe", { u, t }).then(() => setState("done")).catch(() => setState("invalid"));
  }, [router.isReady, u, t]);

  return (
    <div className="max-w-md mx-auto card p-6 flex flex-col gap-3 text-center">
      <Head>
        <title>Unsubscribe — AryaVeda Mehndi</title>
        <meta name="robots" content="noindex" />
      </Head>
      <h1 className="text-xl">Offers &amp; reminders</h1>
      {state === "working" && <p className="text-sm text-ink-soft">One moment…</p>}
      {state === "done" && (
        <p className="text-sm">
          You won&apos;t get offers or occasion reminders from us any more. Order and booking updates will still reach you. You can turn offers
          back on in your profile.
        </p>
      )}
      {state === "invalid" && <p className="text-sm text-red-700">This unsubscribe link isn&apos;t valid. You can change this in your profile instead.</p>}
      <Link href="/" className="text-sm underline text-maroon-soft">Back to AryaVeda Mehndi</Link>
    </div>
  );
}
