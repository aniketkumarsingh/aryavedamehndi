import { createContext, useContext, useEffect, useState } from "react";
import { translate } from "@/lib/i18n";

const LANG_STORAGE_KEY = "aryaveda_lang";
const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState("en");

  useEffect(() => {
    let stored = null;
    try {
      stored = window.localStorage.getItem(LANG_STORAGE_KEY);
    } catch {
      /* storage disabled - stay on the default */
    }
    if (stored === "en" || stored === "hi") setLang(stored);
  }, []);

  // Keeps <html lang> truthful for screen readers and the browser's
  // translate prompt (see _document.js).
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  function changeLang(next) {
    setLang(next);
    try {
      window.localStorage.setItem(LANG_STORAGE_KEY, next);
    } catch {
      /* private browsing / storage disabled — language just won't persist */
    }
  }

  const t = (key) => translate(lang, key);

  return <LanguageContext.Provider value={{ lang, setLang: changeLang, t }}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used within LanguageProvider");
  return ctx;
}
