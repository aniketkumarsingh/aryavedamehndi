import { useEffect, useState } from "react";
import Link from "next/link";
import AccountData from "@/components/AccountData";
import { api } from "@/lib/api";
import CameraCapture from "@/components/CameraCapture";
import SectionDivider from "@/components/SectionDivider";

const PRESETS = ["preset-1", "preset-2", "preset-3", "preset-4", "preset-5", "preset-6"];

const CONSENT_TEXT =
  "I consent to AryaVeda Mehndi storing my date of birth, anniversary date, guardian's name and secondary contact " +
  "number, for booking reminders and safety purposes, in accordance with the Digital Personal Data Protection Act, " +
  "2023. I can withdraw this consent at any time.";

export default function CustomerProfilePage() {
  const [me, setMe] = useState(null);
  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [guardianName, setGuardianName] = useState("");
  const [secondaryPhone, setSecondaryPhone] = useState("");
  const [dob, setDob] = useState("");
  const [anniversary, setAnniversary] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    api
      .get("/users/me")
      .then((u) => {
        setMe(u);
        setName(u.name || "");
        setGender(u.gender || "");
        setGuardianName(u.guardian_name || "");
        setSecondaryPhone(u.secondary_phone || "");
        setDob(u.date_of_birth || "");
        setAnniversary(u.anniversary_date || "");
      })
      .catch((e) => setError(e.message));
  }

  useEffect(load, []);

  const consented = !!me?.consent_given;

  async function toggleConsent(agree) {
    setBusy(true);
    setError("");
    try {
      const updated = await api.post("/users/me/consent", { agree });
      setMe(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveDetails(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = { name, gender };
      if (consented) {
        Object.assign(payload, {
          guardian_name: guardianName || null,
          secondary_phone: secondaryPhone || null,
          date_of_birth: dob || null,
          anniversary_date: anniversary || null,
        });
      }
      const updated = await api.put("/users/me", payload);
      setMe(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function pickPreset(presetId) {
    setBusy(true);
    setError("");
    try {
      const updated = await api.post("/users/me/avatar/preset", { preset_id: presetId });
      setMe(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function uploadSelfie(file) {
    setBusy(true);
    setError("");
    try {
      await api.upload("/users/me/avatar", file);
      load();
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-7 max-w-2xl">
      <div className="invitation-frame p-6 flex items-center gap-4">
        <span className="corner-tl" aria-hidden="true" />
        <span className="corner-tr" aria-hidden="true" />
        <span className="corner-bl" aria-hidden="true" />
        <span className="corner-br" aria-hidden="true" />
        <img
          src={me?.avatar_url || "/avatars/preset-1.svg"}
          alt=""
          className="h-16 w-16 rounded-full object-cover border-2 border-gold"
        />
        <div>
          <h1 className="text-2xl">{me?.name || "My Profile"}</h1>
          <p className="text-sm text-ink-soft">{me?.phone}</p>
        </div>
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}

      <div className="card p-6">
        <h2 className="font-semibold mb-2">Data Consent</h2>
        <p className="text-xs text-ink-soft mb-3">{CONSENT_TEXT}</p>
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={consented} disabled={busy} onChange={(e) => toggleConsent(e.target.checked)} />
          I agree
          {me?.consent_given_at && <span className="chip">given {new Date(me.consent_given_at).toLocaleDateString()}</span>}
        </label>
      </div>

      <div className="card p-6">
        <h2 className="font-semibold mb-2">Offers &amp; reminders</h2>
        <p className="text-sm mb-2">
          <Link href="/shop/wallet" className="underline text-maroon-soft">Wallet &amp; refer a friend →</Link>
        </p>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!me?.marketing_opt_in}
            disabled={busy}
            onChange={async (e) => {
              const opt_in = e.target.checked;
              try {
                await api.put("/users/me/marketing", { opt_in });
                setMe({ ...me, marketing_opt_in: opt_in });
              } catch (err) {
                setError(err.message);
              }
            }}
          />
          Send me offers and occasion reminders on WhatsApp
        </label>
        <p className="text-xs text-ink-soft mt-1">Order and booking updates are always sent, whatever you choose here.</p>
      </div>

      <div className="card p-6">
        <h2 className="font-semibold mb-1">Basic Details</h2>
        <p className="text-sm text-ink-soft mb-4">Kept private, used only for your bookings and safety-matching.</p>
        <form onSubmit={saveDetails} className="grid sm:grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-semibold">Full name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-semibold">Gender</label>
            <select className="input" value={gender} onChange={(e) => setGender(e.target.value)}>
              <option value="">Prefer not to say</option>
              <option value="female">Female</option>
              <option value="male">Male</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-semibold">Father&apos;s / Husband&apos;s name</label>
            <input className="input" value={guardianName} onChange={(e) => setGuardianName(e.target.value)} disabled={!consented} />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-semibold">Secondary contact number</label>
            <input
              className="input"
              value={secondaryPhone}
              onChange={(e) => setSecondaryPhone(e.target.value)}
              placeholder="Optional"
              disabled={!consented}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-semibold">Date of birth</label>
            <input className="input" type="date" value={dob} onChange={(e) => setDob(e.target.value)} disabled={!consented} />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-semibold">Anniversary date</label>
            <input className="input" type="date" value={anniversary} onChange={(e) => setAnniversary(e.target.value)} disabled={!consented} />
          </div>
          <p className="text-xs text-ink-soft sm:col-span-2">
            Gender is used to match you with a same-gender artist by default, for your comfort and safety.
            {!consented && " Accept the consent form above to fill in the fields above it."}
          </p>
          <button className="btn-primary self-start sm:col-span-2" disabled={busy}>
            Save Details
          </button>
        </form>
      </div>

      <SectionDivider />

      <div className="card p-6">
        <h2 className="font-semibold mb-1">Your Selfie</h2>
        <p className="text-sm text-ink-soft mb-4">
          For your safety, a profile selfie must be taken live with your camera — we don&apos;t accept photos from your gallery.
        </p>
        <CameraCapture busy={busy} previewUrl={me?.avatar_url?.startsWith("/avatars/") ? null : me?.avatar_url} onCapture={uploadSelfie} />
      </div>

      <div className="card p-6">
        <h2 className="font-semibold mb-1">Or Pick a Mehndi Avatar</h2>
        <p className="text-sm text-ink-soft mb-4">Prefer not to share a photo? Choose one of these instead.</p>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
          {PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              disabled={busy}
              onClick={() => pickPreset(p)}
              className={`rounded-full p-0.5 transition-shadow ${
                me?.avatar_url === `/avatars/${p}.svg` ? "ring-2 ring-maroon" : "hover:ring-2 hover:ring-gold"
              }`}
              title={p}
            >
              <img src={`/avatars/${p}.svg`} alt={p} className="w-full aspect-square rounded-full" />
            </button>
          ))}
        </div>
      </div>

      <AccountData />
    </div>
  );
}
