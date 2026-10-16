import { createContext, useContext, useEffect, useState } from "react";
import { translate } from "@/lib/i18n";

const LANG_STORAGE_KEY = "aryaveda_lang";
const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState("en");

  useEffect(() => {
    const stored = typeof window !== "undefined" ? window.localStorage.getItem(LANG_STORAGE_KEY) : null;
    if (stored === "en" || stored === "hi") setLang(stored);
  }, []);

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
