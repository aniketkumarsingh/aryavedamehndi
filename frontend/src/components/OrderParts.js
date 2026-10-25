// Shared pieces of the custom/event order pages - styles in globals.css
// ("Order pages" section).

const ICONS = {
  hand: (
    <>
      <path d="M8 21c-2-1.5-3.5-4-3.5-7V9.5a1.5 1.5 0 013 0V12" />
      <path d="M7.5 12V5.5a1.5 1.5 0 013 0V11" />
      <path d="M10.5 11V4a1.5 1.5 0 013 0v7" />
      <path d="M13.5 11V5.5a1.5 1.5 0 013 0V13c0 4-2 8-6.5 8H8" />
      <circle cx="12" cy="15.5" r="1.4" />
    </>
  ),
  people: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19c.8-3.2 3-5 5.5-5s4.7 1.8 5.5 5" />
      <circle cx="17" cy="9" r="2.4" />
      <path d="M15.5 14.2c2.3.2 4 1.8 4.8 4.8" />
    </>
  ),
  tag: (
    <>
      <path d="M3.5 12.5V5a1.5 1.5 0 011.5-1.5h7.5l8 8-9 9z" />
      <circle cx="8" cy="8" r="1.5" />
    </>
  ),
  receipt: (
    <>
      <path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" />
      <path d="M9 8h6M9 12h6M9 16h3" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3l7.5 3v5.5c0 4.5-3.2 8.2-7.5 9.5-4.3-1.3-7.5-5-7.5-9.5V6z" />
      <path d="M8.8 12.2l2.2 2.2 4.3-4.6" />
    </>
  ),
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21s-6.5-6-6.5-11a6.5 6.5 0 0113 0c0 5-6.5 11-6.5 11z" />
      <circle cx="12" cy="10" r="2.3" />
    </>
  ),
  sparkle: <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM18.5 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" />,
};

export function Icon({ name, className = "w-6 h-6" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      {ICONS[name]}
    </svg>
  );
}

/** Invitation-card hero: double gold frame, paisley corners, mandala watermark. */
export function OrnateHero({ eyebrow, title, children }) {
  return (
    <section className="invitation-frame text-center flex flex-col items-center gap-3 px-6 py-10 sm:px-12 sm:py-12 mx-2 overflow-hidden">
      <span className="corner-tl" aria-hidden="true" />
      <span className="corner-tr" aria-hidden="true" />
      <span className="corner-bl" aria-hidden="true" />
      <span className="corner-br" aria-hidden="true" />
      <img
        src="/patterns/mandala.svg"
        alt=""
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-1/2 w-[440px] max-w-none -translate-x-1/2 -translate-y-1/2 opacity-[0.14]"
      />
      {eyebrow && <span className="chip relative">{eyebrow}</span>}
      <h1 className="relative text-3xl sm:text-4xl font-semibold text-maroon text-balance max-w-xl">{title}</h1>
      <div className="relative text-ink-soft max-w-xl text-sm sm:text-base">{children}</div>
    </section>
  );
}

export function StepHeading({ n, title, hint }) {
  return (
    <div className="flex items-start gap-3">
      <span className="medallion">{n}</span>
      <div>
        <h2 className="text-lg font-semibold text-maroon leading-tight mt-1">{title}</h2>
        {hint && <p className="text-xs text-ink-soft mt-0.5">{hint}</p>}
      </div>
    </div>
  );
}

export function QuantityStepper({ value, onChange, min = 1, max = 500 }) {
  const n = Number(value) || min;
  const set = (v) => onChange(Math.max(min, Math.min(max, v)));
  return (
    <div className="inline-flex items-center rounded-full border border-line bg-ivory-raised overflow-hidden">
      <button type="button" className="w-9 h-9 text-lg text-maroon hover:bg-gold-soft disabled:opacity-40" onClick={() => set(n - 1)} disabled={n <= min} aria-label="One fewer person">
        −
      </button>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => set(n)}
        className="w-12 text-center bg-transparent font-semibold [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
        aria-label="Number of people"
      />
      <button type="button" className="w-9 h-9 text-lg text-maroon hover:bg-gold-soft disabled:opacity-40" onClick={() => set(n + 1)} disabled={n >= max} aria-label="One more person">
        +
      </button>
    </div>
  );
}

/** Bill-style price summary. `rows` are [label, value, emphasis?]. */
export function Receipt({ title, subtitle, rows, total, footnotes = [], children }) {
  return (
    <div className="receipt fade-up">
      <div className="receipt-head">
        <p className="font-display text-lg leading-tight flex items-center gap-2">
          <Icon name="receipt" className="w-5 h-5 text-gold-soft" />
          {title}
        </p>
        {subtitle && <p className="text-xs opacity-80 mt-0.5">{subtitle}</p>}
      </div>
      <div className="px-5 pt-5 pb-4 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="receipt-row">
            <span className="text-ink-soft">{label}</span>
            <span className="font-semibold text-right">{value}</span>
          </div>
        ))}
        {total && (
          <>
            <div className="receipt-rule" />
            <div className="receipt-row items-baseline">
              <span className="font-display text-base">{total[0]}</span>
              <span className="font-display text-xl font-semibold text-maroon text-right">{total[1]}</span>
            </div>
          </>
        )}
        {footnotes.filter(Boolean).map((f) => (
          <p key={f} className="text-xs text-ink-soft mt-2 flex gap-1.5">
            <span className="text-gold">✦</span>
            <span>{f}</span>
          </p>
        ))}
        {children}
      </div>
    </div>
  );
}

const TRACK = [
  ["requested", "Requested"],
  ["quoted", "Quote ready"],
  ["confirmed", "Confirmed"],
  ["completed", "Celebrated"],
];

/** Progress through the bulk order statuses. */
export function StatusTracker({ status }) {
  if (status === "cancelled") {
    return <p className="text-sm text-red-700 font-semibold text-center">This order was cancelled</p>;
  }
  const current = TRACK.findIndex(([key]) => key === status);
  return (
    <ol className="flex items-start" aria-label="Order progress">
      {TRACK.map(([key, label], i) => {
        const done = i <= current;
        return (
          <li key={key} className="flex-1 flex flex-col items-center text-center relative" aria-current={i === current ? "step" : undefined}>
            {i > 0 && <span className={`absolute top-3.5 right-1/2 w-full h-0.5 ${i <= current ? "bg-gold" : "bg-line"}`} aria-hidden="true" />}
            <span
              className={`relative z-10 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                done ? "bg-maroon text-ivory-raised" : "bg-ivory-raised border-2 border-line text-ink-soft"
              } ${i === current ? "ring-4 ring-gold-soft" : ""}`}
            >
              {i < current ? "✓" : i + 1}
            </span>
            <span className={`text-[11px] mt-1.5 leading-tight ${done ? "text-maroon font-semibold" : "text-ink-soft"}`}>{label}</span>
          </li>
        );
      })}
    </ol>
  );
}
