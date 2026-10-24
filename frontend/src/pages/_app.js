import { useEffect } from "react";
import { Manrope, Petrona } from "next/font/google";
import Layout from "@/components/Layout";
// Also starts listening for the browser's install prompt as early as
// possible - see useInstallPrompt.
import { clearPrivateCaches } from "@/lib/pwa";
import { LanguageProvider } from "@/lib/useLanguage";
import "leaflet/dist/leaflet.css";
import "@/styles/globals.css";

// Self-hosted via Next.js (fetched once at build time, served from our own
// origin) instead of a runtime CSS @import to Google's CDN - that approach
// silently fell back to different system fonts per-browser whenever the
// CDN request was slow/blocked (ad-blockers, privacy extensions, flaky
// network), which is exactly what caused Chrome and Edge to render the
// site with different typefaces.
const manrope = Manrope({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-manrope", display: "swap" });
const petrona = Petrona({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-petrona", display: "swap" });

export default function App({ Component, pageProps }) {
  // Installs from before the service-worker caching fix still have a
  // cache full of private API responses - the new worker never writes it,
  // so drop it once on load.
  useEffect(() => {
    clearPrivateCaches();
  }, []);

  return (
    <LanguageProvider>
      <div className={`${manrope.variable} ${petrona.variable}`}>
        <Layout>
          <Component {...pageProps} />
        </Layout>
      </div>
    </LanguageProvider>
  );
}
