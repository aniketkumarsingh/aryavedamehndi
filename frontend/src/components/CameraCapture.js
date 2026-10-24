import { useEffect, useRef, useState } from "react";

function cameraErrorMessage(err) {
  switch (err?.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Camera permission was blocked. Allow camera access for this site in your browser settings, then try again.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No camera was found on this device.";
    case "NotReadableError":
    case "AbortError":
      return "Your camera is being used by another app or tab. Close it and try again.";
    default:
      return "Couldn't start your camera - please try again.";
  }
}

/** Captures a photo directly from the device camera - there is no file
 * input anywhere in this component, so there is no way to pick an image
 * from the gallery instead. Used for the consumer's profile selfie and the
 * artist's KYC selfie.
 *
 * `onCapture` may return a promise; if it resolves to `false` (upload
 * failed) the captured preview is discarded so it isn't mistaken for a
 * saved photo. */
export default function CameraCapture({ onCapture, busy, previewUrl, fileName = "selfie.jpg" }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [active, setActive] = useState(false);
  const [starting, setStarting] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [captured, setCaptured] = useState(null);

  useEffect(() => stopCamera, []);

  // The <video> only mounts once `active` flips true, so the stream has to
  // be attached here rather than in startCamera - there the ref is still null.
  useEffect(() => {
    const video = videoRef.current;
    if (!active || !video || !streamRef.current) return;
    video.srcObject = streamRef.current;
    video.play().catch(() => {});
  }, [active]);

  useEffect(() => () => captured && URL.revokeObjectURL(captured), [captured]);

  async function startCamera() {
    setError("");
    // getUserMedia only exists on secure origins (https or localhost) - e.g.
    // opening the dev server from a phone via http://192.168.x.x hides it.
    if (!navigator.mediaDevices?.getUserMedia) {
      setError(
        window.isSecureContext
          ? "This browser doesn't support camera access - please use an up-to-date Chrome or Safari."
          : "Camera only works over a secure (https) connection. Open this site via https and try again."
      );
      return;
    }
    setStarting(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 1280 } },
        audio: false,
      });
      stream.getVideoTracks().forEach((t) => (t.onended = stopCamera));
      streamRef.current = stream;
      setReady(false);
      setActive(true);
    } catch (err) {
      setError(cameraErrorMessage(err));
    } finally {
      setStarting(false);
    }
  }

  function stopCamera() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setActive(false);
    setReady(false);
  }

  function takePhoto() {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) {
      setError("The camera isn't ready yet - give it a second and try again.");
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob(
      async (blob) => {
        if (!blob) {
          setError("Couldn't capture the photo - please try again.");
          return;
        }
        const url = URL.createObjectURL(blob);
        setCaptured(url);
        stopCamera();
        const ok = await onCapture(new File([blob], fileName, { type: "image/jpeg" }));
        if (ok === false) setCaptured(null);
      },
      "image/jpeg",
      0.9
    );
  }

  const shown = captured || previewUrl;

  return (
    <div className="flex flex-col items-center gap-3">
      {active ? (
        <div className="flex flex-col items-center gap-2">
          <div className="relative w-56 h-56">
            {/* Mirrored like a mirror, which is what people expect from a
                front camera - the saved photo itself is not flipped. */}
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              onPlaying={() => setReady(true)}
              className="w-56 h-56 object-cover rounded-full border-2 border-gold bg-ink/10 -scale-x-100"
            />
            {!ready && (
              <span className="absolute inset-0 flex items-center justify-center text-xs text-ink-soft">
                Starting camera...
              </span>
            )}
          </div>
          <button type="button" className="btn-primary text-sm" onClick={takePhoto} disabled={busy || !ready}>
            📸 Capture
          </button>
          <button type="button" className="text-xs text-ink-soft" onClick={stopCamera}>
            Cancel
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2">
          {shown ? (
            <img src={shown} alt="Selfie" className="w-56 h-56 object-cover rounded-full border-2 border-gold" />
          ) : (
            <div className="w-56 h-56 rounded-full border-2 border-dashed border-line bg-ivory flex items-center justify-center text-ink-soft text-sm text-center px-4">
              No selfie yet
            </div>
          )}
          <button type="button" className="btn-secondary text-sm" onClick={startCamera} disabled={busy || starting}>
            {busy ? "Uploading..." : starting ? "Opening camera..." : shown ? "Retake with camera" : "Open camera to take selfie"}
          </button>
          <p className="text-xs text-ink-soft text-center max-w-xs">
            Camera only - gallery photos aren&apos;t accepted here, so we know this is really you right now.
          </p>
        </div>
      )}
      {error && <p className="text-xs text-red-700 text-center max-w-xs">{error}</p>}
    </div>
  );
}
