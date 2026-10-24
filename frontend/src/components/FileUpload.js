import { useRef } from "react";

const SHRINK_ABOVE_BYTES = 3 * 1024 * 1024;
const MAX_DIMENSION = 2560;

/** Modern phone cameras produce 5-15MB photos, over the API's upload cap
 * (MAX_UPLOAD_SIZE_MB, 8MB by default). Large photos are re-encoded as a
 * JPEG no bigger than MAX_DIMENSION on the long edge - still plenty for KYC
 * documents and design matching. Falls back to the original file if the
 * browser can't decode it (e.g. HEIC on a desktop browser). */
async function shrinkIfLarge(file) {
  if (file.size <= SHRINK_ABOVE_BYTES || !file.type.startsWith("image/") || file.type === "image/gif") return file;
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, MAX_DIMENSION / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.88));
    if (!blob || blob.size >= file.size) return file;
    return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
  } catch {
    return file;
  }
}

export default function FileUpload({
  onFile,
  accept = "image/*",
  label = "Click to upload a photo",
  hint,
  busy = false,
  previewUrl,
  variant = "dropzone",
  capture,
}) {
  const inputRef = useRef(null);

  async function handleChange(e) {
    const file = e.target.files[0];
    e.target.value = "";
    if (file) onFile(await shrinkIfLarge(file));
  }

  if (variant === "avatar") {
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={() => !busy && inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && !busy && inputRef.current?.click()}
        className={`group relative inline-flex h-24 w-24 items-center justify-center rounded-full border-2 border-dashed border-line bg-ivory cursor-pointer overflow-hidden hover:border-gold ${
          busy ? "opacity-60 pointer-events-none" : ""
        }`}
        title={label}
      >
        {previewUrl ? (
          <img src={previewUrl} alt="" className="h-full w-full object-cover" />
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="w-7 h-7 text-gold">
            <circle cx="12" cy="8.5" r="3.2" />
            <path d="M4.5 19.5c1.6-3.2 4.4-5 7.5-5s5.9 1.8 7.5 5" strokeLinecap="round" />
          </svg>
        )}
        <span className="absolute inset-x-0 bottom-0 bg-maroon/80 text-ivory-raised text-[10px] font-semibold py-1 text-center opacity-0 group-hover:opacity-100 transition-opacity">
          {busy ? "..." : "Change"}
        </span>
        <input ref={inputRef} type="file" accept={accept} capture={capture} className="hidden" onChange={handleChange} />
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => !busy && inputRef.current?.click()}
      onKeyDown={(e) => e.key === "Enter" && !busy && inputRef.current?.click()}
      className={`group flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-line bg-ivory px-6 py-8 text-center transition-colors cursor-pointer hover:border-gold hover:bg-gold-soft/50 ${
        busy ? "opacity-60 pointer-events-none" : ""
      }`}
    >
      {previewUrl ? (
        <img src={previewUrl} alt="" className="w-16 h-16 object-cover rounded-lg border border-line mb-1" />
      ) : capture ? (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="w-8 h-8 text-gold">
          <path d="M4 8a2 2 0 012-2h1.2l.9-1.5A1.5 1.5 0 019.4 4h5.2a1.5 1.5 0 011.3.75L16.8 6H18a2 2 0 012 2v9a2 2 0 01-2 2H6a2 2 0 01-2-2V8z" strokeLinejoin="round" />
          <circle cx="12" cy="13" r="3.3" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="w-8 h-8 text-gold">
          <path d="M12 15V4M12 4l-3.5 3.5M12 4l3.5 3.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M4.5 15v2.5A2.5 2.5 0 007 20h10a2.5 2.5 0 002.5-2.5V15" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      <span className="text-sm font-semibold text-maroon-soft group-hover:underline">
        {busy ? "Uploading..." : previewUrl ? (capture ? "Retake photo" : "Replace photo") : label}
      </span>
      {hint && <span className="text-xs text-ink-soft max-w-xs">{hint}</span>}
      <input ref={inputRef} type="file" accept={accept} capture={capture} className="hidden" onChange={handleChange} />
    </div>
  );
}
