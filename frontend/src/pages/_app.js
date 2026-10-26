import { useEffect } from "react";
import Head from "next/head";
import { Manrope, Petrona } from "next/font/google";
import Analytics from "@/components/Analytics";
import { SITE_URL } from "@/components/SocialMeta";
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
      {/* Site-wide defaults. They live here rather than in _document so that
          a page's own tags (same key, via SocialMeta) replace them. */}
      <Head>
        <meta key="description" name="description" content="AryaVeda Mehndi - Ayurvedic, organic mehndi artists, booked safely near you." />
        <meta key="og:type" property="og:type" content="website" />
        <meta key="og:site_name" property="og:site_name" content="AryaVeda Mehndi" />
        <meta key="og:title" property="og:title" content="AryaVeda Mehndi - Ayurvedic Mehndi, Booked Safely" />
        <meta
          key="og:description"
          property="og:description"
          content="Find verified, gender-matched, organic-mehndi artists near you. Negotiate the price, pay only once you're happy with the design."
        />
        <meta key="og:image" property="og:image" content={`${SITE_URL}/icons/icon-512.png`} />
        <meta key="twitter:card" name="twitter:card" content="summary" />
      </Head>
      <div className={`${manrope.variable} ${petrona.variable}`}>
        <Layout>
          <Component {...pageProps} />
        </Layout>
        <Analytics />
      </div>
    </LanguageProvider>
  );
}
