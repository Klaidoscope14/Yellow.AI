/** Turbulence + displacement map: the refraction behind the glass surfaces
 * used by the floating "Ask Nexus" pills and panels. */
export function GlassFilter() {
  return (
    <svg className="ai-glass-defs" aria-hidden>
      <defs>
        <filter id="ai-glass" x="0%" y="0%" width="100%" height="100%" colorInterpolationFilters="sRGB">
          <feTurbulence type="fractalNoise" baseFrequency="0.012 0.012" numOctaves="2" seed="4" result="noise" />
          <feGaussianBlur in="noise" stdDeviation="2" result="blurredNoise" />
          <feDisplacementMap
            in="SourceGraphic"
            in2="blurredNoise"
            scale="24"
            xChannelSelector="R"
            yChannelSelector="B"
            result="displaced"
          />
          <feGaussianBlur in="displaced" stdDeviation="0.4" />
        </filter>
      </defs>
    </svg>
  );
}
