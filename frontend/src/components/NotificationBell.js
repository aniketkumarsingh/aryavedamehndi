import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/router";
import { api } from "@/lib/api";

export default function NotificationBell() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const boxRef = useRef(null);
  const PAGE_SIZE = 20;

  function loadCount() {
    api
      .get("/notifications/unread-count")
      .then((r) => setUnread(r.unread_count))
      .catch(() => {});
  }

  useEffect(() => {
    loadCount();
    const id = setInterval(loadCount, 30000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    function onClickOutside(e) {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function toggleOpen() {
    const next = !open;
    setOpen(next);
    if (next) {
      api
        .get("/notifications", { limit: PAGE_SIZE, offset: 0 })
        .then((rows) => {
          setItems(rows);
          setHasMore(rows.length === PAGE_SIZE);
        })
        .catch(() => {});
    }
  }

  async function loadMore() {
    setLoadingMore(true);
    try {
      const rows = await api.get("/notifications", { limit: PAGE_SIZE, offset: items.length });
      setItems((prev) => [...prev, ...rows]);
      setHasMore(rows.length === PAGE_SIZE);
    } catch {
      /* non-critical */
    } finally {
      setLoadingMore(false);
    }
  }

  async function onClickItem(n) {
    setOpen(false);
    if (!n.is_read) {
      try {
        await api.post(`/notifications/${n.id}/read`, {});
        loadCount();
      } catch {
        /* non-critical */
      }
    }
    if (n.link_url) router.push(n.link_url);
  }

  async function markAllRead() {
    try {
      await api.post("/notifications/read-all", {});
      setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnread(0);
    } catch {
      /* non-critical */
    }
  }

  return (
    <div className="relative" ref={boxRef}>
      <button onClick={toggleOpen} className="relative p-1.5 rounded-full hover:bg-ivory" aria-label="Notifications">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="w-5 h-5 text-maroon">
          <path d="M6 8a6 6 0 1112 0c0 4 1.5 6 2 7H4c.5-1 2-3 2-7z" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M9.5 19a2.5 2.5 0 005 0" strokeLinecap="round" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 bg-maroon text-ivory-raised text-[10px] font-bold rounded-full h-4 min-w-4 px-1 flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 max-w-[90vw] card p-0 overflow-hidden z-20 shadow-lg">
          <div className="flex items-center justify-between px-4 py-2 border-b border-line">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && (
              <button onClick={markAllRead} className="text-xs text-maroon-soft underline">
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 && <p className="text-sm text-ink-soft px-4 py-4">No notifications yet.</p>}
            {items.map((n) => (
              <button
                key={n.id}
                onClick={() => onClickItem(n)}
                className={`w-full text-left px-4 py-3 border-b border-line last:border-b-0 hover:bg-ivory ${
                  n.is_read ? "" : "bg-gold-soft/40"
                }`}
              >
                <div className="flex items-start gap-2">
                  {!n.is_read && <span className="h-1.5 w-1.5 rounded-full bg-gold mt-1.5 flex-none" />}
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{n.title}</p>
                    {n.body && <p className="text-xs text-ink-soft line-clamp-2">{n.body}</p>}
                    <p className="text-[10px] text-ink-soft mt-0.5">{new Date(n.created_at).toLocaleString()}</p>
                  </div>
                </div>
              </button>
            ))}
            {hasMore && (
              <button onClick={loadMore} disabled={loadingMore} className="w-full text-center text-xs text-maroon-soft underline py-2">
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
