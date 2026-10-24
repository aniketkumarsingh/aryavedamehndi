import { useEffect, useState } from "react";

// Chrome/Edge/Samsung fire `beforeinstallprompt` once, early - usually
// before the user ever opens /download - so it's captured here at module
// load (this module is imported from _app) and handed to the page later.
let deferredPrompt = null;
let installedThisSession = false;
const listeners = new Set();

function emit() {
  listeners.forEach((fn) => fn());
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // we show our own Install button instead of the mini-infobar
    deferredPrompt = e;
    emit();
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    installedThisSession = true;
    emit();
  });
}

/** { canPrompt, installed, promptInstall } - promptInstall() shows the
 * browser's own install dialog and resolves to "accepted" | "dismissed" |
 * "unavailable". */
export function useInstallPrompt() {
  const [, rerender] = useState(0);
  useEffect(() => {
    const fn = () => rerender((n) => n + 1);
    listeners.add(fn);
    return () => listeners.delete(fn);
  }, []);

  async function promptInstall() {
    if (!deferredPrompt) return "unavailable";
    const prompt = deferredPrompt;
    deferredPrompt = null; // a prompt event can only be used once
    emit();
    await prompt.prompt();
    const { outcome } = await prompt.userChoice;
    return outcome;
  }

  return { canPrompt: !!deferredPrompt, installed: installedThisSession, promptInstall };
}

/** Caches that may hold one user's private data. "apis" is where service
 * workers built before the runtimeCaching fix in next.config.js stored
 * every /api response - those installs still have it on disk. */
const PRIVATE_CACHES = ["apis"];

export async function clearPrivateCaches() {
  if (typeof window === "undefined" || !("caches" in window)) return;
  try {
    await Promise.all(PRIVATE_CACHES.map((name) => caches.delete(name)));
  } catch {
    /* storage access denied - nothing we can do */
  }
}

/** True when running as the installed app (its own window / home-screen
 * icon) rather than in a browser tab. */
export function isStandalone() {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

/** Which install path applies to this browser. Order matters: iPadOS
 * Safari reports a Mac user agent, and every iOS browser includes
 * "Safari" in its UA. */
export function detectPlatform(ua = navigator.userAgent, maxTouchPoints = navigator.maxTouchPoints || 0) {
  const isIOS = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && maxTouchPoints > 1);
  const isAndroid = /Android/.test(ua);
  const isMac = !isIOS && /Macintosh|Mac OS X/.test(ua);
  const isWindows = /Windows/.test(ua);

  let browser = "other";
  if (/Edg(e|A|iOS)?\//.test(ua)) browser = "edge";
  else if (/SamsungBrowser\//.test(ua)) browser = "samsung";
  else if (/Firefox\/|FxiOS\//.test(ua)) browser = "firefox";
  else if (/Chrome\/|CriOS\//.test(ua)) browser = "chrome";
  else if (/Safari\//.test(ua)) browser = "safari";

  const os = isIOS ? "ios" : isAndroid ? "android" : isMac ? "mac" : isWindows ? "windows" : "other";
  return { os, browser };
}
