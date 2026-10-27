/** Read-only star rating, e.g. <Stars value={4.3} count={12} />. */
export default function Stars({ value = 0, count, className = "" }) {
  const rounded = Math.round(value);
  return (
    <span className={`inline-flex items-center gap-1 text-sm ${className}`} aria-label={`${Number(value).toFixed(1)} out of 5 stars`}>
      <span className="text-gold tracking-tight" aria-hidden="true">
        {"★".repeat(rounded) + "☆".repeat(5 - rounded)}
      </span>
      <span className="text-ink-soft text-xs">
        {Number(value).toFixed(1)}
        {count != null && ` (${count})`}
      </span>
    </span>
  );
}
