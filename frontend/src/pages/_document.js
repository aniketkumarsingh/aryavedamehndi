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
        <link rel="sitemap" type="application/xml" href="/sitemap.xml" />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
