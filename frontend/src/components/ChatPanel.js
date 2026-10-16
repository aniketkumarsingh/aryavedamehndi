import { useEffect, useRef, useState } from "react";
import { api, getStoredUser } from "@/lib/api";
import { buildChatWsUrl } from "@/lib/chatSocket";

const RECONNECT_DELAY_MS = 3000;

export default function ChatPanel({ bookingId }) {
  const me = getStoredUser();
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const wsRef = useRef(null);
  const listRef = useRef(null);
  const reconnectTimer = useRef(null);
  const closedByUs = useRef(false);

  useEffect(() => {
    api
      .get(`/bookings/${bookingId}/chat/messages`)
      .then(setMessages)
      .catch((e) => setError(e.message));

    closedByUs.current = false;
    connect();

    return () => {
      closedByUs.current = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingId]);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages]);

  function connect() {
    const ws = new WebSocket(buildChatWsUrl(bookingId));
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      setMessages((prev) => (prev.some((m) => m.id === msg.id) ? prev : [...prev, msg]));
    };
    ws.onclose = () => {
      setConnected(false);
      if (!closedByUs.current) {
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };
    ws.onerror = () => ws.close();
  }

  function send(e) {
    e.preventDefault();
    const body = draft.trim();
    if (!body || wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ body }));
    setDraft("");
  }

  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Chat</h2>
        <span className={`text-xs ${connected ? "text-leaf" : "text-ink-soft"}`}>{connected ? "● Live" : "○ Connecting…"}</span>
      </div>
      {error && <p className="text-xs text-red-700">{error}</p>}
      <div ref={listRef} className="flex flex-col gap-2 max-h-80 overflow-y-auto pr-1">
        {messages.length === 0 && <p className="text-sm text-ink-soft">No messages yet — say hello!</p>}
        {messages.map((m) => {
          const mine = m.sender_id === me?.id;
          return (
            <div key={m.id} className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${mine ? "self-end bg-gold-soft" : "self-start bg-ivory border border-line"}`}>
              <p>{m.body}</p>
              <p className="text-[10px] text-ink-soft mt-0.5">{new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p>
            </div>
          );
        })}
      </div>
      <form onSubmit={send} className="flex gap-2">
        <input
          className="input flex-1"
          placeholder="Type a message…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={2000}
        />
        <button className="btn-primary text-sm" disabled={!connected || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
