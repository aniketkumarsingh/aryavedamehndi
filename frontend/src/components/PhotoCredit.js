/** The credit an image's licence requires, or the label an AI illustration
 * must carry. `credit` comes from the API (Design.image_credit /
 * DesignImage.credit): {author, license, license_url, source_url, edited}
 * for licensed photos, {generator} for illustrations. Renders nothing for
 * photos that need no credit. */
export default function PhotoCredit({ credit, illustration = false, className = "" }) {
  if (illustration || credit?.generator) {
    return (
      <p className={`text-xs text-ink-soft ${className}`}>
        <span className="font-semibold text-maroon-soft">AI illustration</span> - shows the idea of this design, not a real
        mehndi. Your artist recreates it by hand, so the finished design will differ in detail.
      </p>
    );
  }
  if (!credit?.author) return null;
  const link = (href, text) =>
    href ? (
      <a href={href} target="_blank" rel="noopener noreferrer license" className="underline hover:text-maroon">
        {text}
      </a>
    ) : (
      text
    );
  return (
    <p className={`text-[11px] text-ink-soft ${className}`}>
      Photo: {link(credit.source_url, credit.author)}, {link(credit.license_url, credit.license)}
      {credit.edited ? " · edited" : ""}
    </p>
  );
}
