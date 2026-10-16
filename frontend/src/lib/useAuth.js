import { useEffect, useState } from "react";
import { AUTH_CHANGED_EVENT, clearSession, getStoredUser } from "./api";

export function useAuth() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setUser(getStoredUser());
    setReady(true);

    // storeSession/clearSession dispatch this in the same tab (e.g. right
    // after login), and the browser's own "storage" event covers other
    // tabs/windows sharing the same origin logging in or out.
    function refresh() {
      setUser(getStoredUser());
    }
    window.addEventListener(AUTH_CHANGED_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  function logout() {
    clearSession();
    setUser(null);
    window.location.href = "/login";
  }

  return { user, ready, logout };
}
