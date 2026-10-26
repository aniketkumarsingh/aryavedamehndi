import { api } from "@/lib/api";

/** Downloads an authenticated file (e.g. an invoice PDF) from the API. A
 * plain link can't send the login token, so fetch it and save the blob. */
export async function downloadFile(path, filename) {
  const blob = await api.blob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
