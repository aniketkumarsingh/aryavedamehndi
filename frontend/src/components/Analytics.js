import { useEffect, useState } from "react";
import Link from "next/link";
import Script from "next/script";
import { useRouter } from "next/router";
import { useLanguage } from "@/lib/useLanguage";
import { CONSENT_EVENT, GA_ID, META_PIXEL_ID, analyticsConfigured, getConsent, setConsent } from "@/lib/analytics";

/** Loads Google Analytics 4 and the Meta Pixel once the visitor accepts,
 * tracks page views on client-side navigation, and shows the consent
 * banner. Renders nothing when no analytics IDs are configured. */
export default function Analytics() {
  const router = useRouter();
  const { t } = useLanguage();
  const [consent, setConsentState] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sync = () => setConsentState(getConsent());
    sync();
    setReady(true);
    window.addEventListener(CONSENT_EVENT, sync);
    return () => window.removeEventListener(CONSENT_EVENT, sync);
  }, []);

  useEffect(() => {
    if (consent !== "granted") return;
    const onRoute = (url) => {
      if (window.gtag && GA_ID) window.gtag("config", GA_ID, { page_path: url });
      if (window.fbq) window.fbq("track", "PageView");
    };
    router.events.on("routeChangeComplete", onRoute);
    return () => router.events.off("routeChangeComplete", onRoute);
  }, [consent, router.events]);

  if (!analyticsConfigured || !ready) return null;

  return (
    <>
      {consent === "granted" && GA_ID && (
        <>
          <Script src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`} strategy="afterInteractive" />
          <Script id="ga4" strategy="afterInteractive">
            {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}window.gtag=gtag;gtag('js',new Date());gtag('config','${GA_ID}');`}
          </Script>
        </>
      )}
      {consent === "granted" && META_PIXEL_ID && (
        <Script id="meta-pixel" strategy="afterInteractive">
          {`!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');fbq('init','${META_PIXEL_ID}');fbq('track','PageView');`}
        </Script>
      )}
      {consent === null && (
        <div role="dialog" aria-label="Cookie consent" className="fixed inset-x-0 bottom-0 z-50 p-3">
          <div className="max-w-3xl mx-auto card p-4 flex flex-col sm:flex-row sm:items-center gap-3 shadow-lg">
            <p className="text-xs text-ink-soft flex-1">
              {t("consent_text")}{" "}
              <Link href="/legal/privacy" className="underline">{t("consent_privacy")}</Link>
            </p>
            <div className="flex gap-2 flex-none">
              <button className="btn-secondary text-xs" onClick={() => setConsent("denied")}>
                {t("consent_decline")}
              </button>
              <button className="btn-primary text-xs" onClick={() => setConsent("granted")}>
                {t("consent_accept")}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
