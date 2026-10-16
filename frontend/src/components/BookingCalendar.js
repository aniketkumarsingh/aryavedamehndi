import { useMemo, useState } from "react";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAY_LABELS = ["S", "M", "T", "W", "T", "F", "S"];

function dateKey(d) {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

export default function BookingCalendar({ bookings, onSelectDay }) {
  const [cursor, setCursor] = useState(() => new Date());
  const [selectedKey, setSelectedKey] = useState(null);

  const byDay = useMemo(() => {
    const map = {};
    for (const b of bookings) {
      const d = new Date(b.scheduled_at);
      const key = dateKey(d);
      (map[key] = map[key] || []).push(b);
    }
    return map;
  }, [bookings]);

  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  const firstDay = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const startWeekday = firstDay.getDay();
  const today = new Date();

  const cells = [];
  for (let i = 0; i < startWeekday; i++) cells.push(null);
  for (let day = 1; day <= daysInMonth; day++) cells.push(day);

  function selectDay(day) {
    const d = new Date(year, month, day);
    const key = dateKey(d);
    setSelectedKey(key);
    onSelectDay?.(byDay[key] || [], d);
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <button type="button" className="btn-secondary text-sm" onClick={() => setCursor(new Date(year, month - 1, 1))}>
          ‹
        </button>
        <h2 className="font-semibold">
          {MONTH_NAMES[month]} {year}
        </h2>
        <button type="button" className="btn-secondary text-sm" onClick={() => setCursor(new Date(year, month + 1, 1))}>
          ›
        </button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-xs text-ink-soft mb-1">
        {WEEKDAY_LABELS.map((w, i) => (
          <div key={i}>{w}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((day, i) => {
          if (day === null) return <div key={i} />;
          const d = new Date(year, month, day);
          const key = dateKey(d);
          const hasBookings = byDay[key]?.length > 0;
          const isToday = dateKey(today) === key;
          const isSelected = selectedKey === key;
          return (
            <button
              key={i}
              type="button"
              onClick={() => selectDay(day)}
              className={`relative aspect-square rounded-lg text-sm flex items-center justify-center transition-colors ${
                isSelected ? "bg-maroon text-ivory-raised" : isToday ? "bg-gold-soft font-semibold" : "hover:bg-ivory"
              }`}
            >
              {day}
              {hasBookings && (
                <span
                  className={`absolute bottom-1 h-1.5 w-1.5 rounded-full ${isSelected ? "bg-ivory-raised" : "bg-gold"}`}
                />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
