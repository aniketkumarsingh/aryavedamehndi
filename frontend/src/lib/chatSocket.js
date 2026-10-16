import { getToken } from "@/lib/api";

export function buildChatWsUrl(bookingId) {
  const token = getToken();
  const base = process.env.NEXT_PUBLIC_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;
  const wsBase = base.replace(/^http/, "ws");
  return `${wsBase}/ws/bookings/${bookingId}/chat?token=${encodeURIComponent(token || "")}`;
}
