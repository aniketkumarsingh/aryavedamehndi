import { useEffect, useState } from "react";
import AccountData from "@/components/AccountData";
import { api } from "@/lib/api";
import ArtistDesignsManager from "@/components/ArtistDesignsManager";
import CameraCapture from "@/components/CameraCapture";
import FileUpload from "@/components/FileUpload";
import Lightbox from "@/components/Lightbox";

const TABS = ["About Me", "Verification", "Account Info"];

const CONSENT_TEXT =
  "I consent to AryaVeda Mehndi collecting, storing and processing my personal data - including my date of birth, " +
  "guardian/emergency contact details, government ID proof, address proof and bank account details - for the " +
  "purpose of identity verification, safety checks and enabling bookings on the platform, in accordance with the " +
  "Digital Personal Data Protection Act, 2023. I can withdraw this consent at any time, which will pause new " +
  "bookings until it is given again.";

export default function ArtistProfilePage() {
  const [profile, setProfile] = useState(null);
  const [profileMissing, setProfileMissing] = useState(false);
  const [tab, setTab] = useState("About Me");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [lightbox, setLightbox] = useState(null); // { images, index }
  const [locations, setLocations] = useState([]);

  // About Me
  const [fullName, setFullName] = useState("");
  const [dob, setDob] = useState("");
  const [guardianName, setGuardianName] = useState("");
  const [emergencyName, setEmergencyName] = useState("");
  const [emergencyPhone, setEmergencyPhone] = useState("");
  const [bio, setBio] = useState("");
  const [radius, setRadius] = useState(10);
  const [addressText, setAddressText] = useState("");
  const [city, setCity] = useState("");
  const [slug, setSlug] = useState("");
  const [coords, setCoords] = useState(null);
  const [locLabel, setLocLabel] = useState("");
  const [locAddress, setLocAddress] = useState("");

  // Verification
  const [idProofType, setIdProofType] = useState("aadhaar");
  const [idProofNumber, setIdProofNumber] = useState("");
  const [panNumber, setPanNumber] = useState("");

  // Account info
  const [bankAccountNumber, setBankAccountNumber] = useState("");
  const [bankIfsc, setBankIfsc] = useState("");
  const [bankHolderName, setBankHolderName] = useState("");

  function loadProfile() {
    api
      .get("/artists/me/profile")
      .then((p) => {
        setProfile(p);
        setProfileMissing(false);
        setFullName(p.user?.name || "");
        setDob(p.date_of_birth || "");
        setGuardianName(p.guardian_name || "");
        setEmergencyName(p.emergency_contact_name || "");
        setEmergencyPhone(p.emergency_contact_phone || "");
        setBio(p.bio || "");
        setRadius(p.service_radius_km);
        setAddressText(p.address_text || "");
        setCity(p.city || "");
        setSlug(p.slug || "");
        setIdProofType(p.id_proof_type || "aadhaar");
        setIdProofNumber(p.id_proof_number || "");
        setPanNumber(p.pan_number || "");
        setBankAccountNumber(p.bank_account_number || "");
        setBankIfsc(p.bank_ifsc_code || "");
        setBankHolderName(p.bank_account_holder_name || "");
      })
      .catch(() => setProfileMissing(true));
  }

  function loadLocations() {
    api.get("/artists/me/locations").then(setLocations).catch(() => {});
  }

  useEffect(() => {
    loadProfile();
    loadLocations();
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition((pos) => setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude }));
    }
  }, []);

  const consented = !!profile?.consent_given;

  async function toggleConsent(agree) {
    setBusy(true);
    setError("");
    try {
      const updated = await api.post("/artists/me/consent", { agree });
      setProfile(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile(e) {
    e.preventDefault();
    if (!coords) {
      setError("Allow location access first — consumers find you by this primary location.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload = {
        full_name: fullName || null,
        bio,
        service_radius_km: Number(radius),
        address_text: addressText || null,
        city: city.trim(),
        base_lat: coords.lat,
        base_lng: coords.lng,
        pan_number: panNumber || null,
      };
      if (consented) {
        Object.assign(payload, {
          date_of_birth: dob || null,
          guardian_name: guardianName || null,
          emergency_contact_name: emergencyName || null,
          emergency_contact_phone: emergencyPhone || null,
          id_proof_type: idProofType || null,
          id_proof_number: idProofNumber || null,
          bank_account_number: bankAccountNumber || null,
          bank_ifsc_code: bankIfsc || null,
          bank_account_holder_name: bankHolderName || null,
        });
      }
      const updated = await api.put("/artists/me/profile", payload);
      setProfile(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function uploadFile(endpoint, file) {
    setBusy(true);
    setError("");
    try {
      await api.upload(endpoint, file);
      loadProfile();
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function addLocation(e) {
    e.preventDefault();
    if (!navigator.geolocation) return;
    setBusy(true);
    setError("");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          await api.post("/artists/me/locations", {
            label: locLabel || "Extra location",
            address_text: locAddress || null,
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
          });
          setLocLabel("");
          setLocAddress("");
          loadLocations();
        } catch (err) {
          setError(err.message);
        } finally {
          setBusy(false);
        }
      },
      () => {
        setError("Allow location access to add this as a service location.");
        setBusy(false);
      }
    );
  }

  async function removeLocation(id) {
    setBusy(true);
    try {
      await api.del(`/artists/me/locations/${id}`);
      loadLocations();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <h1 className="text-2xl">My Profile &amp; Verification</h1>
      {error && <p className="text-sm text-red-700">{error}</p>}

      {profileMissing && (
        <p className="text-sm text-ink-soft">Fill in the About Me tab below to set up your artist profile for the first time.</p>
      )}

      <div className="card p-5">
        <h2 className="font-semibold mb-2">Data Consent</h2>
        <p className="text-xs text-ink-soft mb-3">{CONSENT_TEXT}</p>
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={consented} disabled={busy} onChange={(e) => toggleConsent(e.target.checked)} />
          I have read and agree to this consent statement
          {profile?.consent_given_at && (
            <span className="chip">given {new Date(profile.consent_given_at).toLocaleDateString()}</span>
          )}
        </label>
        {!consented && (
          <p className="text-xs text-gold mt-2">
            Date of birth, ID proof, emergency contact and bank details can only be saved after you agree above.
          </p>
        )}
      </div>

      <div className="flex gap-2 flex-wrap">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} className={tab === t ? "btn-primary text-sm" : "btn-secondary text-sm"}>
            {t}
          </button>
        ))}
      </div>

      <form onSubmit={saveProfile} className="flex flex-col gap-6">
        {tab === "About Me" && (
          <div className="card p-5 flex flex-col gap-4">
            <div className="flex items-center gap-4">
              <FileUpload
                variant="avatar"
                previewUrl={profile?.profile_photo_url}
                busy={busy}
                label="Upload profile picture"
                onFile={(f) => uploadFile("/artists/me/profile-photo", f)}
              />
              <div>
                <p className="text-sm font-semibold">Profile picture</p>
                <p className="text-xs text-ink-soft">Shown to consumers when they find you.</p>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-sm">Full name</label>
              <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} />

              <label className="text-sm">Date of birth</label>
              <input
                className="input"
                type="date"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
                disabled={!consented}
                title={!consented ? "Accept the consent form above first" : ""}
              />

              <label className="text-sm">Father&apos;s or husband&apos;s name</label>
              <input
                className="input"
                value={guardianName}
                onChange={(e) => setGuardianName(e.target.value)}
                disabled={!consented}
              />

              <label className="text-sm">Contact number</label>
              <input className="input" value={profile?.user?.phone || ""} disabled />

              <label className="text-sm">Emergency contact name</label>
              <input
                className="input"
                value={emergencyName}
                onChange={(e) => setEmergencyName(e.target.value)}
                disabled={!consented}
              />
              <label className="text-sm">Emergency contact phone</label>
              <input
                className="input"
                value={emergencyPhone}
                onChange={(e) => setEmergencyPhone(e.target.value)}
                disabled={!consented}
              />

              <label className="text-sm">Bio</label>
              <textarea className="input" value={bio} onChange={(e) => setBio(e.target.value)} />

              <label className="text-sm">City (shown on your public page)</label>
              <input className="input" maxLength={60} placeholder="e.g. Jaipur" value={city} onChange={(e) => setCity(e.target.value)} />
              {slug && profile?.kyc_status === "approved" && (
                <p className="text-xs text-ink-soft">
                  Your public page: <a className="underline" href={`/artists/${slug}`} target="_blank" rel="noopener noreferrer">/artists/{slug}</a> — share it on Instagram and WhatsApp.
                </p>
              )}

              <label className="text-sm">Service radius (km)</label>
              <input className="input" type="number" value={radius} onChange={(e) => setRadius(e.target.value)} />

              <label className="text-sm">Permanent address</label>
              <textarea
                className="input"
                placeholder="House no., street, area, city, PIN code"
                value={addressText}
                onChange={(e) => setAddressText(e.target.value)}
              />
              <p className="text-xs text-ink-soft">Saving uses your current device location as the map point for this address.</p>
            </div>

            <button className="btn-primary self-start" disabled={busy}>
              Save About Me
            </button>

            <div className="border-t border-line pt-4">
              <h3 className="font-semibold mb-1">Extra Service Locations</h3>
              <p className="text-xs text-ink-soft mb-3">
                Add up to 2 more places you take bookings from — consumers searching near any of them will find you.
              </p>
              <div className="flex flex-col gap-2 mb-3 text-sm">
                {locations.map((loc) => (
                  <div key={loc.id} className="flex justify-between items-start border-b border-line pb-2">
                    <div>
                      <div>{loc.label}</div>
                      {loc.address_text && <div className="text-ink-soft text-xs mt-0.5">{loc.address_text}</div>}
                    </div>
                    <button type="button" className="text-xs text-red-700" onClick={() => removeLocation(loc.id)} disabled={busy}>
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              {locations.length < 2 ? (
                <div className="flex flex-col gap-2">
                  <input className="input" placeholder="Label, e.g. Mother's house" value={locLabel} onChange={(e) => setLocLabel(e.target.value)} />
                  <input className="input" placeholder="Address (optional)" value={locAddress} onChange={(e) => setLocAddress(e.target.value)} />
                  <button type="button" className="btn-secondary self-start text-sm" onClick={addLocation} disabled={busy || !locLabel}>
                    Add (uses current location)
                  </button>
                </div>
              ) : (
                <p className="text-xs text-ink-soft">You&apos;ve added the maximum of 2 extra locations.</p>
              )}
            </div>
          </div>
        )}

        {tab === "Verification" && profile && (
          <div className="card p-5 flex flex-col gap-4">
            <p className="text-sm">
              KYC status: <b>{profile.kyc_status}</b>
              {profile.kyc_status !== "approved" && " — an admin needs to approve your documents before you appear in search."}
            </p>

            <div>
              <label className="text-sm">ID proof type</label>
              <select className="input mt-1" value={idProofType} onChange={(e) => setIdProofType(e.target.value)} disabled={!consented}>
                <option value="aadhaar">Aadhaar card</option>
                <option value="driving_license">Driving licence</option>
                <option value="passport">Passport</option>
              </select>
              <label className="text-sm mt-2 block">ID number</label>
              <input className="input mt-1" value={idProofNumber} onChange={(e) => setIdProofNumber(e.target.value)} disabled={!consented} />
              <div className="mt-2">
                <DocTile
                  title={`${idProofType.replaceAll("_", " ")} photo`}
                  previewUrl={profile.id_proof_doc_url}
                  onUpload={(f) => uploadFile("/artists/me/id-proof-doc", f)}
                  busy={busy}
                  disabled={!consented}
                />
              </div>
            </div>

            <DocTile
              title="Selfie"
              previewUrl={profile.kyc_selfie_url}
              onUpload={(f) => uploadFile("/artists/me/kyc-selfie", f)}
              busy={busy}
              liveCamera
            />

            <div>
              <label className="text-sm">PAN number</label>
              <input className="input mt-1" value={panNumber} onChange={(e) => setPanNumber(e.target.value)} placeholder="ABCDE1234F" />
              <div className="mt-2">
                <DocTile
                  title="PAN card photo"
                  previewUrl={profile.pan_doc_url}
                  onUpload={(f) => uploadFile("/artists/me/pan-doc", f)}
                  busy={busy}
                  disabled={!consented}
                />
              </div>
            </div>

            <div>
              <p className="text-sm font-semibold mb-2">Address verification</p>
              <p className="text-xs text-ink-soft mb-2">Upload a utility bill, rent agreement, or similar document showing the address above.</p>
              <DocTile
                title="Address proof"
                previewUrl={profile.address_proof_doc_url}
                onUpload={(f) => uploadFile("/artists/me/address-proof-doc", f)}
                busy={busy}
                disabled={!consented}
              />
            </div>

            <button className="btn-primary self-start" disabled={busy}>
              Save Verification Details
            </button>
          </div>
        )}

        {tab === "Account Info" && (
          <div className="card p-5 flex flex-col gap-2">
            <p className="text-xs text-ink-soft mb-2">
              For your records — the package amount is always settled directly between you and the consumer, the
              platform never moves money through this account.
            </p>
            <label className="text-sm">Account holder name</label>
            <input className="input" value={bankHolderName} onChange={(e) => setBankHolderName(e.target.value)} disabled={!consented} />
            <label className="text-sm">Account number</label>
            <input className="input" value={bankAccountNumber} onChange={(e) => setBankAccountNumber(e.target.value)} disabled={!consented} />
            <label className="text-sm">IFSC code</label>
            <input
              className="input"
              value={bankIfsc}
              onChange={(e) => setBankIfsc(e.target.value.toUpperCase())}
              placeholder="HDFC0001234"
              disabled={!consented}
            />
            <button className="btn-primary self-start mt-2" disabled={busy}>
              Save Account Info
            </button>
          </div>
        )}
      </form>

      {profile && (
        <div className="card p-5">
          <h2 className="font-semibold mb-1">Portfolio</h2>
          <p className="text-sm text-ink-soft mb-3">Show off your best work — consumers see these when browsing artists.</p>
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-3 mb-3">
            {(profile.portfolio_urls || "")
              .split(",")
              .filter(Boolean)
              .map((url, i, arr) => (
                <button key={url} type="button" onClick={() => setLightbox({ images: arr, index: i })}>
                  <img src={url} alt="" className="w-full aspect-square object-cover rounded-xl border border-line shadow-sm" />
                </button>
              ))}
          </div>
          <FileUpload
            onFile={(f) => uploadFile("/artists/me/portfolio", f)}
            busy={busy}
            label="Add a portfolio photo"
            hint="JPG or PNG, your best mehndi work"
          />
        </div>
      )}

      {profile && <ArtistDesignsManager />}

      <Lightbox
        images={lightbox?.images ?? null}
        index={lightbox?.index ?? 0}
        onClose={() => setLightbox(null)}
        onIndexChange={(i) => setLightbox((prev) => ({ ...prev, index: i }))}
      />

      <AccountData />
    </div>
  );
}

function DocTile({ title, previewUrl, onUpload, busy, disabled, liveCamera }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-sm font-semibold">{title}</span>
        {previewUrl && <span className="chip">uploaded</span>}
      </div>
      {disabled ? (
        <p className="text-xs text-ink-soft border-2 border-dashed border-line rounded-xl px-6 py-8 text-center">
          Accept the consent form above to unlock this upload.
        </p>
      ) : liveCamera ? (
        // A file input's `capture` attribute is ignored on desktop browsers
        // (it just opens a file picker), so a KYC selfie uses the live camera.
        <CameraCapture onCapture={onUpload} busy={busy} previewUrl={previewUrl} fileName="kyc-selfie.jpg" />
      ) : (
        <FileUpload onFile={onUpload} busy={busy} previewUrl={previewUrl} label={`Upload ${title.toLowerCase()}`} />
      )}
    </div>
  );
}
