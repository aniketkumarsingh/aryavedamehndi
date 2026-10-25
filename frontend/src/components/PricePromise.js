import { useEffect, useState } from "react";
import { Icon } from "@/components/OrderParts";
import { api } from "@/lib/api";
import { pricePromises } from "@/lib/pricing";

let policyCache = null;
// In pricePromises() order: same price, platform fee, deposit.
const PROMISE_ICONS = ["tag", "receipt", "shield"];

/** The site-wide pricing promise - shown on every order page. */
export default function PricePromise({ compact = false }) {
  const [policy, setPolicy] = useState(policyCache);

  useEffect(() => {
    if (policyCache) return;
    api
      .get("/pricing/policy")
      .then((p) => {
        policyCache = p;
        setPolicy(p);
      })
      .catch(() => {});
  }, []);

  const promises = pricePromises(policy);
  if (compact) {
    return (
      <div className="rounded-xl border border-gold/40 bg-gold-soft px-4 py-3">
        <p className="text-[11px] font-bold uppercase tracking-wider text-gold mb-2">The AryaVeda price promise</p>
        <ul className="flex flex-col gap-2">
          {promises.map((p, i) => (
            <li key={p.title} className="flex gap-2 text-xs">
              <Icon name={PROMISE_ICONS[i]} className="w-4 h-4 text-gold flex-none mt-0.5" />
              <span>
                <b className="text-maroon">{p.title}.</b> {p.body}
              </span>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  return (
    <section aria-label="Our price promise">
      <p className="text-center text-[11px] font-bold uppercase tracking-[0.2em] text-gold mb-3">The AryaVeda price promise</p>
      <div className="grid sm:grid-cols-3 gap-4">
        {promises.map((p, i) => (
          <div key={p.title} className="card p-5 flex flex-col items-center text-center gap-2">
            <span className="w-12 h-12 rounded-full bg-gold-soft text-gold flex items-center justify-center ring-1 ring-gold/40">
              <Icon name={PROMISE_ICONS[i]} />
            </span>
            <p className="font-display font-semibold text-maroon">{p.title}</p>
            <p className="text-xs text-ink-soft leading-relaxed">{p.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
