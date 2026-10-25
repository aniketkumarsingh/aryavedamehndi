import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { useLanguage } from "@/lib/useLanguage";
import { useCart } from "@/lib/useCart";
import { cartCount } from "@/lib/cart";
import { LANGUAGES } from "@/lib/i18n";
import NotificationBell from "@/components/NotificationBell";

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const { lang, setLang, t } = useLanguage();
  const cartItems = useCart();
  const router = useRouter();
  const [me, setMe] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (user) {
      api
        .get("/users/me")
        .then(setMe)
        .catch(() => {});
    } else {
      setMe(null);
    }
  }, [user]);

  // Close the mobile menu whenever the route changes, so it doesn't stay
  // open over the newly-navigated-to page.
  useEffect(() => {
    const close = () => setMenuOpen(false);
    router.events.on("routeChangeStart", close);
    return () => router.events.off("routeChangeStart", close);
  }, [router.events]);

  const profileHref = user?.role === "artist" ? "/artist/profile" : user?.role === "consumer" ? "/customer/profile" : null;

  const navLinks = (
    <>
      <Link href="/discover" className="whitespace-nowrap">{t("nav_find_artist")}</Link>
      <Link href="/designs" className="whitespace-nowrap">{t("nav_designs")}</Link>
      {!["artist", "admin"].includes(user?.role) && <Link href="/custom-order" className="whitespace-nowrap">{t("nav_custom_order")}</Link>}
      <Link href="/shop" className="whitespace-nowrap">{t("nav_shop")}</Link>
      <Link href="/download" className="whitespace-nowrap">{t("nav_download")}</Link>
      {user?.role === "consumer" && <Link href="/customer" className="whitespace-nowrap">{t("nav_dashboard")}</Link>}
      {user?.role === "consumer" && <Link href="/my-bookings" className="whitespace-nowrap">{t("nav_my_bookings")}</Link>}
      {user?.role === "artist" && <Link href="/artist" className="whitespace-nowrap">{t("nav_dashboard")}</Link>}
      {user?.role === "artist" && <Link href="/artist/profile" className="whitespace-nowrap">{t("nav_profile")}</Link>}
      {user?.role === "admin" && <Link href="/admin" className="whitespace-nowrap">{t("nav_admin")}</Link>}
    </>
  );

  const languageSelect = (
    <select
      value={lang}
      onChange={(e) => setLang(e.target.value)}
      className="chip text-xs bg-transparent cursor-pointer"
      aria-label="Language"
    >
      {Object.entries(LANGUAGES).map(([code, label]) => (
        <option key={code} value={code}>
          {label}
        </option>
      ))}
    </select>
  );

  const cartLink = (
    <Link href="/cart" className="relative flex-none" aria-label="Cart">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="w-5 h-5 text-maroon">
        <circle cx="9" cy="20" r="1.4" />
        <circle cx="17" cy="20" r="1.4" />
        <path d="M3 4h2l2.2 11.2a2 2 0 002 1.8h7.6a2 2 0 002-1.7L20 8H6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {cartCount(cartItems) > 0 && (
        <span className="absolute -top-1.5 -right-1.5 bg-maroon text-ivory-raised text-[10px] font-bold rounded-full h-4 min-w-4 px-1 flex items-center justify-center">
          {cartCount(cartItems) > 9 ? "9+" : cartCount(cartItems)}
        </span>
      )}
    </Link>
  );

  return (
    <div className="min-h-screen flex flex-col">
      <div className="toran-strip" aria-hidden="true" />
      <header className="border-b border-line bg-ivory-raised sticky top-0 z-10">
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-3 px-4 py-3">
          <Link href="/" className="flex items-center gap-2 font-display text-xl font-semibold text-maroon flex-none">
            <img src="/logo/mark.svg" alt="" className="h-9 w-9" />
            <span className="hidden sm:inline">AryaVeda Mehndi</span>
          </Link>

          {/* Full nav - only shown when there's room for it (xl and up). Logged-in
              users get up to ~1100px of links, which doesn't fit below xl. */}
          <nav className="hidden xl:flex items-center gap-3 2xl:gap-4 text-sm flex-1 justify-end">
            {navLinks}
            {cartLink}
            {languageSelect}
            {user ? (
              <div className="flex items-center gap-2 flex-none">
                <NotificationBell />
                {me && (
                  <Link href={profileHref || "#"} className="flex items-center gap-1.5 whitespace-nowrap" title={me.name || "My profile"}>
                    <img src={me.avatar_url || "/avatars/preset-1.svg"} alt="" className="h-7 w-7 rounded-full object-cover border border-gold" />
                    <span className="text-ink-soft">{me.name || "Me"}</span>
                  </Link>
                )}
                <button onClick={logout} className="chip whitespace-nowrap">
                  {t("nav_logout")}
                </button>
              </div>
            ) : (
              <Link href="/login" className="btn-primary text-sm whitespace-nowrap">
                {t("nav_login")}
              </Link>
            )}
          </nav>

          {/* Narrow screens: just the essentials inline, everything else behind the menu toggle */}
          <div className="flex xl:hidden items-center gap-3 flex-none">
            {cartLink}
            {user && <NotificationBell />}
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="p-1.5 rounded-lg border border-line"
              aria-label="Menu"
              aria-expanded={menuOpen}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-5 h-5 text-maroon">
                {menuOpen ? (
                  <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
                ) : (
                  <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
                )}
              </svg>
            </button>
          </div>
        </div>

        {menuOpen && (
          <div className="xl:hidden border-t border-line bg-ivory-raised px-4 py-4 flex flex-col gap-3 text-sm">
            <div className="flex flex-col gap-3">{navLinks}</div>
            <div className="flex items-center justify-between pt-2 border-t border-line">
              {languageSelect}
              {user ? (
                <div className="flex items-center gap-2">
                  {me && (
                    <Link href={profileHref || "#"} className="flex items-center gap-1.5" title={me.name || "My profile"}>
                      <img src={me.avatar_url || "/avatars/preset-1.svg"} alt="" className="h-7 w-7 rounded-full object-cover border border-gold" />
                      <span className="text-ink-soft">{me.name || "Me"}</span>
                    </Link>
                  )}
                  <button onClick={logout} className="chip">
                    {t("nav_logout")}
                  </button>
                </div>
              ) : (
                <Link href="/login" className="btn-primary text-sm">
                  {t("nav_login")}
                </Link>
              )}
            </div>
          </div>
        )}
      </header>
      <main className="flex-1 max-w-5xl w-full mx-auto px-4 py-8">{children}</main>
      <footer className="border-t border-line text-center text-xs text-ink-soft py-6 flex flex-col gap-1">
        <span>{t("footer_tagline")}</span>
        <Link href="/download" className="text-maroon-soft underline">
          {t("footer_download")}
        </Link>
        <div className="flex items-center justify-center gap-3 mt-1">
          <Link href="/legal/terms" className="underline">{t("footer_terms")}</Link>
          <span>·</span>
          <Link href="/legal/privacy" className="underline">{t("footer_privacy")}</Link>
        </div>
      </footer>
    </div>
  );
}
