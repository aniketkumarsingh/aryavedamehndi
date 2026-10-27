import { useEffect } from "react";
import { AUTH_CHANGED_EVENT, api, getStoredUser } from "@/lib/api";
import { CONSENT_EVENT, getConsent } from "@/lib/analytics";
import { attributionPayload, captureLanding, firstTouch } from "@/lib/attribution";

const SENT_KEY = "aryaveda_attribution_sent";

/** Records campaign landings, and once signed in tells the server the first
 * touch, the cookie-consent choice and any ?ref= code (applied to new
 * customers). Renders nothing. */
export default function AttributionSync() {
  useEffect(() => {
    captureLanding();

    function send(force = false) {
      if (!getStoredUser()) return;
      const consent = getConsent();
      const body = { ...(firstTouch() || {}), ...(attributionPayload()?.ref ? { ref: attributionPayload().ref } : {}) };
      if (consent) body.analytics_consent = consent === "granted";
      const fingerprint = JSON.stringify(body);
      try {
        if (!force && sessionStorage.getItem(SENT_KEY) === fingerprint) return;
        sessionStorage.setItem(SENT_KEY, fingerprint);
      } catch {
        /* storage blocked - sending again is harmless */
      }
      api.post("/growth/attribution", body).catch(() => {});
    }

    send();
    const onAuth = () => send(true);
    const onConsent = () => send(true);
    window.addEventListener(AUTH_CHANGED_EVENT, onAuth);
    window.addEventListener(CONSENT_EVENT, onConsent);
    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, onAuth);
      window.removeEventListener(CONSENT_EVENT, onConsent);
    };
  }, []);
  return null;
}
