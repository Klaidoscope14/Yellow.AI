/**
 * NEXUS wordmark — SVG-based so it scales crisply and inherits color via
 * currentColor. Uses Inter 900 (loaded from Google Fonts in index.html)
 * with tight negative tracking to match the reference proportions.
 * The E's subtle inward-notched middle bar is done as a tiny <rect> mask
 * overlaid at the letter's mid-height — the "bent E" brand detail.
 */
export function NexusWordmark({ height = 22 }: { height?: number }) {
  return (
    <svg
      className="nexus-wordmark-svg"
      height={height}
      viewBox="0 0 220 44"
      role="img"
      aria-label="Nexus"
    >
      <text
        x="0"
        y="36"
        fontFamily="Inter, ui-sans-serif, system-ui, sans-serif"
        fontWeight="900"
        fontSize="44"
        letterSpacing="-2.6"
        fill="currentColor"
      >
        NEXUS
      </text>
      {/* Custom E middle-bar treatment: overlay a small rect the color of
          the background over the right end of the middle bar, giving the
          E its distinctive shorter middle stroke. Positioned over the
          "E" glyph approximately. */}
      <rect x="66" y="20" width="7" height="6" fill="var(--bg, #fbfaf6)" />
    </svg>
  );
}
