import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { api, storeSession } from "@/lib/api";
import { useLanguage } from "@/lib/useLanguage";

export default function Login() {
  const router = useRouter();
  const { t } = useLanguage();

  const GENDERS = [
    { value: "female", label: t("gender_female") },
    { value: "male", label: t("gender_male") },
    { value: "other", label: t("gender_other") },
  ];

  const ROLES = [
    { value: "consumer", label: t("login_role_consumer"), icon: "/avatars/preset-1.svg" },
    { value: "artist", label: t("login_role_artist"), icon: "/logo/mark.svg" },
  ];
  const [phone, setPhone] = useState("");
  const [step, setStep] = useState("phone"); // "phone" | "otp"
  const [code, setCode] = useState("");
  const [devOtp, setDevOtp] = useState(null);
  const [role, setRole] = useState("consumer");
  const [name, setName] = useState("");
  const [gender, setGender] = useState("female");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function requestOtp(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post("/auth/request-otp", { phone }, null);
      setDevOtp(res.sent_by_sms ? null : res.dev_otp);
      setStep("otp");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function verifyOtp(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post("/auth/verify-otp", { phone, code, role, name, gender });
      storeSession(res);
      router.push(res.role === "artist" ? "/artist" : res.role === "admin" ? "/admin" : "/customer");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="invitation-frame max-w-sm mx-auto p-6 mt-4">
      <span className="corner-tl" aria-hidden="true" />
      <span className="corner-tr" aria-hidden="true" />
      <span className="corner-bl" aria-hidden="true" />
      <span className="corner-br" aria-hidden="true" />
      <img src="/logo/mark.svg" alt="AryaVeda Mehndi" className="h-16 w-16 mx-auto mb-3" />
      <h1 className="text-xl text-center">{t("login_welcome")}</h1>
      <p className="text-sm text-ink-soft text-center mb-5">{t("login_tagline")}</p>

      {step === "phone" && (
        <form onSubmit={requestOtp} className="flex flex-col gap-3">
          <label className="text-sm font-semibold">{t("login_phone_label")}</label>
          <div className="flex items-center input gap-2 p-0 overflow-hidden">
            <span className="px-3 text-ink-soft border-r border-line select-none">+91</span>
            <input
              className="flex-1 bg-transparent outline-none py-[0.55rem] pr-3"
              placeholder={t("login_phone_placeholder")}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              maxLength={10}
              required
            />
          </div>
          <button className="btn-primary" disabled={loading}>
            {loading ? t("login_sending") : t("login_send_otp")}
          </button>
        </form>
      )}

      {step === "otp" && (
        <form onSubmit={verifyOtp} className="flex flex-col gap-3">
          {devOtp && (
            <p className="text-xs text-ink-soft bg-gold-soft rounded-lg px-3 py-2">
              {t("login_dev_otp")} <b>{devOtp}</b> {t("login_dev_otp_note")}
            </p>
          )}
          <label className="text-sm font-semibold">{t("login_otp_label")}</label>
          <input
            className="input tracking-[0.3em] text-center"
            placeholder={t("login_otp_placeholder")}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            maxLength={6}
            required
          />

          <div className="border-t border-line pt-3 mt-1">
            <p className="text-sm text-ink-soft mb-2">{t("login_new_here")}</p>
            <label className="text-sm font-semibold">{t("login_name_label")}</label>
            <input className="input mt-1 mb-3" placeholder={t("login_name_placeholder")} value={name} onChange={(e) => setName(e.target.value)} />

            <label className="text-sm font-semibold">{t("login_i_am")}</label>
            <div className="flex gap-2 mt-1 mb-3">
              {ROLES.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  onClick={() => setRole(r.value)}
                  className={`flex-1 flex flex-col items-center gap-1 rounded-xl border-2 px-2 py-2 text-xs font-semibold transition-colors ${
                    role === r.value ? "border-maroon bg-gold-soft" : "border-line"
                  }`}
                >
                  <img src={r.icon} alt="" className="h-8 w-8 rounded-full" />
                  {r.label}
                </button>
              ))}
            </div>

            <label className="text-sm font-semibold">{t("login_gender_label")}</label>
            <div className="flex gap-2 mt-1">
              {GENDERS.map((g) => (
                <button
                  key={g.value}
                  type="button"
                  onClick={() => setGender(g.value)}
                  className={`flex-1 rounded-full border-2 px-3 py-1.5 text-xs font-semibold transition-colors ${
                    gender === g.value ? "border-maroon bg-gold-soft text-maroon" : "border-line text-ink-soft"
                  }`}
                >
                  {g.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-ink-soft mt-1">{t("login_gender_note")}</p>
          </div>

          <p className="text-xs text-ink-soft">
            {t("login_agree_prefix")}{" "}
            <Link href="/legal/terms" className="underline text-maroon-soft">{t("footer_terms")}</Link> {t("login_agree_and")}{" "}
            <Link href="/legal/privacy" className="underline text-maroon-soft">{t("footer_privacy")}</Link>.
          </p>
          <button className="btn-primary mt-1" disabled={loading}>
            {loading ? t("login_verifying") : t("login_verify")}
          </button>
          <button type="button" className="text-xs text-ink-soft" onClick={() => setStep("phone")}>
            {t("login_change_phone")}
          </button>
        </form>
      )}

      {error && <p className="text-red-700 text-sm mt-3">{error}</p>}

      <Link href="/admin-login" className="block text-center text-xs text-ink-soft underline mt-4">
        AryaVeda Mehndi team? Admin login
      </Link>
    </div>
  );
}
