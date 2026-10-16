import { useEffect, useRef, useState } from "react";

/** Captures a photo directly from the device camera - there is no file
 * input anywhere in this component, so there is no way to pick an image
 * from the gallery instead. Used for the consumer's profile selfie. */
export default function CameraCapture({ onCapture, busy, previewUrl }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [active, setActive] = useState(false);
  const [error, setError] = useState("");
  const [captured, setCaptured] = useState(null);

  useEffect(() => stopCamera, []);

  async function startCamera() {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setActive(true);
    } catch (err) {
      setError("Couldn't access your camera - please allow camera permission and try again.");
    }
  }

  function stopCamera() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setActive(false);
  }

  function takePhoto() {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        setCaptured(URL.createObjectURL(blob));
        stopCamera();
        onCapture(new File([blob], "selfie.jpg", { type: "image/jpeg" }));
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
          <video ref={videoRef} playsInline muted className="w-56 h-56 object-cover rounded-full border-2 border-gold" />
          <button type="button" className="btn-primary text-sm" onClick={takePhoto} disabled={busy}>
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
          <button type="button" className="btn-secondary text-sm" onClick={startCamera} disabled={busy}>
            {shown ? "Retake with camera" : "Open camera to take selfie"}
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
