import { Head, Html, Main, NextScript } from "next/document";

export default function Document() {
  return (
    // English is the default UI language; LanguageProvider updates this
    // attribute when the user switches to Hindi.
    <Html lang="en">
      <Head>
        <meta name="theme-color" content="#5C1A21" />
        <link rel="manifest" href="/manifest.json" />
        <link rel="icon" href="/icons/icon-192.png" />
        {/* iOS ignores the manifest icons - it needs an opaque 180x180. */}
        <link rel="apple-touch-icon" sizes="180x180" href="/icons/apple-touch-icon.png" />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-title" content="AryaVeda" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="application-name" content="AryaVeda Mehndi" />
        <meta
          name="description"
          content="AryaVeda Mehndi - Ayurvedic, organic mehndi artists, booked safely near you."
        />
        <meta property="og:type" content="website" />
        <meta property="og:site_name" content="AryaVeda Mehndi" />
        <meta property="og:title" content="AryaVeda Mehndi - Ayurvedic Mehndi, Booked Safely" />
        <meta
          property="og:description"
          content="Find verified, gender-matched, organic-mehndi artists near you. Negotiate the price, pay only once you're happy with the design."
        />
        <meta property="og:image" content="/logo/mark.svg" />
        <meta name="twitter:card" content="summary" />
        <meta name="twitter:title" content="AryaVeda Mehndi" />
        <meta
          name="twitter:description"
          content="Ayurvedic, organic mehndi artists near you - booked safely."
        />
        <link rel="sitemap" type="application/xml" href="/sitemap.xml" />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
